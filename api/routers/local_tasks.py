# -*- coding: utf-8 -*-

"""Local tasks API - no Feishu dependency"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from ..services.local_task_manager import list_tasks, create_task, update_task, delete_task


router = APIRouter(prefix="/tasks", tags=["local_tasks"])


class TaskCreateRequest(BaseModel):
    platform: str = Field(default="微博")
    crawler_type: str = Field(default="关键词")
    keywords: str = ""
    specified_id: str = ""
    creator_id: str = ""
    max_notes_count: int = Field(default=20, ge=1, le=10000)
    enable_comments: bool = True
    enable_sub_comments: bool = False
    login_type: str = Field(default="无需登录")
    status: str = Field(default="待执行")


class TaskUpdateRequest(TaskCreateRequest):
    pass


@router.get("")
async def get_tasks():
    return list_tasks()


@router.post("")
async def add_task(request: TaskCreateRequest):
    try:
        return create_task(request.model_dump())
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"{type(exc).__name__}: {exc}")


@router.put("/{task_id}")
async def edit_task(task_id: int, request: TaskUpdateRequest):
    result = update_task(task_id, request.model_dump())
    if not result:
        raise HTTPException(status_code=404, detail="Task not found")
    return result



@router.post("/{task_id}/dry-run")
async def dry_run_task(task_id: int):
    """Preview the crawler command for a local task"""
    from ..services.local_task_manager import list_tasks
    tasks = list_tasks()
    task = None
    for t in tasks.get("tasks", []):
        if t.get("id") == task_id:
            task = t
            break
    if not task:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Task not found")
    
    platform_map = {"xhs": "xhs", "dy": "dy", "ks": "ks", "bili": "bili", "wb": "wb", "tieba": "tieba", "zhihu": "zhihu",
                    "小红书": "xhs", "抖音": "dy", "快手": "ks", "Bilibili": "bili", "微博": "wb", "贴吧": "tieba", "知乎": "zhihu"}
    pf = platform_map.get(task.get("platform", ""), task.get("platform", ""))
    ct = task.get("crawler_type", "search")
    kw = task.get("keywords", "")
    sid = task.get("specified_id", "")
    cid = task.get("creator_id", "")
    max_n = task.get("max_notes_count", 20)
    comments = "true" if task.get("enable_comments", True) else "false"
    sub_comments = "true" if task.get("enable_sub_comments", False) else "false"
    
    cmd_parts = ["uv", "run", "python", "main.py", "--platform", pf, "--lt", "qrcode", "--type", ct,
                 "--save_data_option", "jsonl", "--get_comment", comments, "--get_sub_comment", sub_comments,
                 "--crawler_max_notes_count", str(max_n)]
    if ct == "search" and kw:
        cmd_parts.extend(["--keywords", kw])
    elif ct == "detail" and sid:
        cmd_parts.extend(["--specified_id", sid])
    elif ct == "creator" and cid:
        cmd_parts.extend(["--creator_id", cid])
    
    return {"command": " ".join(cmd_parts), "task_id": task_id, "dry_run": True}


@router.post("/{task_id}/start")
async def start_task(task_id: int):
    """Start running a local task via crawler manager"""
    from ..services.local_task_manager import list_tasks
    from ..services.crawler_manager import crawler_manager
    from ..schemas import CrawlerStartRequest, LoginType, CrawlerType, SaveDataOption, PlatformType
    
    tasks = list_tasks()
    task = None
    for t in tasks.get("tasks", []):
        if t.get("id") == task_id:
            task = t
            break
    if not task:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Task not found")
    
    platform_map = {"xhs": "xhs", "dy": "dy", "ks": "ks", "bili": "bili", "wb": "wb", "tieba": "tieba", "zhihu": "zhihu",
                    "小红书": "xhs", "抖音": "dy", "快手": "ks", "Bilibili": "bili", "微博": "wb", "贴吧": "tieba", "知乎": "zhihu"}
    pf = platform_map.get(task.get("platform", ""), task.get("platform", ""))
    
    # Create config
    try:
        config = CrawlerStartRequest(
            platform=PlatformType(pf),
            login_type=LoginType.QRCODE,
            crawler_type=CrawlerType(task.get("crawler_type", "search").upper()),
            keywords=task.get("keywords", ""),
            specified_ids=task.get("specified_id", ""),
            creator_ids=task.get("creator_id", ""),
            max_notes_count=task.get("max_notes_count", 20),
            enable_comments=task.get("enable_comments", True),
            enable_sub_comments=task.get("enable_sub_comments", False),
            save_option=SaveDataOption.JSONL,
        )
    except Exception as exc:
        from fastapi import HTTPException
        raise HTTPException(status_code=400, detail=f"Config error: {exc}")
    
    success = await crawler_manager.start(config)
    if not success:
        from fastapi import HTTPException
        raise HTTPException(status_code=400, detail="Crawler already running")
    
    # Update task status to running
    from ..services.local_task_manager import update_task
    update_task(task_id, {"status": "运行中"})
    
    return {"status": "ok", "message": "Task started"}

@router.delete("/{task_id}")
async def remove_task(task_id: int):
    if not delete_task(task_id):
        raise HTTPException(status_code=404, detail="Task not found")
    return {"status": "ok"}
