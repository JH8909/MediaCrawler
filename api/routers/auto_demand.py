# -*- coding: utf-8 -*-
"""Auto demand report API."""

from __future__ import annotations

from fastapi import APIRouter

from api.schemas.auto_demand import AutoDemandConfig, AutoDemandRunRequest
from api.services.auto_demand_manager import auto_demand_manager


router = APIRouter(prefix="/auto-demand", tags=["auto-demand"])


@router.get("/status")
async def get_status():
    return auto_demand_manager.get_status()


@router.post("/config")
async def save_config(config: AutoDemandConfig):
    return {"status": "ok", "config": auto_demand_manager.save_config(config).model_dump()}


@router.post("/run")
async def run_once(request: AutoDemandRunRequest):
    return auto_demand_manager.run_once(dry_run=request.dry_run)

