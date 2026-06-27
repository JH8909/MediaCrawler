# -*- coding: utf-8 -*-

"""Feishu Webhook API router"""

from __future__ import annotations

import os
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from integrations.feishu_webhook import get_webhook_url, test_webhook

router = APIRouter(prefix="/feishu/webhook", tags=["feishu_webhook"])


class WebhookUrlRequest(BaseModel):
    url: str = Field(default="", max_length=500)
    test_send: bool = Field(default=False)


@router.get("/status")
async def get_webhook_status():
    url = get_webhook_url()
    return {
        "configured": bool(url),
        "url": url[:50] + "..." if url and len(url) > 50 else (url or ""),
        "url_masked": bool(url),
    }


@router.post("/save")
async def save_webhook_url(request: WebhookUrlRequest):
    """Save webhook URL to .env file"""
    from pathlib import Path
    url = request.url.strip()
    env_path = Path(__file__).resolve().parent.parent.parent / ".env"
    if not env_path.exists():
        raise HTTPException(status_code=500, detail=".env file not found")
    try:
        lines = env_path.read_text(encoding="utf-8").splitlines()
        found = False
        for i, line in enumerate(lines):
            if line.startswith("FEISHU_WEBHOOK_URL"):
                lines[i] = "FEISHU_WEBHOOK_URL=" + url
                found = True
                break
        if not found:
            lines.append("FEISHU_WEBHOOK_URL=" + url)
        NL = chr(10)
        env_path.write_text(NL.join(lines), encoding="utf-8")
        os.environ["FEISHU_WEBHOOK_URL"] = url
        return {"success": True, "message": "Webhook URL saved"}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/test")
async def test_webhook_url():
    url = get_webhook_url()
    if not url:
        raise HTTPException(status_code=400, detail="Webhook URL not configured")
    result = test_webhook(url)
    if not result["success"]:
        raise HTTPException(status_code=400, detail=result["message"])
    return result
