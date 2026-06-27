# -*- coding: utf-8 -*-
"""Local task manager - stores tasks in JSON file, no Feishu dependency"""

from __future__ import annotations

import json
import os
import threading
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional


TASKS_FILE = Path(__file__).resolve().parent.parent / ".local_tasks.json"
_lock = threading.Lock()


def _load_tasks() -> List[Dict[str, Any]]:
    if not TASKS_FILE.exists():
        return []
    try:
        with open(TASKS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data if isinstance(data, list) else []
    except (json.JSONDecodeError, OSError):
        return []


def _save_tasks(tasks: List[Dict[str, Any]]) -> None:
    TASKS_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(TASKS_FILE, "w", encoding="utf-8") as f:
        json.dump(tasks, f, ensure_ascii=False, indent=2)


def _next_id(tasks: List[Dict[str, Any]]) -> int:
    ids = [t.get("id", 0) for t in tasks]
    return (max(ids) + 1) if ids else 1


def list_tasks() -> Dict[str, Any]:
    with _lock:
        tasks = _load_tasks()
    counts: Dict[str, int] = {}
    for t in tasks:
        s = t.get("status", "待执行")
        counts[s] = counts.get(s, 0) + 1
    return {"tasks": tasks, "counts": counts, "total": len(tasks)}


def create_task(fields: Dict[str, Any]) -> Dict[str, Any]:
    with _lock:
        tasks = _load_tasks()
        task = {
            "id": _next_id(tasks),
            "platform": fields.get("platform", "微博"),
            "crawler_type": fields.get("crawler_type", "关键词"),
            "keywords": fields.get("keywords", ""),
            "specified_id": fields.get("specified_id", ""),
            "creator_id": fields.get("creator_id", ""),
            "max_notes_count": fields.get("max_notes_count", 20),
            "enable_comments": fields.get("enable_comments", True),
            "enable_sub_comments": fields.get("enable_sub_comments", False),
            "login_type": fields.get("login_type", "无需登录"),
            "status": fields.get("status", "待执行"),
            "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "finished_at": "",
            "success_count": 0,
            "skip_count": 0,
            "fail_count": 0,
            "error": "",
        }
        tasks.append(task)
        _save_tasks(tasks)
    return task


def update_task(task_id: int, fields: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    with _lock:
        tasks = _load_tasks()
        for task in tasks:
            if task.get("id") == task_id:
                task.update(fields)
                _save_tasks(tasks)
                return task
    return None


def delete_task(task_id: int) -> bool:
    with _lock:
        tasks = _load_tasks()
        new_tasks = [t for t in tasks if t.get("id") != task_id]
        if len(new_tasks) == len(tasks):
            return False
        _save_tasks(new_tasks)
    return True
