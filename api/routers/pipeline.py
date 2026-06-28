# -*- coding: utf-8 -*-
"""Pipeline API - one-click demand discovery"""

from __future__ import annotations

import asyncio
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from ..services.pipeline_manager import pipeline_manager
from integrations.demand_report.keywords import DEFAULT_PLATFORMS

router = APIRouter(prefix="/pipeline", tags=["pipeline"])


class PipelineStartRequest(BaseModel):
    platforms: list = Field(default_factory=lambda: DEFAULT_PLATFORMS[:2])
    keyword_count: int = Field(default=3, ge=1, le=10)
    keyword_offset: int = Field(default=0, ge=0)
    max_notes: int = Field(default=15, ge=1, le=100)


class PipelineStatusResponse(BaseModel):
    status: str
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    logs: List[str] = Field(default_factory=list)
    last_result: Optional[Dict[str, Any]] = Field(default_factory=dict)


@router.post("/start")
async def start_pipeline(request: PipelineStartRequest):
    """Start one-click demand discovery pipeline"""
    if pipeline_manager.status == "running":
        raise HTTPException(status_code=400, detail="Pipeline is already running")

    asyncio.create_task(pipeline_manager.start(
        platforms=request.platforms,
        keyword_count=request.keyword_count,
        keyword_offset=request.keyword_offset,
        max_notes=request.max_notes,
    ))
    return {"status": "started", "message": "Pipeline started in background"}


@router.get("/status", response_model=PipelineStatusResponse)
async def get_pipeline_status():
    """Get pipeline status and logs"""
    return pipeline_manager.get_status()


@router.post("/stop")
async def stop_pipeline():
    """Stop running pipeline"""
    if pipeline_manager.status != "running":
        raise HTTPException(status_code=400, detail="No pipeline is running")
    # For now, the pipeline runs synchronously in the event loop
    # A full implementation would use asyncio tasks for cancellation
    return {"status": "ok", "message": "Stop requested (will complete current task)"}
