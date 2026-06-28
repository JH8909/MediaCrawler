# -*- coding: utf-8 -*-
"""Report store — persist analysis report results to disk and retrieve them.

Reports are saved as JSON files in data/reports/<timestamp>_<platform>_<keyword>.json
"""

from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

PROJECT_ROOT = Path(__file__).resolve().parents[2]
REPORTS_DIR = PROJECT_ROOT / "data" / "reports"
MAX_REPORTS = 50  # keep at most this many report files


def save_report(
    platform: str,
    keyword: str,
    total: int,
    aggregation: list,
    classified_records: list,
    solutions_data: list,
    webhook_sent: bool = False,
) -> dict:
    """Persist analysis report to disk and return the report dict.

    Returns a dict suitable for frontend consumption and WebSocket broadcast.
    """
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)

    now = datetime.now()
    ts = now.strftime("%Y%m%d_%H%M%S")
    safe_kw = keyword.replace(" ", "_")[:30] if keyword else "nokeyword"
    safe_platform = platform or "unknown"
    filename = f"{ts}_{safe_platform}_{safe_kw}.json"
    filepath = REPORTS_DIR / filename

    # Only store top-level info to keep file size reasonable;
    # classified_records can be large — store a summary instead.
    summary_records = []
    for rec in (classified_records or [])[:50]:
        summary_records.append({
            "categories": rec.get("categories", []),
            "hot_score": rec.get("hot_score", 0),
            "extracted_text": rec.get("extracted_text", "")[:120],
            "nickname": rec.get("nickname", rec.get("author", "")),
            "liked_count": rec.get("liked_count", rec.get("like_count", 0)),
        })

    report = {
        "platform": safe_platform,
        "keyword": safe_kw,
        "total": total,
        "categories": len(aggregation),
        "aggregation": aggregation[:20],
        "classified_count": len(classified_records or []),
        "classified_preview": summary_records,
        "solutions": len(solutions_data),
        "solutions_data": solutions_data,
        "webhook_sent": webhook_sent,
        "generated_at": now.strftime("%Y-%m-%d %H:%M:%S"),
        "file": filename,
    }

    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    _prune_old_reports()
    return report


def get_latest_report(platform: Optional[str] = None) -> Optional[dict]:
    """Return the most recent analysis report, optionally filtered by platform."""
    if not REPORTS_DIR.exists():
        return None

    files = sorted(REPORTS_DIR.glob("*.json"), reverse=True)
    for fp in files:
        try:
            report = json.loads(fp.read_text(encoding="utf-8"))
            if platform and report.get("platform") != platform:
                continue
            return report
        except Exception:
            continue
    return None


def list_reports(limit: int = 20, platform: Optional[str] = None) -> list:
    """Return a list of recent report summaries."""
    if not REPORTS_DIR.exists():
        return []

    result = []
    files = sorted(REPORTS_DIR.glob("*.json"), reverse=True)
    for fp in files:
        if len(result) >= limit:
            break
        try:
            report = json.loads(fp.read_text(encoding="utf-8"))
            if platform and report.get("platform") != platform:
                continue
            # Return lightweight summary
            result.append({
                "platform": report.get("platform"),
                "keyword": report.get("keyword"),
                "total": report.get("total"),
                "categories": report.get("categories"),
                "solutions": report.get("solutions"),
                "webhook_sent": report.get("webhook_sent"),
                "generated_at": report.get("generated_at"),
                "file": report.get("file"),
            })
        except Exception:
            continue
    return result


def _prune_old_reports() -> None:
    """Delete oldest report files if we exceed MAX_REPORTS."""
    files = sorted(REPORTS_DIR.glob("*.json"))  # oldest first
    while len(files) > MAX_REPORTS:
        try:
            files[0].unlink()
        except Exception:
            pass
        files.pop(0)
