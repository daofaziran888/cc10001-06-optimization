"""重试队列 时间线服务：生成作业时间序列和示例数据。"""
from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from app.store import store

MODULE = "retry_queue"
REQUIRED_FIELDS = ["条目编号", "失败页面", "失败原因"]
# 跨模块数据流需要的可追溯字段：关联的调度计划、窗口、触发记录
OPTIONAL_FIELDS = ["重试次数", "最大重试", "下次重试", "错误详情", "关联任务", "计划编号", "窗口标识", "窗口起始", "触发记录"]
STATUS_ORDER = ["排队中", "重试中", "已达上限", "已恢复"]
ACTION_RULES = {"强制重试": "重试中", "标记放弃": "已达上限", "确认恢复": "已恢复"}
NEGATIVE_ACTIONS = []


class RetryQueueService:
    def get_timeline(self) -> list[dict[str, Any]]:
        rows = store.rows(MODULE)
        today = date.today()
        items: list[dict] = []
        for i, row in enumerate(rows):
            start = (today - timedelta(days=7 - i * 2)).isoformat()
            end = (today + timedelta(days=3 - i)).isoformat()
            items.append({
                "id": int(row.get("id", i + 1)),
                "name": str(row.get(list(row.keys())[1] if len(row) > 1 else "name", "")),
                "start": start,
                "end": end,
                "status": str(row.get("status", STATUS_ORDER[i % len(STATUS_ORDER)])),
                "logs": f"[{start}] 作业启动\n[{start}] 正在处理...\n[{end}] 任务{'完成' if row.get('status') == STATUS_ORDER[-1] else '进行中'}",
            })
        return items

    def get_entry(self, entry_id: int) -> dict[str, Any] | None:
        return store.find(MODULE, entry_id)

    def get_entries(self) -> list[dict[str, Any]]:
        """返回全部重试条目（含调度窗口扩展字段），供跨模块视图筛选。"""
        return [dict(row) for row in store.rows(MODULE)]

    def open_statuses(self) -> set[str]:
        """仍可继续重试的状态集合（已恢复为终态）。"""
        return {status for status in STATUS_ORDER if status != "已恢复"}

    def create_entry(self, values: dict[str, Any]) -> tuple[dict[str, Any] | None, list[str]]:
        missing = [f for f in REQUIRED_FIELDS if not str(values.get(f) or "").strip()]
        if missing:
            return None, missing
        rows = store.rows(MODULE)
        entry = {"id": max((int(r.get("id", 0)) for r in rows), default=0) + 1}
        entry.update({f: values.get(f) for f in REQUIRED_FIELDS})
        for field in OPTIONAL_FIELDS:
            if values.get(field) not in (None, ""):
                entry[field] = values.get(field)
        entry["status"] = STATUS_ORDER[0]
        entry["pending"] = True
        entry["abnormal"] = False
        rows.append(entry)
        return entry, []

    def run_action(self, entry_id: int, action: str) -> tuple[dict[str, Any] | None, str]:
        entry = store.find(MODULE, entry_id)
        if entry is None:
            return None, f"重试条目 {entry_id} 不存在或已归档"
        if action not in ACTION_RULES:
            return None, f"动作「{action}」不属于重试队列可执行范围"
        target = ACTION_RULES[action]
        entry["status"] = target
        entry["pending"] = target != STATUS_ORDER[-1]
        entry["abnormal"] = action in NEGATIVE_ACTIONS
        return entry, f"重试条目已{action}"
