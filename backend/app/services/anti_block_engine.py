"""反爬引擎：反爬触发后自动轮换凭证管理中的会话凭证。

数据流：anti_block -> cookie_vault
"""
from __future__ import annotations

import time
from typing import Any

from app.store import store

ANTI_MODULE = "anti_block"
COOKIE_MODULE = "cookie_vault"


class AntiBlockEngine:
    def __init__(self) -> None:
        pass

    def _next_rotation_id(self) -> int:
        rows = store.joint_rows("cookie_rotations")
        return max((int(r.get("id", 0)) for r in rows), default=0) + 1

    def evaluate_and_rotate(self, strategy_id: int) -> dict[str, Any]:
        """评估反爬策略触发情况，执行凭证轮换。"""
        strategy = store.find(ANTI_MODULE, strategy_id)
        if strategy is None:
            return {"ok": False, "error": f"反爬策略 {strategy_id} 不存在"}

        # 模拟触发判断：成功率低于阈值则触发轮换
        success_rate = 40.0 + float(int(strategy["id"])) * 10
        triggered = success_rate < 50

        rotated: list[dict[str, Any]] = []
        if triggered:
            # 查找目标站点关联的凭证并轮换
            target_site = str(strategy.get("目标站点", ""))
            cookies = store.rows(COOKIE_MODULE)
            for cookie in cookies:
                if target_site in str(cookie.get("关联站点", "")):
                    old_status = str(cookie.get("status", ""))
                    # 轮换：将当前有效凭证标记为即将过期，寻找下一个有效凭证
                    if old_status == "有效":
                        cookie["status"] = "即将过期"
                        cookie["最后验证"] = time.strftime("%Y-%m-%d %H:%M:%S")
                        rotation = {
                            "id": self._next_rotation_id(),
                            "strategy_id": strategy_id,
                            "cookie_id": cookie["id"],
                            "old_status": old_status,
                            "new_status": "即将过期",
                            "rotated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
                        }
                        store.joint_append("cookie_rotations", rotation)
                        rotated.append(rotation)

            # 尝试启用一条未验证凭证作为替代
            for cookie in cookies:
                if target_site in str(cookie.get("关联站点", "")) and cookie.get("status") == "未验证":
                    cookie["status"] = "有效"
                    cookie["最后验证"] = time.strftime("%Y-%m-%d %H:%M:%S")
                    replacement = {
                        "id": self._next_rotation_id(),
                        "strategy_id": strategy_id,
                        "cookie_id": cookie["id"],
                        "old_status": "未验证",
                        "new_status": "有效",
                        "rotated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
                    }
                    store.joint_append("cookie_rotations", replacement)
                    rotated.append(replacement)
                    break

            strategy["status"] = "运行中"
            strategy["备注"] = f"于 {time.strftime('%Y-%m-%d %H:%M:%S')} 触发凭证轮换"

        return {
            "ok": True,
            "triggered": triggered,
            "success_rate": success_rate,
            "rotated": rotated,
        }

    def rotate_all(self) -> dict[str, Any]:
        """对所有运行中的反爬策略执行评估与轮换。"""
        strategies = [s for s in store.rows(ANTI_MODULE) if s.get("status") == "运行中"]
        results: list[dict[str, Any]] = []
        for st in strategies:
            res = self.evaluate_and_rotate(int(st["id"]))
            results.append(res)
        total_rotated = sum(len(r.get("rotated", [])) for r in results)
        return {"ok": True, "evaluated": len(results), "total_rotated": total_rotated, "results": results}

    def list_rotations(self) -> list[dict[str, Any]]:
        return list(store.joint_rows("cookie_rotations"))

    def get_rotation(self, rotation_id: int) -> dict[str, Any] | None:
        return store.joint_find("cookie_rotations", rotation_id)


anti_block_engine = AntiBlockEngine()
