"""调度引擎：定时调度触发采集任务，失败任务进入重试队列。

数据流：scheduler -> crawl_task -> retry_queue
"""
from __future__ import annotations

import time
from typing import Any

from app.store import store
from app.services.crawl_task import CrawlTaskService
from app.services.retry_queue import RetryQueueService

MODULE = "scheduler"


class SchedulerEngine:
    def __init__(self) -> None:
        self._task_svc = CrawlTaskService()
        self._retry_svc = RetryQueueService()

    def _next_trigger_id(self) -> int:
        rows = store.joint_rows("scheduler_triggers")
        return max((int(r.get("id", 0)) for r in rows), default=0) + 1

    def trigger_plan(self, plan_id: int, *, simulate_failure: bool = False) -> dict[str, Any]:
        """触发单个调度计划，生成采集任务；失败时写入重试队列。"""
        plan = store.find(MODULE, plan_id)
        if plan is None:
            return {"ok": False, "error": f"调度计划 {plan_id} 不存在"}

        # 生成采集任务（跨模块数据产物）
        task_values = {
            "任务编号": f"TASK-{plan_id}-{int(time.time())}",
            "目标站点": str(plan.get("关联任务", "")),
            "入口URL": f"https://example.com/{plan_id}",
            "深度限制": "3",
            "页面上限": "100",
            "调度cron": str(plan.get("Cron表达式", "")),
            "优先级": "5",
            "截止时间": time.strftime("%Y-%m-%d %H:%M:%S"),
        }
        task_entry, missing = self._task_svc.create_entry(task_values)
        if task_entry is None:
            return {"ok": False, "error": f"任务创建失败：缺少 {missing}"}

        # 记录调度触发（联合存储）
        trigger_record = {
            "id": self._next_trigger_id(),
            "plan_id": plan_id,
            "task_id": task_entry["id"],
            "status": "失败" if simulate_failure else "成功",
            "triggered_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        }
        store.joint_append("scheduler_triggers", trigger_record)

        if simulate_failure:
            # 失败任务进入重试队列（跨模块数据产物）
            retry_values = {
                "条目编号": f"RETRY-{task_entry['id']}",
                "失败页面": str(task_values["入口URL"]),
                "失败原因": "模拟调度失败：连接超时",
                "重试次数": "0",
                "最大重试": str(plan.get("重试次数", "3")),
                "下次重试": time.strftime("%Y-%m-%d %H:%M:%S"),
                "错误详情": "连接超时，等待重试",
                "关联任务": str(task_entry["id"]),
            }
            retry_entry, retry_missing = self._retry_svc.create_entry(retry_values)
            return {
                "ok": False,
                "error": "模拟失败：已写入重试队列",
                "trigger": trigger_record,
                "task": task_entry,
                "retry_entry": retry_entry,
            }

        # 更新调度计划状态
        plan["status"] = "运行中"
        plan["pending"] = True
        return {
            "ok": True,
            "trigger": trigger_record,
            "task": task_entry,
        }

    def tick_all(self) -> dict[str, Any]:
        """轮询所有待激活调度计划并触发。"""
        rows = store.rows(MODULE)
        pending = [r for r in rows if r.get("status") == "待激活"]
        results: list[dict[str, Any]] = []
        for plan in pending:
            res = self.trigger_plan(int(plan["id"]))
            results.append(res)
        return {"ok": True, "triggered": len(results), "results": results}

    def list_triggers(self) -> list[dict[str, Any]]:
        return list(store.joint_rows("scheduler_triggers"))

    def get_trigger(self, trigger_id: int) -> dict[str, Any] | None:
        return store.joint_find("scheduler_triggers", trigger_id)


scheduler_engine = SchedulerEngine()
