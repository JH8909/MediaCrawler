# -*- coding: utf-8 -*-
"""Pipeline manager - orchestrates one-click demand discovery flow.

Flow:
  1. Generate keyword plans from domain + demand words
  2. Run MediaCrawler CLI for each platform + keyword combo
  3. Wait for crawlers to complete
  4. Find newly created data files
  5. Run analysis + AI solution generation
  6. Send Feishu notification
"""

from __future__ import annotations

import asyncio
import json
import os
import subprocess
import traceback
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from integrations.demand_report.keywords import (
    DEFAULT_PLATFORMS,
    generate_keyword_plans,
    KeywordPlan,
)


# Project root directory
PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = PROJECT_ROOT / "data"
SYNC_STATE_DIR = PROJECT_ROOT / ".sync_state"


class PipelineManager:
    """Manages the one-click demand discovery pipeline"""

    def __init__(self):
        self._lock = asyncio.Lock()
        self._cancel_event = asyncio.Event()
        self.status = "idle"  # idle | running | completed | failed | cancelled
        self.started_at: Optional[datetime] = None
        self.completed_at: Optional[datetime] = None
        self.current_plan: Optional[Dict[str, Any]] = None
        self.last_result: Optional[Dict[str, Any]] = None
        self._logs: List[str] = []

    def _log(self, message: str) -> None:
        timestamp = datetime.now().strftime("%H:%M:%S")
        line = f"[{timestamp}] {message}"
        self._logs.append(line)
        print(f"[Pipeline] {line}")

    @property
    def logs(self) -> List[str]:
        return self._logs[-200:]  # Keep last 200 lines

    def clear_logs(self) -> None:
        """Clear all stored logs."""
        self._logs = []

    async def stop(self) -> None:
        """Request pipeline cancellation."""
        self._cancel_event.set()
        self._log("Cancellation requested, will stop after current task completes")

    async def start(
        self,
        platforms: Optional[List[str]] = None,
        keyword_count: int = 3,
        keyword_offset: int = 0,
        max_notes: int = 15,
    ) -> Dict[str, Any]:
        """Start the one-click pipeline"""
        async with self._lock:
            if self.status == "running":
                return {"status": "error", "message": "Pipeline already running"}

            self.status = "running"
            self.started_at = datetime.now()
            self._logs = []
            self._log("Pipeline started")

        try:
            self._cancel_event.clear()

            # Step 1: Generate keyword plans
            self._log(f"Generating {keyword_count} keyword plans (offset={keyword_offset})...")
            plans = generate_keyword_plans(count=keyword_count, offset=keyword_offset)
            self._log(f"Keywords: {[p.keyword for p in plans]}")

            if platforms is None:
                platforms = DEFAULT_PLATFORMS

            # Step 2: Run MediaCrawler for each platform
            all_new_files = []
            total_tasks = len(platforms) * len(plans)
            completed_tasks = 0

            for platform in platforms:
                if self._cancel_event.is_set():
                    self._log("Pipeline cancelled by user")
                    break
                for plan in plans:
                    if self._cancel_event.is_set():
                        self._log("Pipeline cancelled by user")
                        break
                    self._log(f"[{platform}] Crawling: {plan.keyword}")
                    try:
                        new_files = await self._run_single_crawl(platform, plan, max_notes)
                        all_new_files.extend(new_files)
                    except asyncio.CancelledError:
                        self._log(f"[{platform}] Cancelled: {plan.keyword}")
                        raise
                    except Exception as exc:
                        self._log(f"[{platform}] Failed: {plan.keyword} - {exc}")

                    completed_tasks += 1
                    self._log(f"Progress: {completed_tasks}/{total_tasks}")
                if self._cancel_event.is_set():
                    break

            if self._cancel_event.is_set():
                result = {
                    "status": "cancelled",
                    "total_files": len(all_new_files),
                    "message": "Pipeline was cancelled by user",
                    "files": [str(f.relative_to(PROJECT_ROOT)) for f in all_new_files],
                    "analysis": None,
                }
            elif not all_new_files:
                self._log("No new data files found, analysis skipped")
                result = {
                    "status": "completed",
                    "total_files": 0,
                    "message": "采集完成，但未发现新数据文件",
                    "files": [],
                    "analysis": None,
                }
            else:
                # Step 3: Analyze new files
                self._log(f"Analyzing {len(all_new_files)} new data files...")
                analysis_results = []
                for file_path in all_new_files[:5]:  # Analyze up to 5 files
                    try:
                        result = await self._analyze_file(file_path)
                        analysis_results.append(result)
                    except Exception as exc:
                        self._log(f"Analysis failed for {file_path.name}: {exc}")
                        self._log(traceback.format_exc())

                # Step 4: Send notification (handled by analyze endpoint)
                self._log(f"Analysis complete: {len(analysis_results)} files processed")

                result = {
                    "status": "completed",
                    "total_files": len(all_new_files),
                    "files": [str(f.relative_to(PROJECT_ROOT)) for f in all_new_files],
                    "analysis": analysis_results,
                    "message": f"采集完成，发现 {len(all_new_files)} 个新文件，已分析 {len(analysis_results)} 个",
                }

            self.last_result = result
            self.status = "completed"
            self.completed_at = datetime.now()
            self._log("Pipeline completed successfully")
            return result

        except Exception as exc:
            self.status = "failed"
            self._log(f"Pipeline failed: {exc}")
            return {"status": "failed", "message": str(exc)}

    def get_status(self) -> Dict[str, Any]:
        """Get current pipeline status"""
        return {
            "status": self.status,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "logs": self.logs[-50:],
            "last_result": self.last_result or {},
        }

    async def _run_single_crawl(
        self,
        platform: str,
        plan: KeywordPlan,
        max_notes: int,
    ) -> List[Path]:
        """Run MediaCrawler CLI for a single platform + keyword combination"""
        # Record existing data files before crawl
        existing_files = set(self._find_data_files(platform))

        # Build the CLI command
        cmd = [
            "uv", "run", "python", "-u", "main.py",
            "--platform", platform,
            "--type", "search",
            "--keywords", plan.keyword,
            "--crawler_max_notes_count", str(max_notes),
            "--headless", "true",
            "--save_data_option", "jsonl",
        ]

        self._log(f"  Running: {' '.join(cmd)}")
        crawl_env = dict(os.environ)
        crawl_env["PYTHONUNBUFFERED"] = "1"
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd=str(PROJECT_ROOT),
            env=crawl_env,
        )
        stdout_task = asyncio.create_task(self._read_process_stream(process.stdout, "stdout"))
        stderr_task = asyncio.create_task(self._read_process_stream(process.stderr, "stderr"))

        try:
            await asyncio.wait_for(
                process.wait(), timeout=300.0  # 5 min timeout per crawl
            )
            if process.returncode != 0:
                self._log(f"  Crawler exited with code {process.returncode}")
        except asyncio.TimeoutError:
            process.kill()
            await process.wait()
            self._log(f"  Crawler timed out after 300s")
        finally:
            await asyncio.gather(stdout_task, stderr_task, return_exceptions=True)

        # Find new files created by this crawl
        new_files = []
        for f in self._find_data_files(platform):
            if f not in existing_files:
                new_files.append(f)

        if new_files:
            self._log(f"  Created {len(new_files)} file(s): {[f.name for f in new_files]}")
        else:
            self._log(f"  No new files detected (may have appended to existing)")

        return new_files

    async def _read_process_stream(self, stream: asyncio.StreamReader, label: str) -> None:
        """Forward child process output into pipeline logs as it arrives."""
        if stream is None:
            return
        while True:
            line = await stream.readline()
            if not line:
                break
            text = line.decode("utf-8", errors="ignore").strip()
            if text:
                self._log(f"  {label}: {text[-300:]}")

    def _find_data_files(self, platform: str) -> List[Path]:
        """Find JSONL data files for a specific platform"""
        platform_dir = DATA_DIR / platform / "jsonl"
        if not platform_dir.exists():
            return []
        return sorted(platform_dir.glob("*.jsonl"))

    async def _analyze_file(self, file_path: Path) -> Dict[str, Any]:
        """Run analysis on a single data file using existing API logic"""
        import json as _json
        from api.services.needs_analyzer import analyze_records
        from api.services.solution_generator import generate_all_solutions
        from api.services.dedup_filter import llm_dedup_records

        # Load records
        records = []
        with open(file_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    records.append(_json.loads(line))

        if not records:
            return {"file": str(file_path), "total": 0, "categories": 0}

        # Step 0: LLM dedup before classification
        orig_count = len(records)
        deduped_records, removed_count = llm_dedup_records(records)
        if removed_count > 0:
            self._log(f"  LLM dedup: {orig_count} -> {len(deduped_records)} ({removed_count} removed)")

        # Classify and aggregate (run in thread to avoid blocking event loop)
        self._log(f"  Analyzing {len(deduped_records)} records from {file_path.name}...")
        analysis = await asyncio.to_thread(analyze_records, deduped_records)
        agg = analysis.get("aggregation", [])
        classified = analysis.get("classified_records", [])
        self._log(f"  Found {len(agg)} categories, {len(classified)} classified records")

        # Generate AI solutions (run in thread — may call LLM API)
        solutions_data = []
        if agg:
            self._log(f"  Generating AI solutions for top {min(len(agg), 5)} categories...")
            try:
                sol_result = await asyncio.to_thread(
                    generate_all_solutions,
                    aggregation=agg,
                    classified_records=classified,
                    max_categories=5,
                )
                solutions_data = sol_result.get("solutions", [])
                self._log(f"  Generated {len(solutions_data)} solution sets")
            except Exception as exc:
                self._log(f"  Solution generation failed: {exc}")

        # Load category rules (used by both webhook and report persistence)
        cat_rules = {}
        rules_path = Path(__file__).resolve().parents[1] / "data" / "category_rules.json"
        if rules_path.exists():
            try:
                with open(rules_path, "r", encoding="utf-8") as f_rules:
                    cat_rules = _json.load(f_rules)
            except Exception:
                pass

        platform_name = file_path.parent.parent.name
        first_keyword = records[0].get("source_keyword", "") if records else ""

        # Send Feishu notification (run in thread — HTTP request)
        webhook_sent = False
        try:
            from integrations.feishu_webhook import send_demand_report, get_webhook_url
            wu = get_webhook_url()
            if wu and agg:
                webhook_sent = await asyncio.to_thread(
                    send_demand_report,
                    aggregation=agg,
                    solutions_data=solutions_data,
                    keyword=first_keyword,
                    platform=platform_name,
                    total=len(deduped_records),
                    classified_records=classified,
                    category_rules=cat_rules,
                    webhook_url=wu,
                )
                self._log(f"  Feishu analysis report sent: {webhook_sent}")
        except Exception as exc:
            self._log(f"  Feishu notification failed: {exc}")

        # Persist report + push to frontend via WebSocket (always save)
        try:
            from api.services.report_store import save_report
            from api.routers.websocket import broadcast_analysis_report
            report_data = save_report(
                platform=platform_name,
                keyword=first_keyword,
                total=len(deduped_records),
                aggregation=agg or [],
                classified_records=classified or [],
                solutions_data=solutions_data or [],
                webhook_sent=webhook_sent,
            )
            await broadcast_analysis_report(report_data)
            self._log(f"  Report saved & pushed: {len(agg or [])} categories")
        except Exception as rpt_exc:
            self._log(f"  Report save/push: {rpt_exc}")

        return {
            "file": str(file_path.relative_to(PROJECT_ROOT)),
            "total": len(deduped_records),
            "categories": len(agg),
            "aggregation": agg[:20],
            "solutions": len(solutions_data),
            "solutions_data": solutions_data,
            "webhook_sent": webhook_sent,
        }


# Singleton
pipeline_manager = PipelineManager()
