"""定时调度 时间线接口：返回作业时间序列结构。"""
from __future__ import annotations

import csv
import io
from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import StreamingResponse

from app.schemas import ActionPayload, ActionResult, EntryPayload
from app.services.scheduler import SchedulerService
from app.services.scheduler_engine import scheduler_engine

router = APIRouter(prefix="/api/scheduler", tags=["定时调度"])
service = SchedulerService()
LIST_FIELDS = ["计划编号", "关联任务", "Cron表达式", "时区", "重试次数", "失败通知", "并发上限", "下次执行"]
STATUSES = ["待激活", "运行中", "已完成", "已停用"]


def csv_cell(value: Any) -> str:
    text = str(value) if value is not None else ""
    if text and text[0] in "=+-@":
        text = "'" + text
    return '"' + text.replace('"', '""') + '"'


@router.get("")
def list_entries() -> dict[str, Any]:
    items = service.get_timeline()
    return {"items": items}


@router.get("/export")
def export_entries() -> StreamingResponse:
    items = service.get_timeline()
    buf = io.StringIO(newline="")
    writer = csv.writer(buf)
    all_keys = ["id"]
    if items:
        all_keys = list(items[0].keys())
    writer.writerow(all_keys)
    for item in items:
        writer.writerow([csv_cell(item.get(k, "")) for k in all_keys])
    buf.seek(0)
    return StreamingResponse(iter([buf.getvalue()]), media_type="text/csv; charset=utf-8",
                             headers={"Content-Disposition": "attachment; filename=scheduler.csv"})


@router.get("/{entry_id}")
def get_entry(entry_id: int) -> dict:
    entry = service.get_entry(entry_id)
    if entry is None:
        raise HTTPException(status_code=404, detail=f"调度计划 {entry_id} 不存在")
    return entry


@router.post("")
def create_entry(payload: EntryPayload) -> ActionResult:
    entry_or_none, missing = service.create_entry(payload.values)
    if missing:
        return ActionResult(ok=False, message=f"缺少必填字段：{'、'.join(missing)}")
    return ActionResult(ok=True, message="调度计划已登记", entry=entry_or_none)


@router.post("/{entry_id}/actions")
def run_action(entry_id: int, payload: ActionPayload) -> ActionResult:
    entry_or_none, message = service.run_action(entry_id, payload.action)
    if entry_or_none is None:
        return ActionResult(ok=False, message=message)
    return ActionResult(ok=True, message=message, entry=entry_or_none)


@router.post("/{entry_id}/trigger")
def trigger_plan(entry_id: int, simulate_failure: bool = False) -> dict[str, Any]:
    """触发调度计划，生成采集任务；模拟失败时进入重试队列。"""
    return scheduler_engine.trigger_plan(entry_id, simulate_failure=simulate_failure)


@router.post("/tick-all")
def tick_all() -> dict[str, Any]:
    """轮询所有待激活调度计划并触发。"""
    return scheduler_engine.tick_all()


@router.get("/joint/triggers")
def list_triggers() -> list[dict[str, Any]]:
    """查询调度触发记录。"""
    return scheduler_engine.list_triggers()
