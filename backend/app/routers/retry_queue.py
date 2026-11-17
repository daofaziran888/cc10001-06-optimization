"""重试队列 时间线接口：返回作业时间序列结构。"""
from __future__ import annotations

import csv
import io
from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.schemas import ActionPayload, ActionResult, EntryPayload
from app.services.retry_queue import RetryQueueService
from app.services.scheduler_engine import scheduler_engine

router = APIRouter(prefix="/api/retry_queue", tags=["重试队列"])
service = RetryQueueService()
LIST_FIELDS = ["条目编号", "失败页面", "失败原因", "重试次数", "最大重试", "下次重试", "错误详情", "关联任务"]
STATUSES = ["排队中", "重试中", "已达上限", "已恢复"]


class ResumePayload(BaseModel):
    """重试条目续做：转发到调度引擎的唯一续做入口。"""

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
                             headers={"Content-Disposition": "attachment; filename=retry_queue.csv"})


@router.get("/{entry_id}")
def get_entry(entry_id: int) -> dict:
    entry = service.get_entry(entry_id)
    if entry is None:
        raise HTTPException(status_code=404, detail=f"重试条目 {entry_id} 不存在")
    return entry


@router.post("")
def create_entry(payload: EntryPayload) -> ActionResult:
    entry_or_none, missing = service.create_entry(payload.values)
    if missing:
        return ActionResult(ok=False, message=f"缺少必填字段：{'、'.join(missing)}")
    return ActionResult(ok=True, message="重试条目已登记", entry=entry_or_none)


@router.get("/joint/windows")
def list_resume_windows(as_of: str | None = Query(default=None)) -> dict[str, Any]:
    """失败窗口视图：列出仍可继续重试的窗口条目，供重试队列页发起续做。"""
    window_state = scheduler_engine.list_windows(as_of=as_of)
    pending_keys = {
        item["window_key"]
        for item in window_state.get("items", [])
        if item.get("retry_entry_id") and item.get("classification") == "待续做"
    }
    items = [
        row for row in service.get_entries()
        if str(row.get("window_key", "")) in pending_keys
    ]
    items.sort(key=lambda row: (str(row.get("窗口起始", "")), int(row.get("id", 0))))
    return {"items": items, "total": len(items)}


@router.post("/{entry_id}/actions")
def run_action(entry_id: int, payload: ActionPayload) -> ActionResult:
    entry_or_none, message = service.run_action(entry_id, payload.action)
    if entry_or_none is None:
        return ActionResult(ok=False, message=message)
    return ActionResult(ok=True, message=message, entry=entry_or_none)


@router.post("/{entry_id}/resume")
def resume_entry(entry_id: int, payload: ResumePayload | None = None) -> dict[str, Any]:
    """从重试条目发起续做：内部仍只调用调度引擎的唯一续做入口。"""
    entry = service.get_entry(entry_id)
    if entry is None:
        return {"ok": False, "error": f"重试条目 {entry_id} 不存在或已归档"}
    trigger_id = entry.get("trigger_id")
    if trigger_id in (None, ""):
        return {"ok": False, "error": "该重试条目没有关联的调度触发记录，无法续做"}
    return scheduler_engine.resume_window(int(trigger_id), note=(payload.note if payload else "") or "")
