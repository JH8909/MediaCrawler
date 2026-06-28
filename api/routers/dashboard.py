"""
Dashboard API - data visualization and statistics endpoints.
"""
from fastapi import APIRouter, Query
from fastapi.responses import JSONResponse

from ..services.data_stats import get_overview_stats, get_recent_activity, get_chart

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("/stats")
async def overview_stats():
    """Get overview statistics (files, records by platform)"""
    return get_overview_stats()


@router.get("/activity")
async def recent_activity(days: int = Query(7, ge=1, le=30)):
    """Get recent activity data (file counts per day by platform)"""
    return get_recent_activity(days=days)


@router.get("/charts/{chart_type}")
async def chart(chart_type: str):
    """Get a chart image as base64 PNG.

    Supported chart types:
    - platform_records: Records per platform
    - platform_files: Files per platform
    - recent_activity: Daily file activity for the last 7 days
    """
    b64 = get_chart(chart_type)
    if b64 is None:
        return JSONResponse(
            status_code=404,
            content={"error": f"Unknown chart type: {chart_type}"},
        )
    return {"chart": b64, "format": "png"}
