"""代理路由器：为采集任务从代理池中获取可用节点。

数据流：proxy_pool -> crawl_task
"""
from __future__ import annotations

import time
from typing import Any

from app.store import store

PROXY_MODULE = "proxy_pool"
TASK_MODULE = "crawl_task"


class ProxyRouter:
    def __init__(self) -> None:
        pass

    def _next_assign_id(self) -> int:
        rows = store.joint_rows("proxy_assignments")
        return max((int(r.get("id", 0)) for r in rows), default=0) + 1

    def health_check_all(self) -> dict[str, Any]:
        """执行代理池健康检查，将延迟过高的节点降级。"""
        rows = store.rows(PROXY_MODULE)
        checked = 0
        degraded = 0
        for node in rows:
            if node.get("status") == "已下线":
                continue
            delay_str = str(node.get("响应延迟", "0") or "0")
            try:
                delay = float(delay_str)
            except (ValueError, TypeError):
                delay = 300.0
            checked += 1
            if delay > 500:
                node["status"] = "降级"
                node["abnormal"] = True
                degraded += 1
            elif delay <= 200:
                node["status"] = "健康"
                node["abnormal"] = False
        return {"ok": True, "checked": checked, "degraded": degraded}

    def route_for_task(self, task_id: int) -> dict[str, Any]:
        """为指定采集任务分配最优代理节点。"""
        task = store.find(TASK_MODULE, task_id)
        if task is None:
            return {"ok": False, "error": f"采集任务 {task_id} 不存在"}

        # 选取健康节点中成功率最高的
        nodes = store.rows(PROXY_MODULE)
        healthy = [n for n in nodes if n.get("status") == "健康"]
        if not healthy:
            return {"ok": False, "error": "无可用健康代理节点"}

        best = max(healthy, key=lambda n: float(str(n.get("成功率", "0") or "0")))

        assignment = {
            "id": self._next_assign_id(),
            "task_id": task_id,
            "proxy_id": best["id"],
            "proxy_node": str(best.get("节点编号", "")),
            "assigned_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        }
        store.joint_append("proxy_assignments", assignment)

        # 回写任务引用代理
        task["代理节点"] = str(best.get("节点编号", ""))
        return {
            "ok": True,
            "assignment": assignment,
            "proxy": best,
        }

    def list_assignments(self) -> list[dict[str, Any]]:
        return list(store.joint_rows("proxy_assignments"))

    def get_assignment(self, assign_id: int) -> dict[str, Any] | None:
        return store.joint_find("proxy_assignments", assign_id)


proxy_router = ProxyRouter()
