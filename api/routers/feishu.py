# -*- coding: utf-8 -*-

"""Feishu environment check - no task management needed anymore"""

from __future__ import annotations

import os

from fastapi import APIRouter

router = APIRouter(prefix="/feishu", tags=["feishu"])

FEISHU_ENV_NAMES = [
    "FEISHU_APP_ID",
    "FEISHU_APP_SECRET",
    "FEISHU_APP_TOKEN",
    "FEISHU_TABLE_ID",
    "FEISHU_WEBHOOK_URL",
]


@router.get("/env")
async def check_feishu_env():
    """Check which Feishu env vars are set"""
    env = {}
    for name in FEISHU_ENV_NAMES:
        env[name] = bool(os.getenv(name))
    return {
        "env": {key: ("SET" if value else "MISSING") for key, value in env.items()},
        "ready": all(env.values()),
    }
