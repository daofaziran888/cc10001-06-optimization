"""定时调度 时间线接口：作业时间序列、调度窗口扫描与续做批次。"""
from __future__ import annotations

import csv
import io
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app.schemas import ActionPayload, ActionResult, EntryPayload
from app.services.scheduler import SchedulerService
from app.services.scheduler_engine import SCOPE_INCLUDE_DUE, scheduler_engine

router = APIRouter(prefix="/api/scheduler", tags=["定时调度"])
service = SchedulerService()
LIST_FIELDS = ["计划编号", "关联任务", "Cron表达式", "时区", "重试次数", "失败通知", "并发上限", "下次执行"]
STATUSES = ["待激活", "运行中", "已完成", "已停用"]


class ScanPayload(BaseModel):
    """批量扫描参数：扫描范围决定刚到期的新窗口本轮还是下一轮进入采集。"""

    scope: str = Field(default=SCOPE_INCLUDE_DUE)
    as_of: str | None = None
    plan_ids: list[int] | None = None
    simulate_failure: bool = False


class ResumePayload(BaseModel):
    """续做入口参数：失败窗口只允许从这里生成续做任务批次。"""

    trigger_id: int
    note: str | None = None


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


@router.post("")
def create_entry(payload: EntryPayload) -> ActionResult:
    entry_or_none, missing = service.create_entry(payload.values)
    if missing:
        return ActionResult(ok=False, message=f"缺少必填字段：{'、'.join(missing)}")
    return ActionResult(ok=True, message="调度计划已登记", entry=entry_or_none)


@router.post("/tick-all")
def tick_all(payload: ScanPayload | None = None) -> dict[str, Any]:
    """批量扫描待激活调度窗口，去重生成触发记录与续做任务批次。"""
    body = payload or ScanPayload()
    return scheduler_engine.scan_windows(
        scope=body.scope,
        as_of=body.as_of,
        plan_ids=body.plan_ids,
        simulate_failure=body.simulate_failure,
    )


@router.post("/scan")
def scan_windows(payload: ScanPayload) -> dict[str, Any]:
    """显式扫描入口：与 tick-all 共用同一套窗口判定与去重逻辑。"""
    return scheduler_engine.scan_windows(
        scope=payload.scope,
        as_of=payload.as_of,
        plan_ids=payload.plan_ids,
        simulate_failure=payload.simulate_failure,
    )


@router.get("/joint/triggers")
def list_triggers() -> list[dict[str, Any]]:
    """查询调度触发记录。"""
    return scheduler_engine.list_triggers()


@router.get("/joint/triggers/{trigger_id}")
def get_trigger(trigger_id: int) -> dict[str, Any]:
    trigger = scheduler_engine.get_trigger(trigger_id)
    if trigger is None:
        raise HTTPException(status_code=404, detail=f"调度触发记录 {trigger_id} 不存在")
    return trigger


@router.get("/joint/resume-batches")
def list_resume_batches() -> list[dict[str, Any]]:
    """查询续做任务批次。"""
    return scheduler_engine.list_resume_batches()


@router.get("/joint/resume-batches/{batch_id}")
def get_resume_batch(batch_id: int) -> dict[str, Any]:
    batch = scheduler_engine.get_resume_batch(batch_id)
    if batch is None:
        raise HTTPException(status_code=404, detail=f"续做任务批次 {batch_id} 不存在")
    return batch


@router.get("/windows")
def list_windows(as_of: str | None = Query(default=None)) -> dict[str, Any]:
    """调度窗口合并视图：区分新触发、已跳过、待续做与未到期。"""
    return scheduler_engine.list_windows(as_of=as_of)


@router.post("/resume")
def resume_window(payload: ResumePayload) -> dict[str, Any]:
    """唯一续做入口：为失败窗口生成续做任务批次。"""
    return scheduler_engine.resume_window(payload.trigger_id, note=payload.note or "")


@router.post("/{entry_id}/trigger")
def trigger_plan(entry_id: int, simulate_failure: bool = False, window_start: str | None = None) -> dict[str, Any]:
    """触发调度计划，生成采集任务；已成功窗口直接跳过，失败窗口进入重试队列。"""
    return scheduler_engine.trigger_plan(entry_id, simulate_failure=simulate_failure, window_start=window_start)


@router.get("/{entry_id}")
def get_entry(entry_id: int) -> dict:
    entry = service.get_entry(entry_id)
    if entry is None:
        raise HTTPException(status_code=404, detail=f"调度计划 {entry_id} 不存在")
    return entry


@router.post("/{entry_id}/actions")
def run_action(entry_id: int, payload: ActionPayload) -> ActionResult:
    entry_or_none, message = service.run_action(entry_id, payload.action)
    if entry_or_none is None:
        return ActionResult(ok=False, message=message)
    return ActionResult(ok=True, message=message, entry=entry_or_none)
