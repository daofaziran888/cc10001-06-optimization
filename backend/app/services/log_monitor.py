"""采集监控 分析看板服务：汇总指标、运行分析并生成模拟结果。"""
from __future__ import annotations

import random
from typing import Any

from app.store import store

MODULE = "log_monitor"
REQUIRED_FIELDS = ["事件编号", "事件类型", "严重级别"]
STATUS_ORDER = ["待确认", "处理中", "已解决", "已忽略"]
ACTION_RULES = {"确认事件": "处理中", "开始处理": "已解决", "标记解决": "已忽略"}
NEGATIVE_ACTIONS = []


class LogMonitorService:
    def list_results(self) -> list[dict[str, Any]]:
        rows = store.rows(MODULE)
        results: list[dict] = []
        for row in rows:
            d = dict(row)
            d["指标值"] = round(random.uniform(0.65, 0.98), 3)
            d["对比基准"] = round(random.uniform(0.60, 0.92), 3)
            d["差异"] = round(d["指标值"] - d["对比基准"], 3)
            results.append(d)
        return results

    def run_analysis(self, params: dict[str, Any]) -> list[dict[str, Any]]:
        count = int(params.get("样本范围", params.get("并行数量", "6")))
        results: list[dict] = []
        for i in range(count):
            results.append({
                "id": i + 1,
                "分组": f"分组{(i%3)+1}",
                "指标值": round(random.uniform(0.62, 1.02), 3),
                "对比基准": round(random.uniform(0.58, 0.95), 3),
                "差异": round(random.uniform(-0.2, 0.3), 3),
            })
        return results

    def get_entry(self, entry_id: int) -> dict[str, Any] | None:
        return store.find(MODULE, entry_id)
