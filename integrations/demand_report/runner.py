# -*- coding: utf-8 -*-
"""Runner for the automated demand discovery report workflow."""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from typing import Callable, Iterable, List, Optional

from integrations.feishu_webhook import (
    get_webhook_url,
    send_demand_report,
    send_demand_report_summary,
)

from .excel_writer import write_demand_report
from .extractor import extract_demand_item
from .keywords import DEFAULT_PLATFORMS, generate_keyword_plans
from .models import DemandItem, DemandReportStats, DemandRunResult, KeywordPlan
from .state import DEFAULT_DEMAND_STATE_PATH, load_hashes, save_hashes


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DATA_DIR = PROJECT_ROOT / "data"
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "output" / "demand_reports"


def _load_env() -> None:
    """Load .env file so FEISHU_WEBHOOK_URL and other credentials are available."""
    env_path = PROJECT_ROOT / ".env"
    if not env_path.is_file():
        return
    try:
        from dotenv import load_dotenv
        load_dotenv(dotenv_path=str(env_path))
    except ImportError:
        with open(env_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, _, val = line.partition("=")
                key, val = key.strip(), val.strip().strip('"').strip("'")
                if key and val:
                    os.environ.setdefault(key, val)


_load_env()


def run_auto_demand_report(
    platforms: Optional[List[str]] = None,
    keyword_count: int = 3,
    keyword_offset: int = 0,
    max_notes_count: int = 15,
    dry_run: bool = False,
    data_dir: Path = DEFAULT_DATA_DIR,
    output_dir: Path = DEFAULT_OUTPUT_DIR,
    state_path: Path = DEFAULT_DEMAND_STATE_PATH,
    executor: Optional[Callable[..., object]] = None,
    send_summary: Optional[Callable[..., bool]] = send_demand_report_summary,
) -> DemandRunResult:
    """Run keyword generation, crawler execution, extraction, Excel writing, and notification."""

    platforms = platforms or DEFAULT_PLATFORMS
    plans = generate_keyword_plans(count=keyword_count, offset=keyword_offset)
    stats = DemandReportStats(total_keywords=len(plans))
    logs: List[str] = []

    if dry_run:
        logs.append("Dry run: crawler execution, Excel writing, and notification skipped")
        return DemandRunResult(dry_run=True, platforms=platforms, keyword_plans=plans, stats=stats, logs=logs)

    run_command = executor or _default_executor
    for platform in platforms:
        for plan in plans:
            command = _build_crawl_command(platform, plan, max_notes_count)
            logs.append("Running: " + " ".join(command))
            try:
                run_command(command, cwd=PROJECT_ROOT)
            except Exception as exc:
                stats.failed_tasks += 1
                logs.append(f"Failed {platform} {plan.keyword}: {exc}")

    known_hashes = load_hashes(state_path)
    all_hashes = set(known_hashes)
    items: List[DemandItem] = []
    all_records: List[dict] = []

    for platform in platforms:
        for record in _iter_export_records(data_dir, platform):
            stats.total_records += 1
            plan = _plan_for_record(record, plans)
            item = extract_demand_item(record, plan, platform=platform)
            if item is None:
                continue
            all_records.append(record)
            if item.content_hash in all_hashes:
                stats.skipped_duplicates += 1
                continue
            all_hashes.add(item.content_hash)
            items.append(item)
            stats.new_items += 1
            if item.content_type == "评论":
                stats.comment_items += 1
            else:
                stats.body_items += 1

    excel_path = write_demand_report(items, output_dir=output_dir) if items else None
    if items:
        save_hashes(all_hashes, state_path)

    # Run analysis and send detailed demand report (pain points + solutions)
    analysis_sent = False
    if all_records:
        try:
            from api.services.needs_analyzer import analyze_records
            from api.services.solution_generator import generate_all_solutions

            logs.append("Analyzing " + str(len(all_records)) + " records for demand report...")
            analysis = analyze_records(all_records)
            agg = analysis.get("aggregation", [])
            classified = analysis.get("classified_records", [])

            solutions_data = []
            try:
                sol_result = generate_all_solutions(
                    aggregation=agg,
                    classified_records=classified,
                    max_categories=5,
                )
                solutions_data = sol_result.get("solutions", [])
            except Exception as exc:
                logs.append("Solution generation failed: " + str(exc))

            webhook_url = get_webhook_url()
            if webhook_url and agg:
                platform_str = "、".join(platforms)
                keyword_str = " / ".join(p.keyword for p in plans)
                analysis_sent = send_demand_report(
                    aggregation=agg,
                    solutions_data=solutions_data,
                    keyword=keyword_str,
                    platform=platform_str,
                    total=stats.new_items,
                    webhook_url=webhook_url,
                )
                logs.append("Detailed analysis report sent: " + str(analysis_sent))
            else:
                logs.append("Webhook URL not configured, skipping detailed report")
        except Exception as exc:
            logs.append("Analysis failed: " + str(exc))

    notification_sent = analysis_sent
    if send_summary:
        summary_sent = bool(
            send_summary(
                platforms=platforms,
                keyword_plans=plans,
                stats=stats,
                excel_path=str(excel_path) if excel_path else "",
            )
        )
        notification_sent = summary_sent or analysis_sent

    return DemandRunResult(
        dry_run=False,
        platforms=platforms,
        keyword_plans=plans,
        stats=stats,
        excel_path=excel_path,
        logs=logs,
        notification_sent=notification_sent,
    )


def _build_crawl_command(platform: str, plan: KeywordPlan, max_notes_count: int) -> List[str]:
    return [
        "uv",
        "run",
        "python",
        "main.py",
        "--platform",
        platform,
        "--type",
        "search",
        "--keywords",
        plan.keyword,
        "--crawler_max_notes_count",
        str(max_notes_count),
        "--headless",
        "true",
        "--save_data_option",
        "jsonl",
    ]


def _default_executor(command: List[str], cwd: Path) -> None:
    subprocess.run(command, cwd=str(cwd), check=False, timeout=600)


def _iter_export_records(data_dir: Path, platform: str) -> Iterable[dict]:
    platform_dir = data_dir / platform
    jsonl_files = sorted(platform_dir.glob("**/*.jsonl")) if platform_dir.exists() else []
    for file_path in jsonl_files:
        with file_path.open("r", encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                try:
                    data = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if isinstance(data, dict):
                    yield data


def _plan_for_record(record: dict, plans: List[KeywordPlan]) -> KeywordPlan:
    source_keyword = str(record.get("source_keyword") or record.get("keyword") or "")
    for plan in plans:
        if source_keyword == plan.keyword:
            return plan
    return plans[0]

