# -*- coding: utf-8 -*-

"""LLM API Configuration router - save/read LLM API config to .env (encrypted)"""

from __future__ import annotations

import os
from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from tools.config_crypto import encrypt_sensitive, decrypt_sensitive, is_encrypted

router = APIRouter(prefix="/llm", tags=["llm_config"])

ENV_PATH = Path(__file__).resolve().parent.parent.parent / ".env"

LLM_KEYS = ["LLM_API_KEY", "LLM_API_URL", "LLM_MODEL"]
MASKED_KEYS = ["LLM_API_KEY"]


class LLMConfigRequest(BaseModel):
    api_key: str = Field(default="", max_length=500)
    api_url: str = Field(default="", max_length=500)
    model: str = Field(default="", max_length=200)
    test_send: bool = Field(default=False)


def _read_env() -> dict:
    """Read LLM config from .env file"""
    config = {}
    if not ENV_PATH.exists():
        return {k: "" for k in LLM_KEYS}
    try:
        lines = ENV_PATH.read_text(encoding="utf-8").splitlines()
    except Exception:
        return {k: "" for k in LLM_KEYS}
    for line in lines:
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        key = key.strip()
        val = val.strip().strip('"').strip("'")
        if key in LLM_KEYS:
            # Decrypt sensitive values
            if key in MASKED_KEYS:
                val = decrypt_sensitive(val)
            config[key] = val
    for k in LLM_KEYS:
        config.setdefault(k, "")
    return config


def _write_env(updates: dict) -> None:
    """Update LLM config in .env file"""
    if not ENV_PATH.exists():
        ENV_PATH.write_text("", encoding="utf-8")
    try:
        lines = ENV_PATH.read_text(encoding="utf-8").splitlines()
    except Exception:
        lines = []

    # Remove existing LLM lines (including comments)
    cleaned = []
    skip = False
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("# === LLM"):
            skip = True
            continue
        if skip and stripped.startswith("#"):
            continue
        if any(stripped.startswith(k + "=") for k in LLM_KEYS):
            continue
        if skip:
            skip = False
        cleaned.append(line)

    # Append new config
    cleaned.append("")
    cleaned.append("# === LLM Configuration ===")
    for k in LLM_KEYS:
        val = updates.get(k, "")
        # Encrypt sensitive values before writing to disk
        if k in MASKED_KEYS and val and not is_encrypted(val):
            val = encrypt_sensitive(val)
        cleaned.append(f"{k}={val}")

    NL = chr(10)
    ENV_PATH.write_text(NL.join(cleaned) + NL, encoding="utf-8")

    # Update current process env
    for k, v in updates.items():
        os.environ[k] = v


@router.get("/config")
async def get_llm_config():
    """Get current LLM config (API key is masked)"""
    config = _read_env()
    result = {}
    for k in LLM_KEYS:
        val = config.get(k, "")
        if k in MASKED_KEYS and val:
            result[k] = val[:4] + "****" + val[-4:] if len(val) > 8 else "****"
        else:
            result[k] = val
    result["configured"] = bool(config.get("LLM_API_KEY", ""))
    return result


@router.post("/config")
async def save_llm_config(request: LLMConfigRequest):
    """Save LLM config to .env file"""
    updates = {
        "LLM_API_KEY": request.api_key.strip(),
        "LLM_API_URL": request.api_url.strip(),
        "LLM_MODEL": request.model.strip(),
    }
    # Validate: if api_key is masked (unchanged), keep current
    if updates["LLM_API_KEY"] and "****" in updates["LLM_API_KEY"]:
        current = _read_env()
        updates["LLM_API_KEY"] = current.get("LLM_API_KEY", updates["LLM_API_KEY"])

    try:
        _write_env(updates)
        return {"success": True, "message": "LLM 配置已保存"}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/test")
async def test_llm_connection():
    """Test LLM API connection with current config"""
    config = _read_env()
    api_key = config.get("LLM_API_KEY", "")
    api_url = config.get("LLM_API_URL", "")
    model = config.get("LLM_MODEL", "")

    if not api_key:
        raise HTTPException(status_code=400, detail="LLM API Key 未配置")

    try:
        import httpx
        with httpx.Client(timeout=15.0) as client:
            resp = client.post(
                api_url or "https://api.deepseek.com/v1/chat/completions",
                headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                json={
                    "model": model or "deepseek-v4-flash",
                    "messages": [{"role": "user", "content": "回复OK表示连接正常"}],
                    "max_tokens": 10,
                },
            )
            resp.raise_for_status()
            body = resp.json()
            reply = body.get("choices", [{}])[0].get("message", {}).get("content", "")
            return {"success": True, "message": "LLM 连接测试成功", "reply": reply.strip()}
    except Exception as exc:
        return {"success": False, "message": f"连接失败: {type(exc).__name__}: {str(exc)[:100]}"}

