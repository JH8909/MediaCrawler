"""
Data statistics service - aggregates crawl data for dashboard visualization.
"""
import json
import os
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import config

DATA_DIR = Path(__file__).resolve().parents[2] / "data"


def _find_data_files() -> List[Path]:
    """Find all data files across all platforms."""
    files = []
    if not DATA_DIR.exists():
        return files
    for root, _, filenames in os.walk(DATA_DIR):
        for fn in filenames:
            p = Path(root) / fn
            if p.suffix.lower() in {".jsonl", ".json"}:
                files.append(p)
    return files


def get_overview_stats() -> Dict[str, Any]:
    """Get overview statistics across all platforms."""
    total_records = 0
    platform_records: Dict[str, int] = defaultdict(int)
    platform_files: Dict[str, int] = defaultdict(int)

    for fp in _find_data_files():
        rel = str(fp.relative_to(DATA_DIR))
        parts = rel.split(os.sep)
        platform = parts[0] if len(parts) > 1 else "unknown"

        platform_files[platform] += 1
        try:
            if fp.suffix == ".jsonl":
                count = sum(1 for line in fp.open("r", encoding="utf-8-sig") if line.strip())
            elif fp.suffix == ".json":
                with fp.open("r", encoding="utf-8") as f:
                    data = json.load(f)
                count = len(data) if isinstance(data, list) else 1
            else:
                count = 0
            total_records += count
            platform_records[platform] += count
        except Exception:
            continue

    return {
        "total_files": len(_find_data_files()),
        "total_records": total_records,
        "platforms": {
            p: {"files": platform_files[p], "records": platform_records[p]}
            for p in sorted(platform_records)
        },
    }


def get_recent_activity(days: int = 7) -> Dict[str, Any]:
    """Get activity data for the last N days (by file modification time)."""
    from collections import defaultdict
    now = datetime.now()
    daily: Dict[str, int] = defaultdict(int)
    platform_daily: Dict[str, Dict[str, int]] = defaultdict(lambda: defaultdict(int))

    for fp in _find_data_files():
        mtime = datetime.fromtimestamp(fp.stat().st_mtime)
        delta = now - mtime
        if delta.days > days:
            continue

        day_key = mtime.strftime("%Y-%m-%d")
        daily[day_key] += 1

        rel = str(fp.relative_to(DATA_DIR))
        platform = rel.split(os.sep)[0] if os.sep in rel else "unknown"
        platform_daily[day_key][platform] = platform_daily[day_key].get(platform, 0) + 1

    return {
        "days": days,
        "daily_file_counts": dict(sorted(daily.items())),
        "daily_platforms": {
            day: dict(platforms)
            for day, platforms in sorted(platform_daily.items())
        },
    }


def _generate_bar_chart(
    labels: List[str],
    values: List[int],
    title: str,
    xlabel: str = "",
    ylabel: str = "",
) -> str:
    """Generate a bar chart and return it as a base64 PNG string."""
    import base64
    from io import BytesIO

    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    plt.rcParams["font.sans-serif"] = ["SimHei", "DejaVu Sans", "Arial Unicode MS"]
    plt.rcParams["axes.unicode_minus"] = False

    fig, ax = plt.subplots(figsize=(10, 5))
    colors = plt.cm.Blues([0.4 + 0.5 * i / max(len(labels), 1) for i in range(len(labels))])
    ax.bar(labels, values, color=colors)
    ax.set_title(title, fontsize=14, pad=15)
    ax.set_xlabel(xlabel)
    ax.set_ylabel(ylabel)
    ax.tick_params(axis="x", rotation=45)

    for i, v in enumerate(values):
        ax.text(i, v + max(values) * 0.01, str(v), ha="center", fontsize=10)

    fig.tight_layout()
    buf = BytesIO()
    fig.savefig(buf, format="png", dpi=100)
    plt.close(fig)
    buf.seek(0)
    return base64.b64encode(buf.read()).decode("utf-8")


def get_chart(chart_type: str) -> Optional[str]:
    """Generate and return a chart as base64 PNG."""
    stats = get_overview_stats()

    if chart_type == "platform_records":
        platforms = sorted(stats["platforms"].keys())
        records = [stats["platforms"][p]["records"] for p in platforms]
        return _generate_bar_chart(platforms, records, "各平台采集数据量", "平台", "记录数")

    if chart_type == "platform_files":
        platforms = sorted(stats["platforms"].keys())
        files = [stats["platforms"][p]["files"] for p in platforms]
        return _generate_bar_chart(platforms, files, "各平台数据文件数", "平台", "文件数")

    if chart_type == "recent_activity":
        activity = get_recent_activity(7)
        days = list(activity["daily_file_counts"].keys())
        counts = list(activity["daily_file_counts"].values())
        if days:
            return _generate_bar_chart(days, counts, f"近 7 天活动趋势", "日期", "文件数")

    return None
