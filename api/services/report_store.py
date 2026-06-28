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
        "sufficiency": assess_data_sufficiency(total, aggregation[:20]),
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
            # Backfill sufficiency assessment for reports saved before this feature
            if "sufficiency" not in report:
                report["sufficiency"] = assess_data_sufficiency(
                    report.get("total", 0),
                    report.get("aggregation", []),
                )
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


# ---------------------------------------------------------------------------
# Data sufficiency assessment
# ---------------------------------------------------------------------------

_STAGES = [
    {
        "level": 1,
        "name": "需求探索",
        "description": "已有初步数据，可以看到用户需求轮廓，建议继续采集",
        "min_records": 10,
        "color": "#faad14",
    },
    {
        "level": 2,
        "name": "痛点确认",
        "description": "数据量足以看到重复痛点，可以做产品方向判断",
        "min_records": 50,
        "color": "#1890ff",
    },
    {
        "level": 3,
        "name": "MVP可行",
        "description": "已有足够有效需求，可以筛选P0痛点进入MVP验证",
        "min_records": 100,
        "color": "#52c41a",
    },
    {
        "level": 4,
        "name": "行业报告级",
        "description": "数据厚度足以生成可信行业分析报告",
        "min_records": 500,
        "color": "#722ed1",
    },
]


def assess_data_sufficiency(total: int, aggregation: list) -> dict:
    """Assess whether collected data is sufficient for product decisions.

    Returns structured assessment with stage, signals, and recommendations.
    """
    # Determine current stage
    stage = _STAGES[0]
    for s in reversed(_STAGES):
        if total >= s["min_records"]:
            stage = s
            break

    # Count high-frequency pain points (count >= 3 OR count >= 5% of total)
    threshold = max(3, round(total * 0.05))
    high_freq = [c for c in aggregation if c.get("count", 0) >= threshold]
    high_freq_count = len(high_freq)
    total_cats = len(aggregation)

    # Top-3 concentration ratio
    top3_count = sum(c.get("count", 0) for c in aggregation[:3])
    concentration = round(top3_count / total * 100, 1) if total > 0 else 0

    # Build signals
    signals = []

    if total < 10:
        signals.append({"type": "warn", "label": "数据不足", "text": "当前数据量较少，建议继续采集到 50 条以上"})
    elif total < 50:
        signals.append({
            "type": "info",
            "label": "初步探索",
            "text": f"已有 {total} 条有效数据，可以看到用户讨论方向，继续采集可发现重复痛点",
        })
    elif total < 100:
        signals.append({
            "type": "info",
            "label": "痛点可见",
            "text": f"已有 {total} 条数据，{high_freq_count} 个高频痛点已浮现，可以开始做产品方向判断",
        })
    else:
        signals.append({
            "type": "good",
            "label": "数据充足",
            "text": f"已有 {total} 条有效数据，{high_freq_count} 个高频痛点，具备MVP决策基础",
        })

    if high_freq_count >= 3:
        signals.append({
            "type": "good",
            "label": "痛点集中",
            "text": f"有 {high_freq_count} 个高频痛点反复出现，可以进行产品功能定位",
        })
    elif high_freq_count >= 1:
        signals.append({
            "type": "info",
            "label": "有信号",
            "text": f"已有 {high_freq_count} 个痛点开始重复，建议继续采集确认更多重复模式",
        })
    else:
        signals.append({
            "type": "warn",
            "label": "分散",
            "text": "需求较分散，无明显重复痛点，建议调整关键词扩大采集范围",
        })

    if concentration >= 50:
        signals.append({
            "type": "good",
            "label": "需求聚焦",
            "text": f"Top 3 痛点占比 {concentration}%，需求方向较集中，适合做垂直产品",
        })
    elif concentration >= 30:
        signals.append({
            "type": "info",
            "label": "有一定聚焦",
            "text": f"Top 3 痛点占比 {concentration}%，有初步聚焦方向",
        })
    else:
        signals.append({
            "type": "warn",
            "label": "需求分散",
            "text": f"Top 3 痛点仅占 {concentration}%，需求较分散，建议缩小关键词范围",
        })

    # Recommendations based on current stage
    recommendations = []
    if stage["level"] <= 2:
        remaining = max(10, _STAGES[2]["min_records"] - total)
        recommendations.append(f"建议继续采集约 {remaining} 条数据以达到 MVP 评估门槛（100 条）")
        recommendations.append("尝试扩展相关关键词，覆盖更多潜在需求表达")
        recommendations.append("关注高热度评论中的具体场景和诉求")
    elif stage["level"] == 3:
        recommendations.append("筛选 Top 3-5 高频痛点，为每个痛点设计一页 MVP 方案")
        recommendations.append(f"找 10 个目标用户验证痛点真实性")
        recommendations.append("可以开始做最小功能原型")
    else:
        recommendations.append("数据量充足，可以生成行业级分析报告")
        recommendations.append("建议细分行业场景做垂直报告")
        recommendations.append("可以准备商业化材料，寻找付费客户验证")

    return {
        "level": stage["level"],
        "stage_name": stage["name"],
        "stage_description": stage["description"],
        "color": stage["color"],
        "total_records": total,
        "high_freq_pain_points": high_freq_count,
        "total_categories": total_cats,
        "top3_concentration": concentration,
        "signals": signals,
        "recommendations": recommendations,
    }
