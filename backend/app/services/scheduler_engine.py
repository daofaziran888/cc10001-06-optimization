"""调度引擎：批量扫描调度窗口，去重生成调度触发记录与续做任务批次。

数据流：
    scheduler(待激活计划) ──扫描──> scheduler_triggers(去重触发记录)
                                        │
                                        ├─ 成功窗口 ──> 跳过，不再创建采集任务
                                        └─ 失败窗口 ──> retry_queue(重试条目)
                                                          └─> scheduler_resume_batches(续做任务批次)
                                                                  └─> crawl_task(续做采集任务)

批量扫描以 (计划, 窗口起始时间) 作为窗口唯一标识：一个窗口最多只有一条
调度触发记录。已成功的窗口在后续轮询中只做「已跳过」标记；失败窗口只
补建一次重试条目与续做任务批次；真正生成续做采集任务的操作统一收敛到
``resume_window`` 这一个入口。
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from app.store import store
from app.services.crawl_task import CrawlTaskService
from app.services.retry_queue import RetryQueueService

MODULE = "scheduler"
TRIGGER_STORE = "scheduler_triggers"
RESUME_STORE = "scheduler_resume_batches"
RETRY_MODULE = "retry_queue"
TASK_MODULE = "crawl_task"

# 触发记录状态
TRIGGER_SUCCESS = "成功"
TRIGGER_FAILURE = "失败"
TRIGGER_DEFERRED = "待触发"

# 扫描范围：决定刚到期的新窗口在本轮还是下一轮进入采集
SCOPE_INCLUDE_DUE = "include_due"
SCOPE_DEFER_DUE = "defer_due"
SCOPE_LABELS = {
    SCOPE_INCLUDE_DUE: "本轮纳入刚到期窗口",
    SCOPE_DEFER_DUE: "下一轮再纳入刚到期窗口",
}
SCOPES = tuple(SCOPE_LABELS)

# 窗口在页面上的分类
RESULT_NEW = "新触发"
RESULT_SKIPPED = "已跳过"
RESULT_PENDING = "待续做"
RESULT_RESUMED = "已续做"
RESULT_DEFERRED = "待下一轮"
RESULT_DUE = "待触发"
RESULT_FUTURE = "未到期"

DEFAULT_WINDOW_MINUTES = 60
MAX_HISTORY = 20
RETRY_TERMINAL = "已恢复"
RETRY_OPEN = {"排队中", "重试中", "已达上限"}

_TIME_FORMATS = (
    "%Y-%m-%d %H:%M:%S",
    "%Y-%m-%d %H:%M",
    "%Y-%m-%dT%H:%M:%S",
    "%Y-%m-%dT%H:%M",
    "%Y-%m-%d",
)


def parse_window_time(value: Any) -> datetime | None:
    """把计划里/接口传入的时间统一解析到分钟粒度。"""
    if isinstance(value, datetime):
        return value.replace(second=0, microsecond=0)
    text = str(value or "").strip()
    if not text:
        return None
    for fmt in _TIME_FORMATS:
        try:
            return datetime.strptime(text, fmt).replace(second=0, microsecond=0)
        except ValueError:
            continue
    return None


def format_window_time(value: datetime) -> str:
    return value.strftime("%Y-%m-%d %H:%M")


def window_key(plan_id: int, start: datetime) -> str:
    """窗口唯一键：同一计划的同一分钟只对应一个调度窗口。"""
    return f"{int(plan_id)}:{format_window_time(start)}"


class SchedulerEngine:
    def __init__(self) -> None:
        self._task_svc = CrawlTaskService()
        self._retry_svc = RetryQueueService()

    # ------------------------------------------------------------------
    # 基础读取与去重索引
    # ------------------------------------------------------------------
    def _next_trigger_id(self) -> int:
        rows = store.joint_rows(TRIGGER_STORE)
        return max((int(r.get("id", 0)) for r in rows), default=0) + 1

    def _next_batch_id(self) -> int:
        rows = store.joint_rows(RESUME_STORE)
        return max((int(r.get("id", 0)) for r in rows), default=0) + 1

    def _normalize_triggers(self) -> list[dict[str, Any]]:
        """兼容历史触发记录：补齐 window_start / window_key 后按窗口去重。"""
        triggers = store.joint_rows(TRIGGER_STORE)
        changed = False
        seen: dict[str, dict[str, Any]] = {}
        deduped: list[dict[str, Any]] = []
        for record in triggers:
            start_text = str(record.get("window_start") or "").strip()
            start_dt = parse_window_time(start_text) or parse_window_time(record.get("triggered_at"))
            if start_dt is None:
                start_dt = datetime.now().replace(second=0, microsecond=0)
            formatted = format_window_time(start_dt)
            if start_text != formatted:
                record["window_start"] = formatted
                changed = True
            key = str(record.get("window_key") or "").strip()
            if not key:
                key = window_key(int(record.get("plan_id", 0)), start_dt)
                record["window_key"] = key
                changed = True
            # 同一窗口只保留一条触发记录：优先保留已续做/成功的那条，避免重复记录
            existing = seen.get(key)
            if existing is None:
                seen[key] = record
                deduped.append(record)
            else:
                changed = True
                # 同一窗口出现重复触发记录：保留真实触发过的窗口，不丢失败痕迹
                keep, drop = self._pick_trigger(existing, record)
                if keep is drop:
                    continue
                index = deduped.index(existing)
                deduped[index] = keep
                seen[key] = keep
                self._merge_trigger_audit(keep, drop)
        if changed or len(deduped) != len(triggers):
            # 原地替换，保证后续 joint_append 与局部引用都是同一份列表
            triggers[:] = deduped
            store.joint_replace(TRIGGER_STORE, triggers)
        return triggers

    @staticmethod
    def _pick_trigger(left: dict[str, Any], right: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
        left_success = left.get("status") == TRIGGER_SUCCESS
        right_success = right.get("status") == TRIGGER_SUCCESS
        if left_success != right_success:
            return (left, right) if left_success else (right, left)
        return (left, right) if int(left.get("id", 0)) >= int(right.get("id", 0)) else (right, left)

    @staticmethod
    def _merge_trigger_audit(target: dict[str, Any], source: dict[str, Any]) -> None:
        events = list(source.get("events") or []) + list(target.get("events") or [])
        if events:
            target["events"] = events[-MAX_HISTORY:]
        if source.get("failure_reason") and not target.get("failure_reason"):
            target["failure_reason"] = source["failure_reason"]

    def _trigger_index(self, triggers: list[dict[str, Any]] | None = None) -> dict[str, dict[str, Any]]:
        rows = triggers if triggers is not None else self._normalize_triggers()
        return {str(row.get("window_key", "")): row for row in rows}

    def _retry_entry_for(self, key: str) -> dict[str, Any] | None:
        """按窗口找重试条目：优先仍处于开放状态的那条。"""
        matches = [row for row in store.rows(RETRY_MODULE) if str(row.get("window_key", "")) == key]
        for row in matches:
            if str(row.get("status", "")) in RETRY_OPEN:
                return row
        return matches[-1] if matches else None

    def _batch_for(self, key: str) -> dict[str, Any] | None:
        for row in store.joint_rows(RESUME_STORE):
            if str(row.get("window_key", "")) == key:
                return row
        return None

    def _plan_code(self, plan: dict[str, Any]) -> str:
        return str(plan.get("计划编号", "") or f"PLAN-{plan.get('id', '')}")

    def _window_interval(self, plan: dict[str, Any]) -> int:
        raw = str(plan.get("窗口间隔", "") or "").strip()
        if raw.isdigit() and int(raw) > 0:
            return int(raw)
        return DEFAULT_WINDOW_MINUTES

    def _candidate_start(self, plan: dict[str, Any], as_of: datetime) -> datetime:
        """计划当前待处理的窗口起点：优先「下次执行」，否则用稳定锚点。

        锚点会回写到计划上，保证连续两次扫描（或页面读取）拿到同一个窗口，
        不会因为跨分钟而漂移出重复窗口。
        """
        parsed = parse_window_time(plan.get("下次执行")) or parse_window_time(plan.get("窗口基准"))
        if parsed is not None:
            if str(plan.get("下次执行", "")) != format_window_time(parsed):
                plan["下次执行"] = format_window_time(parsed)
            return parsed
        anchor = as_of.replace(second=0, microsecond=0)
        plan["窗口基准"] = format_window_time(anchor)
        plan["下次执行"] = format_window_time(anchor)
        return anchor

    def _advance_plan(self, plan: dict[str, Any], start: datetime) -> None:
        interval = self._window_interval(plan)
        next_start = start + timedelta(minutes=interval)
        plan["上次执行"] = format_window_time(start)
        plan["下次执行"] = format_window_time(next_start)
        plan["窗口基准"] = format_window_time(next_start)

    # ------------------------------------------------------------------
    # 跨模块产物
    # ------------------------------------------------------------------
    def _create_task(
        self,
        plan: dict[str, Any],
        plan_id: int,
        start: datetime,
        *,
        purpose: str = "调度窗口",
        previous_task_id: int | None = None,
        attempt: int = 1,
    ) -> dict[str, Any] | None:
        suffix = start.strftime("%Y%m%d%H%M")
        task_number = f"TASK-{plan_id}-{suffix}"
        if purpose == "续做":
            task_number = f"{task_number}-R{attempt}"
        values = {
            "任务编号": task_number,
            "目标站点": str(plan.get("关联任务", "")),
            "入口URL": f"https://example.com/{plan_id}?window={suffix}",
            "深度限制": "3",
            "页面上限": "100",
            "调度cron": str(plan.get("Cron表达式", "")),
            "优先级": "5",
            "截止时间": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "调度窗口": format_window_time(start),
            "任务用途": purpose,
            "前序任务": str(previous_task_id or ""),
        }
        task_entry, _missing = self._task_svc.create_entry(values)
        return task_entry

    def _create_trigger(
        self,
        plan: dict[str, Any],
        plan_id: int,
        start: datetime,
        *,
        status: str,
        task_id: int | None,
        scan_at: str,
        failure_reason: str = "",
    ) -> dict[str, Any]:
        key = window_key(plan_id, start)
        result = RESULT_NEW if status == TRIGGER_SUCCESS else (
            RESULT_PENDING if status == TRIGGER_FAILURE else RESULT_DEFERRED
        )
        record: dict[str, Any] = {
            "id": self._next_trigger_id(),
            "plan_id": plan_id,
            "plan_code": self._plan_code(plan),
            "window_key": key,
            "window_start": format_window_time(start),
            "task_id": task_id,
            "status": status,
            "triggered_at": scan_at,
            "last_scan_result": result,
            "last_scanned_at": scan_at,
            "scan_history": [{"at": scan_at, "result": result}],
        }
        if failure_reason:
            record["failure_reason"] = failure_reason
        store.joint_append(TRIGGER_STORE, record)
        return record

    def _mark_scan(self, trigger: dict[str, Any], result: str, scan_at: str) -> None:
        trigger["last_scan_result"] = result
        trigger["last_scanned_at"] = scan_at
        history = list(trigger.get("scan_history") or [])
        history.append({"at": scan_at, "result": result})
        trigger["scan_history"] = history[-MAX_HISTORY:]

    def _ensure_retry_entry(self, plan: dict[str, Any], trigger: dict[str, Any]) -> dict[str, Any] | None:
        key = str(trigger.get("window_key", ""))
        existing = self._retry_entry_for(key)
        if existing is not None:
            return existing
        max_retry = str(plan.get("重试次数", "3") or "3")
        if not max_retry.isdigit():
            max_retry = "3"
        plan_id = int(plan["id"])
        start_text = str(trigger.get("window_start", ""))
        values = {
            "条目编号": f"RETRY-{plan_id}-{start_text.replace('-', '').replace(':', '').replace(' ', '')}",
            "失败页面": f"https://example.com/{plan_id}?window={start_text}",
            "失败原因": str(trigger.get("failure_reason") or "调度窗口执行失败"),
            "重试次数": "0",
            "最大重试": max_retry,
            "下次重试": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "错误详情": str(trigger.get("failure_reason") or "调度窗口执行失败，等待续做"),
            "关联任务": str(trigger.get("task_id") or ""),
            "计划编号": self._plan_code(plan),
            "窗口标识": key,
            "窗口起始": start_text,
            "触发记录": str(trigger.get("id", "")),
            "plan_id": plan_id,
            "window_key": key,
            "trigger_id": int(trigger.get("id", 0)),
        }
        entry, _missing = self._retry_svc.create_entry(values)
        if entry is None:
            return None
        # create_entry 已保存扩展字段，这里再兜底一次，保证按窗口可查
        entry["window_key"] = key
        entry["plan_id"] = plan_id
        entry["trigger_id"] = int(trigger.get("id", 0))
        return entry

    def _ensure_resume_batch(self, plan: dict[str, Any], trigger: dict[str, Any],
                             retry_entry: dict[str, Any] | None) -> dict[str, Any]:
        key = str(trigger.get("window_key", ""))
        existing = self._batch_for(key)
        if existing is not None:
            return existing
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        batch = {
            "id": self._next_batch_id(),
            "plan_id": int(trigger.get("plan_id", plan.get("id", 0))),
            "plan_code": self._plan_code(plan),
            "window_key": key,
            "window_start": str(trigger.get("window_start", "")),
            "trigger_id": int(trigger.get("id", 0)),
            "failed_task_id": trigger.get("task_id"),
            "retry_entry_id": retry_entry.get("id") if retry_entry else None,
            "task_id": None,
            "status": "待续做",
            "attempts": 0,
            "created_at": now,
            "updated_at": now,
            "note": "批量扫描发现失败窗口，等待唯一续做入口处理",
        }
        store.joint_append(RESUME_STORE, batch)
        return batch

    @staticmethod
    def _task_by_id(task_id: Any) -> dict[str, Any] | None:
        if task_id in (None, ""):
            return None
        return store.find(TASK_MODULE, int(task_id))

    # ------------------------------------------------------------------
    # 窗口执行（扫描内部使用）
    # ------------------------------------------------------------------
    def _execute_window(
        self,
        plan: dict[str, Any],
        start: datetime,
        scan_at: str,
        *,
        simulate_failure: bool,
        trigger: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        plan_id = int(plan["id"])
        key = window_key(plan_id, start)
        result = self._create_task(plan, plan_id, start)
        if result is None:
            return {
                "ok": False,
                "error": f"调度计划 {plan_id} 的窗口 {format_window_time(start)} 任务创建失败",
                "window_key": key,
            }
        task_entry = result
        status = TRIGGER_FAILURE if simulate_failure else TRIGGER_SUCCESS
        reason = "模拟调度失败：连接超时" if simulate_failure else ""

        if trigger is None:
            trigger = self._create_trigger(
                plan, plan_id, start,
                status=status, task_id=int(task_entry["id"]), scan_at=scan_at,
                failure_reason=reason,
            )
        else:
            # 之前被下一轮范围推迟的窗口，本轮正式触发：更新同一条记录
            trigger["status"] = status
            trigger["task_id"] = int(task_entry["id"])
            trigger["triggered_at"] = scan_at
            trigger["failure_reason"] = reason
            trigger["last_scan_result"] = RESULT_NEW if status == TRIGGER_SUCCESS else RESULT_PENDING
            trigger["last_scanned_at"] = scan_at
            history = list(trigger.get("scan_history") or [])
            history.append({"at": scan_at, "result": trigger["last_scan_result"]})
            trigger["scan_history"] = history[-MAX_HISTORY:]

        self._advance_plan(plan, start)

        if simulate_failure:
            plan["pending"] = True
            plan["abnormal"] = True
            retry_entry = self._ensure_retry_entry(plan, trigger)
            batch = self._ensure_resume_batch(plan, trigger, retry_entry)
            return {
                "ok": False,
                "error": "模拟失败：失败窗口已进入重试队列并生成待续做批次",
                "window_key": key,
                "classification": RESULT_PENDING,
                "trigger": trigger,
                "task": task_entry,
                "retry_entry": retry_entry,
                "resume_batch": batch,
            }

        plan["status"] = "运行中"
        plan["pending"] = True
        plan["abnormal"] = False
        return {
            "ok": True,
            "window_key": key,
            "classification": RESULT_NEW,
            "trigger": trigger,
            "task": task_entry,
        }

    # ------------------------------------------------------------------
    # 批量扫描
    # ------------------------------------------------------------------
    def _candidate_plans(self, triggers: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """需要扫描的计划：待激活/运行中的计划，加上仍有未了结失败窗口的计划。

        已停用、已完成的计划不再参与扫描；但只要还有失败窗口没有续做，
        即使计划状态被其他动作改掉也仍要进入扫描，保证失败入口不丢。
        """
        unresolved: set[int] = set()
        for trigger in triggers:
            if trigger.get("status") != TRIGGER_FAILURE:
                continue
            key = str(trigger.get("window_key", ""))
            batch = self._batch_for(key)
            retry = self._retry_entry_for(key)
            if batch is not None and batch.get("status") == "已完成":
                continue
            if retry is not None and retry.get("status") == RETRY_TERMINAL:
                continue
            unresolved.add(int(trigger.get("plan_id", 0)))
        active = {"待激活", "运行中"}
        plans: list[dict[str, Any]] = []
        for plan in store.rows(MODULE):
            if plan.get("status") in active or int(plan.get("id", 0)) in unresolved:
                plans.append(plan)
        return plans

    def scan_windows(
        self,
        scope: str = SCOPE_INCLUDE_DUE,
        as_of: Any = None,
        plan_ids: list[int] | None = None,
        simulate_failure: bool = False,
    ) -> dict[str, Any]:
        """批量扫描调度窗口：成功跳过、失败续做、到期新触发、范围外推迟。"""
        if scope not in SCOPES:
            return {"ok": False, "error": f"未知扫描范围：{scope}", "scopes": list(SCOPES)}
        as_of_dt = parse_window_time(as_of) or datetime.now().replace(second=0, microsecond=0)
        scan_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        triggers = self._normalize_triggers()
        trigger_map = self._trigger_index(triggers)
        candidates = self._candidate_plans(triggers)
        if plan_ids:
            wanted = {int(item) for item in plan_ids}
            candidates = [p for p in candidates if int(p.get("id", 0)) in wanted]

        summary = {
            RESULT_NEW: 0,
            RESULT_SKIPPED: 0,
            RESULT_PENDING: 0,
            RESULT_RESUMED: 0,
            RESULT_DEFERRED: 0,
            RESULT_FUTURE: 0,
        }
        results: list[dict[str, Any]] = []

        for plan in candidates:
            plan_id = int(plan["id"])
            plan_code = self._plan_code(plan)
            history = sorted(
                [t for t in triggers if int(t.get("plan_id", 0)) == plan_id],
                key=lambda item: str(item.get("window_start", "")),
            )
            for trigger in history:
                key = str(trigger.get("window_key", ""))
                start_dt = parse_window_time(trigger.get("window_start"))
                status = trigger.get("status")
                entry: dict[str, Any] = {
                    "plan_id": plan_id,
                    "plan_code": plan_code,
                    "window_key": key,
                    "window_start": trigger.get("window_start"),
                    "trigger_id": trigger.get("id"),
                    "trigger_status": status,
                    "task_id": trigger.get("task_id"),
                }
                if status == TRIGGER_SUCCESS:
                    self._mark_scan(trigger, RESULT_SKIPPED, scan_at)
                    summary[RESULT_SKIPPED] += 1
                    entry["classification"] = RESULT_SKIPPED
                    entry["message"] = "成功窗口已跳过，不重复创建采集任务"
                elif status == TRIGGER_FAILURE:
                    batch = self._batch_for(key)
                    if batch is not None and batch.get("status") == "已完成":
                        self._mark_scan(trigger, RESULT_RESUMED, scan_at)
                        summary[RESULT_RESUMED] += 1
                        entry["classification"] = RESULT_RESUMED
                        entry["resume_batch_id"] = batch.get("id")
                        entry["resume_task_id"] = batch.get("task_id")
                        entry["message"] = "失败窗口已续做完成，不重复创建任务"
                    else:
                        retry_entry = self._ensure_retry_entry(plan, trigger)
                        batch = self._ensure_resume_batch(plan, trigger, retry_entry)
                        self._mark_scan(trigger, RESULT_PENDING, scan_at)
                        summary[RESULT_PENDING] += 1
                        entry["classification"] = RESULT_PENDING
                        entry["retry_entry_id"] = retry_entry.get("id") if retry_entry else None
                        entry["resume_batch_id"] = batch.get("id")
                        entry["message"] = "失败窗口保留重试条目，等待唯一续做入口"
                elif status == TRIGGER_DEFERRED:
                    if start_dt is not None and start_dt <= as_of_dt and scope == SCOPE_INCLUDE_DUE:
                        outcome = self._execute_window(
                            plan, start_dt, scan_at,
                            simulate_failure=simulate_failure, trigger=trigger,
                        )
                        classification = outcome.get("classification", RESULT_NEW)
                        summary[classification] = summary.get(classification, 0) + 1
                        entry["classification"] = classification
                        entry["trigger_status"] = trigger.get("status")
                        entry["task_id"] = trigger.get("task_id")
                        entry["message"] = outcome.get("error", "到期窗口本轮进入采集")
                    else:
                        self._mark_scan(trigger, RESULT_DEFERRED, scan_at)
                        summary[RESULT_DEFERRED] += 1
                        entry["classification"] = RESULT_DEFERRED
                        entry["message"] = "到期窗口按扫描范围推迟到下一轮"
                else:
                    continue
                results.append(entry)

            # 当前候选窗口（同一计划同一轮只处理一个未建记录的窗口）
            start = self._candidate_start(plan, as_of_dt)
            key = window_key(plan_id, start)
            while key in trigger_map:
                start = start + timedelta(minutes=self._window_interval(plan))
                key = window_key(plan_id, start)
            if start > as_of_dt:
                summary[RESULT_FUTURE] += 1
                results.append({
                    "plan_id": plan_id,
                    "plan_code": plan_code,
                    "window_key": key,
                    "window_start": format_window_time(start),
                    "classification": RESULT_FUTURE,
                    "message": "窗口未到期，本轮不触发",
                })
                continue

            if scope == SCOPE_DEFER_DUE:
                trigger = self._create_trigger(
                    plan, plan_id, start,
                    status=TRIGGER_DEFERRED, task_id=None, scan_at=scan_at,
                )
                # 推迟时固定住窗口起点，下一轮仍是同一个窗口
                plan["窗口基准"] = format_window_time(start)
                plan["下次执行"] = plan["窗口基准"]
                trigger_map[key] = trigger
                summary[RESULT_DEFERRED] += 1
                results.append({
                    "plan_id": plan_id,
                    "plan_code": plan_code,
                    "window_key": key,
                    "window_start": format_window_time(start),
                    "trigger_id": trigger["id"],
                    "trigger_status": TRIGGER_DEFERRED,
                    "classification": RESULT_DEFERRED,
                    "message": "刚到期窗口按扫描范围推迟到下一轮",
                })
                continue

            outcome = self._execute_window(plan, start, scan_at, simulate_failure=simulate_failure)
            classification = outcome.get("classification", RESULT_NEW)
            summary[classification] = summary.get(classification, 0) + 1
            trigger = outcome.get("trigger") or {}
            trigger_map[key] = trigger
            results.append({
                "plan_id": plan_id,
                "plan_code": plan_code,
                "window_key": key,
                "window_start": format_window_time(start),
                "trigger_id": trigger.get("id"),
                "trigger_status": trigger.get("status"),
                "task_id": trigger.get("task_id"),
                "retry_entry_id": (outcome.get("retry_entry") or {}).get("id"),
                "resume_batch_id": (outcome.get("resume_batch") or {}).get("id"),
                "classification": classification,
                "message": outcome.get("error") or "到期窗口本轮进入采集",
            })

        store.joint_replace(TRIGGER_STORE, triggers)
        return {
            "ok": True,
            "scope": scope,
            "scope_label": SCOPE_LABELS[scope],
            "as_of": format_window_time(as_of_dt),
            "scanned": len(candidates),
            # 兼容旧轮询接口的字段：本轮真正新建采集任务的窗口数
            "triggered": summary[RESULT_NEW],
            "summary": summary,
            "results": results,
        }

    def tick_all(
        self,
        scope: str = SCOPE_INCLUDE_DUE,
        as_of: Any = None,
        plan_ids: list[int] | None = None,
        simulate_failure: bool = False,
    ) -> dict[str, Any]:
        """兼容旧入口：轮询待激活计划，实际走同一套窗口扫描。"""
        return self.scan_windows(scope=scope, as_of=as_of, plan_ids=plan_ids,
                                 simulate_failure=simulate_failure)

    # ------------------------------------------------------------------
    # 单计划手动触发（同样按窗口去重）
    # ------------------------------------------------------------------
    def trigger_plan(
        self,
        plan_id: int,
        *,
        simulate_failure: bool = False,
        window_start: Any = None,
    ) -> dict[str, Any]:
        plan = store.find(MODULE, plan_id)
        if plan is None:
            return {"ok": False, "error": f"调度计划 {plan_id} 不存在"}

        as_of = datetime.now().replace(second=0, microsecond=0)
        start = parse_window_time(window_start) or self._candidate_start(plan, as_of)
        key = window_key(plan_id, start)
        triggers = self._normalize_triggers()
        existing = self._trigger_index(triggers).get(key)
        scan_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        if existing is not None:
            status = existing.get("status")
            if status == TRIGGER_SUCCESS:
                return {
                    "ok": True,
                    "skipped": True,
                    "message": "该窗口已成功触发，跳过重复创建",
                    "window_key": key,
                    "trigger": existing,
                    "task": self._task_by_id(existing.get("task_id")),
                }
            if status == TRIGGER_FAILURE:
                batch = self._batch_for(key)
                if batch is not None and batch.get("status") == "已完成":
                    return {
                        "ok": True,
                        "skipped": True,
                        "message": "该失败窗口已续做完成，跳过重复创建",
                        "window_key": key,
                        "trigger": existing,
                        "task": self._task_by_id(batch.get("task_id")),
                    }
                retry_entry = self._ensure_retry_entry(plan, existing)
                batch = self._ensure_resume_batch(plan, existing, retry_entry)
                return {
                    "ok": False,
                    "error": "该窗口已失败，失败入口保留在重试队列，请走续做入口",
                    "window_key": key,
                    "trigger": existing,
                    "retry_entry": retry_entry,
                    "resume_batch": batch,
                }
            if status == TRIGGER_DEFERRED:
                outcome = self._execute_window(
                    plan, start, scan_at,
                    simulate_failure=simulate_failure, trigger=existing,
                )
                store.joint_replace(TRIGGER_STORE, triggers)
                return outcome

        outcome = self._execute_window(plan, start, scan_at, simulate_failure=simulate_failure)
        store.joint_replace(TRIGGER_STORE, triggers)
        return outcome

    # ------------------------------------------------------------------
    # 唯一续做入口
    # ------------------------------------------------------------------
    def resume_window(self, trigger_id: int, note: str = "") -> dict[str, Any]:
        """失败窗口的唯一续做入口：生成续做任务批次，不覆盖任何已完成任务。"""
        triggers = self._normalize_triggers()
        trigger = next((row for row in triggers if int(row.get("id", 0)) == int(trigger_id)), None)
        if trigger is None:
            return {"ok": False, "error": f"调度触发记录 {trigger_id} 不存在"}
        if trigger.get("status") == TRIGGER_SUCCESS:
            return {
                "ok": True,
                "skipped": True,
                "message": "成功窗口无需续做，也不会再次创建采集任务",
                "trigger": trigger,
            }
        if trigger.get("status") != TRIGGER_FAILURE:
            return {"ok": False, "error": "只有失败窗口可以续做"}

        key = str(trigger.get("window_key", ""))
        batch = self._batch_for(key)
        if batch is not None and batch.get("status") == "已完成":
            return {
                "ok": True,
                "skipped": True,
                "message": "该窗口已续做完成，不重复创建任务",
                "trigger": trigger,
                "resume_batch": batch,
                "task": self._task_by_id(batch.get("task_id")),
            }

        retry_entry = self._retry_entry_for(key)
        if retry_entry is not None and retry_entry.get("status") == RETRY_TERMINAL:
            # 上一轮已恢复：不要覆盖上一轮已完成任务
            if batch is not None:
                batch["status"] = "已完成"
                batch["updated_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                store.joint_replace(RESUME_STORE, store.joint_rows(RESUME_STORE))
            return {
                "ok": True,
                "skipped": True,
                "message": "重试条目上一轮已恢复，未覆盖已完成任务",
                "trigger": trigger,
                "retry_entry": retry_entry,
                "resume_batch": batch,
            }

        plan = store.find(MODULE, int(trigger.get("plan_id", 0)))
        if plan is None:
            return {"ok": False, "error": f"调度计划 {trigger.get('plan_id')} 不存在"}
        start = parse_window_time(trigger.get("window_start")) or datetime.now().replace(second=0, microsecond=0)
        if batch is None:
            batch = self._ensure_resume_batch(plan, trigger, retry_entry)
        attempt = int(batch.get("attempts", 0)) + 1
        task_entry = self._create_task(
            plan, int(plan["id"]), start,
            purpose="续做",
            previous_task_id=trigger.get("task_id"),
            attempt=attempt,
        )
        if task_entry is None:
            return {"ok": False, "error": "续做任务批次创建失败"}

        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        batch["status"] = "已完成"
        batch["task_id"] = int(task_entry["id"])
        batch["attempts"] = attempt
        batch["updated_at"] = now
        batch["note"] = note or "已通过唯一续做入口生成续做任务批次"
        store.joint_replace(RESUME_STORE, store.joint_rows(RESUME_STORE))

        if retry_entry is not None:
            try:
                retries = int(str(retry_entry.get("重试次数", "0")))
            except ValueError:
                retries = 0
            retry_entry["重试次数"] = str(retries + 1)
            retry_entry["status"] = RETRY_TERMINAL
            retry_entry["pending"] = False
            retry_entry["abnormal"] = False
            retry_entry["下次重试"] = now
            retry_entry["最后重试"] = now
            retry_entry["恢复任务"] = str(task_entry["id"])
            retry_entry["window_key"] = key

        trigger["resolved"] = True
        trigger["resume_batch_id"] = batch["id"]
        trigger["resume_task_id"] = task_entry["id"]
        trigger["resume_attempts"] = attempt
        trigger["resumed_at"] = now
        trigger["last_scan_result"] = RESULT_RESUMED
        trigger["last_scanned_at"] = now
        events = list(trigger.get("events") or [])
        events.append({"at": now, "event": "续做", "task_id": task_entry["id"], "batch_id": batch["id"]})
        trigger["events"] = events[-MAX_HISTORY:]
        store.joint_replace(TRIGGER_STORE, triggers)

        return {
            "ok": True,
            "message": "失败窗口已生成续做任务批次，原失败记录与已完成任务均保留",
            "trigger": trigger,
            "retry_entry": retry_entry,
            "resume_batch": batch,
            "task": task_entry,
        }

    # ------------------------------------------------------------------
    # 查询
    # ------------------------------------------------------------------
    def list_triggers(self) -> list[dict[str, Any]]:
        return list(self._normalize_triggers())

    def get_trigger(self, trigger_id: int) -> dict[str, Any] | None:
        self._normalize_triggers()
        return store.joint_find(TRIGGER_STORE, trigger_id)

    def list_resume_batches(self) -> list[dict[str, Any]]:
        return list(store.joint_rows(RESUME_STORE))

    def get_resume_batch(self, batch_id: int) -> dict[str, Any] | None:
        return store.joint_find(RESUME_STORE, batch_id)

    def list_windows(self, as_of: Any = None) -> dict[str, Any]:
        """返回触发记录 + 续做批次合并后的窗口口径，供跨模块页面同步。"""
        as_of_dt = parse_window_time(as_of) or datetime.now().replace(second=0, microsecond=0)
        triggers = self._normalize_triggers()
        items: list[dict[str, Any]] = []
        seen: set[str] = set()
        for trigger in sorted(triggers, key=lambda row: (int(row.get("plan_id", 0)), str(row.get("window_start", "")))):
            key = str(trigger.get("window_key", ""))
            if key in seen:
                continue
            seen.add(key)
            plan = store.find(MODULE, int(trigger.get("plan_id", 0)))
            status = trigger.get("status")
            batch = self._batch_for(key)
            retry_entry = self._retry_entry_for(key)
            if status == TRIGGER_SUCCESS:
                classification = RESULT_SKIPPED
            elif status == TRIGGER_FAILURE:
                if batch is not None and batch.get("status") == "已完成":
                    classification = RESULT_RESUMED
                else:
                    classification = RESULT_PENDING
            elif status == TRIGGER_DEFERRED:
                start = parse_window_time(trigger.get("window_start"))
                classification = RESULT_DUE if start is not None and start <= as_of_dt else RESULT_DEFERRED
            else:
                classification = str(trigger.get("last_scan_result") or RESULT_FUTURE)
            items.append({
                "plan_id": int(trigger.get("plan_id", 0)),
                "plan_code": str(trigger.get("plan_code") or (self._plan_code(plan) if plan else "")),
                "window_key": key,
                "window_start": trigger.get("window_start"),
                "classification": classification,
                "last_scan_result": trigger.get("last_scan_result"),
                "last_scanned_at": trigger.get("last_scanned_at"),
                "trigger_id": trigger.get("id"),
                "trigger_status": status,
                "task_id": trigger.get("task_id"),
                "retry_entry_id": retry_entry.get("id") if retry_entry else None,
                "retry_status": retry_entry.get("status") if retry_entry else None,
                "resume_batch_id": batch.get("id") if batch else None,
                "resume_status": batch.get("status") if batch else None,
                "resume_task_id": batch.get("task_id") if batch else None,
            })

        # 计划当前待处理窗口（尚无触发记录）
        for plan in self._candidate_plans(triggers):
            start = self._candidate_start(plan, as_of_dt)
            key = window_key(int(plan["id"]), start)
            if key in seen:
                continue
            seen.add(key)
            items.append({
                "plan_id": int(plan["id"]),
                "plan_code": self._plan_code(plan),
                "window_key": key,
                "window_start": format_window_time(start),
                "classification": RESULT_DUE if start <= as_of_dt else RESULT_FUTURE,
                "last_scan_result": "",
                "last_scanned_at": "",
                "trigger_id": None,
                "trigger_status": "",
                "task_id": None,
                "retry_entry_id": None,
                "retry_status": None,
                "resume_batch_id": None,
                "resume_status": None,
                "resume_task_id": None,
            })
        items.sort(key=lambda row: (row["plan_id"], str(row["window_start"])))
        summary: dict[str, int] = {}
        for item in items:
            summary[item["classification"]] = summary.get(item["classification"], 0) + 1
        return {
            "items": items,
            "summary": summary,
            "scopes": [{"value": value, "label": label} for value, label in SCOPE_LABELS.items()],
            "as_of": format_window_time(as_of_dt),
        }


scheduler_engine = SchedulerEngine()
