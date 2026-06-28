# -*- coding: utf-8 -*-
# Copyright (c) 2025 relakkes@gmail.com
#
# This file is part of MediaCrawler project.
# Repository: https://github.com/NanmiCoder/MediaCrawler/blob/main/api/services/crawler_manager.py
# GitHub: https://github.com/NanmiCoder
# Licensed under NON-COMMERCIAL LEARNING LICENSE 1.1
#
# 声明：本代码仅供学习和研究目的使用。使用者应遵守以下原则：
# 1. 不得用于任何商业用途。
# 2. 使用时应遵守目标平台的使用条款和robots.txt规则。
# 3. 不得进行大规模爬取或对平台造成运营干扰。
# 4. 应合理控制请求频率，避免给目标平台带来不必要的负担。
# 5. 不得用于任何非法或不当的用途。
#
# 详细许可条款请参阅项目根目录下的LICENSE文件。
# 使用本代码即表示您同意遵守上述原则和LICENSE中的所有条款。

import asyncio
import subprocess
import signal
import os
from typing import Optional, List
from datetime import datetime
from pathlib import Path
from integrations.feishu_webhook import send_crawl_summary, get_webhook_url, send_requirements_doc

from ..schemas import CrawlerStartRequest, LogEntry


class CrawlerManager:
    """Crawler process manager"""

    def __init__(self):
        self._lock = asyncio.Lock()
        self.process: Optional[subprocess.Popen] = None
        self.status = "idle"
        self.started_at: Optional[datetime] = None
        self.current_config: Optional[CrawlerStartRequest] = None
        self._log_id = 0
        self._logs: List[LogEntry] = []
        self._read_task: Optional[asyncio.Task] = None
        # Project root directory
        self._project_root = Path(__file__).parent.parent.parent
        # Log queue - for pushing to WebSocket
        self._log_queue: Optional[asyncio.Queue] = None

    @property
    def logs(self) -> List[LogEntry]:
        return self._logs

    def clear_logs(self) -> None:
        """Clear all stored logs and reset log id counter."""
        self._logs = []
        self._log_id = 0
        if self._log_queue is not None:
            try:
                while True:
                    self._log_queue.get_nowait()
            except asyncio.QueueEmpty:
                pass

    def get_log_queue(self) -> asyncio.Queue:
        """Get or create log queue"""
        if self._log_queue is None:
            self._log_queue = asyncio.Queue()
        return self._log_queue

    def _create_log_entry(self, message: str, level: str = "info") -> LogEntry:
        """Create log entry"""
        self._log_id += 1
        entry = LogEntry(
            id=self._log_id,
            timestamp=datetime.now().strftime("%H:%M:%S"),
            level=level,
            message=message
        )
        self._logs.append(entry)
        # Keep last 500 logs
        if len(self._logs) > 500:
            self._logs = self._logs[-500:]
        return entry

    async def _push_log(self, entry: LogEntry):
        """Push log to queue"""
        if self._log_queue is not None:
            try:
                self._log_queue.put_nowait(entry)
            except asyncio.QueueFull:
                pass

    def _parse_log_level(self, line: str) -> str:
        """Parse log level"""
        line_upper = line.upper()
        if "ERROR" in line_upper or "FAILED" in line_upper:
            return "error"
        elif "WARNING" in line_upper or "WARN" in line_upper:
            return "warning"
        elif "SUCCESS" in line_upper or "完成" in line or "成功" in line:
            return "success"
        elif "DEBUG" in line_upper:
            return "debug"
        return "info"

    async def start(self, config: CrawlerStartRequest) -> bool:
        """Start crawler process"""
        async with self._lock:
            if self.process and self.process.poll() is None:
                return False

            # Clear old logs
            self._logs = []
            self._log_id = 0

            # Clear pending queue (don't replace object to avoid WebSocket broadcast coroutine holding old queue reference)
            if self._log_queue is None:
                self._log_queue = asyncio.Queue()
            else:
                try:
                    while True:
                        self._log_queue.get_nowait()
                except asyncio.QueueEmpty:
                    pass

            # Build command line arguments
            cmd = self._build_command(config)

            # Log start information
            entry = self._create_log_entry(f"Starting crawler: {' '.join(cmd)}", "info")
            await self._push_log(entry)

            try:
                # Start subprocess
                self.process = subprocess.Popen(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    encoding='utf-8',
                    bufsize=1,
                    cwd=str(self._project_root),
                    env={**os.environ, "PYTHONUNBUFFERED": "1"}
                )

                self.status = "running"
                self.started_at = datetime.now()
                self.current_config = config

                entry = self._create_log_entry(
                    f"Crawler started on platform: {config.platform.value}, type: {config.crawler_type.value}",
                    "success"
                )
                await self._push_log(entry)

                # Start log reading task
                self._read_task = asyncio.create_task(self._read_output())

                return True
            except Exception as e:
                self.status = "error"
                entry = self._create_log_entry(f"Failed to start crawler: {str(e)}", "error")
                await self._push_log(entry)
                return False

    async def stop(self) -> bool:
        """Stop crawler process"""
        async with self._lock:
            if not self.process or self.process.poll() is not None:
                return False

            self.status = "stopping"
            entry = self._create_log_entry("Sending SIGTERM to crawler process...", "warning")
            await self._push_log(entry)

            try:
                self.process.send_signal(signal.SIGTERM)

                # Wait for graceful exit (up to 15 seconds)
                for _ in range(30):
                    if self.process.poll() is not None:
                        break
                    await asyncio.sleep(0.5)

                # If still not exited, force kill
                if self.process.poll() is None:
                    entry = self._create_log_entry("Process not responding, sending SIGKILL...", "warning")
                    await self._push_log(entry)
                    self.process.kill()

                entry = self._create_log_entry("Crawler process terminated", "info")
                await self._push_log(entry)

            except Exception as e:
                entry = self._create_log_entry(f"Error stopping crawler: {str(e)}", "error")
                await self._push_log(entry)

            self.status = "idle"
            self.current_config = None

            # Cancel log reading task
            if self._read_task:
                self._read_task.cancel()
                self._read_task = None

            return True

    def get_status(self) -> dict:
        """Get current status"""
        return {
            "status": self.status,
            "platform": self.current_config.platform.value if self.current_config else None,
            "crawler_type": self.current_config.crawler_type.value if self.current_config else None,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "error_message": None
        }

    def _build_command(self, config: CrawlerStartRequest) -> list:
        """Build main.py command line arguments"""
        cmd = ["uv", "run", "python", "main.py"]

        cmd.extend(["--platform", config.platform.value])
        cmd.extend(["--lt", config.login_type.value])
        cmd.extend(["--type", config.crawler_type.value])
        cmd.extend(["--save_data_option", config.save_option.value])

        # Pass different arguments based on crawler type
        if config.crawler_type.value == "search" and config.keywords:
            cmd.extend(["--keywords", config.keywords])
        elif config.crawler_type.value == "detail" and config.specified_ids:
            cmd.extend(["--specified_id", config.specified_ids])
        elif config.crawler_type.value == "creator" and config.creator_ids:
            cmd.extend(["--creator_id", config.creator_ids])

        if config.start_page != 1:
            cmd.extend(["--start", str(config.start_page)])

        cmd.extend(["--get_comment", "true" if config.enable_comments else "false"])
        cmd.extend(["--get_sub_comment", "true" if config.enable_sub_comments else "false"])

        if config.max_notes_count is not None:
            cmd.extend(["--crawler_max_notes_count", str(config.max_notes_count)])

        if config.max_comments_count is not None:
            cmd.extend(["--max_comments_count_singlenotes", str(config.max_comments_count)])

        if config.cookies:
            cmd.extend(["--cookies", config.cookies])

        cmd.extend(["--headless", "true" if config.headless else "false"])

        return cmd

    async def _read_output(self):
        """Asynchronously read process output"""
        loop = asyncio.get_event_loop()

        try:
            while self.process and self.process.poll() is None:
                # Read a line in thread pool
                line = await loop.run_in_executor(
                    None, self.process.stdout.readline
                )
                if line:
                    line = line.strip()
                    if line:
                        level = self._parse_log_level(line)
                        entry = self._create_log_entry(line, level)
                        await self._push_log(entry)

            # Read remaining output
            if self.process and self.process.stdout:
                remaining = await loop.run_in_executor(
                    None, self.process.stdout.read
                )
                if remaining:
                    for line in remaining.strip().split('\n'):
                        if line.strip():
                            level = self._parse_log_level(line)
                            entry = self._create_log_entry(line.strip(), level)
                            await self._push_log(entry)

            # Process ended
            if self.status == "running":
                exit_code = self.process.returncode if self.process else -1
                if exit_code == 0:
                    entry = self._create_log_entry("Crawler completed successfully", "success")
                    await self._push_log(entry)

                    # === Full pipeline: analyze + AI solutions + Feishu output ===
                    try:
                        pf = self.current_config.platform.value if self.current_config else "unknown"
                        kw = self.current_config.keywords if self.current_config else ""

                        import json as _json
                        dd = self._project_root / "data" / pf / "jsonl"
                        records = []
                        if dd.exists():
                            fs = sorted(dd.glob("search_contents_*.jsonl"), reverse=True)
                            if fs:
                                with open(fs[0], "r", encoding="utf-8") as fh:
                                    for ln in fh:
                                        ln = ln.strip()
                                        if ln:
                                            try:
                                                records.append(_json.loads(ln))
                                            except Exception:
                                                pass

                        rcount = len(records)
                        we = self._create_log_entry(f"Loaded {rcount} records for analysis", "info")
                        await self._push_log(we)

                        if rcount > 0:
                            from api.services.needs_analyzer import analyze_records
                            analysis = analyze_records(records)
                            agg = analysis.get("aggregation", [])
                            classified = analysis.get("classified_records", [])
                            we = self._create_log_entry(f"Analysis: {len(agg)} categories", "info")
                            await self._push_log(we)

                            solutions_data = []
                            llm_key = os.environ.get("LLM_API_KEY", "")
                            if llm_key:
                                try:
                                    from api.services.solution_generator import generate_all_solutions
                                    sol_result = generate_all_solutions(
                                        aggregation=agg, classified_records=classified,
                                        api_key=llm_key,
                                        api_url=os.environ.get("LLM_API_URL", "https://api.deepseek.com/v1/chat/completions"),
                                        model=os.environ.get("LLM_MODEL", "deepseek-v4-flash"),
                                        max_categories=5,
                                    )
                                    solutions_data = sol_result.get("solutions", [])
                                    we = self._create_log_entry(f"AI solutions: {len(solutions_data)} categories", "info")
                                    await self._push_log(we)
                                except Exception as sol_exc:
                                    we = self._create_log_entry(f"Solution gen: {sol_exc}", "warning")
                                    await self._push_log(we)

                            items = []
                            for r in records[:5]:
                                items.append({"title": r.get("title",""), "desc": r.get("desc","")[:80], "nickname": r.get("nickname",""), "likes": r.get("liked_count","0"), "url": r.get("note_url","")})

                            wu = get_webhook_url()
                            if wu:
                                ct = self.current_config.crawler_type.value if self.current_config else "unknown"
                                summary_sent = send_crawl_summary(
                                    platform=pf,
                                    crawler_type=ct,
                                    keywords=kw,
                                    stats={"success": rcount, "skipped": 0, "failed": 0},
                                    content_items=items[:5],
                                    webhook_url=wu,
                                )
                                we = self._create_log_entry(
                                    "Summary sent" if summary_sent else "Summary send failed",
                                    "info" if summary_sent else "warning",
                                )
                                await self._push_log(we)
                                if agg:
                                    analysis_sent = send_analysis_report(aggregation=agg, solutions_data=solutions_data, keyword=kw, platform=pf, total=rcount, webhook_url=wu)
                                    we = self._create_log_entry(
                                        "Analysis report sent" if analysis_sent else "Analysis report send failed",
                                        "success" if analysis_sent else "warning",
                                    )
                                    await self._push_log(we)

                    except Exception as pipe_exc:
                        we = self._create_log_entry(f"Pipeline: {pipe_exc}", "error")
                        await self._push_log(we)
                else:
                    entry = self._create_log_entry(f"Crawler exited with code: {exit_code}", "warning")
                    # Send failure webhook
                    try:
                        wu = get_webhook_url()
                        if wu:
                            pf = self.current_config.platform.value if self.current_config else "unknown"
                            ct = self.current_config.crawler_type.value if self.current_config else "unknown"
                            kw = self.current_config.keywords if self.current_config else ""
                            from integrations.feishu_webhook import send_simple_message
                            failure_sent = send_simple_message(title="Collection Failed", content=f"Platform: {pf} | Type: {ct} | Keyword: {kw}", template="red", webhook_url=wu)
                            we = self._create_log_entry(
                                "Failure webhook sent" if failure_sent else "Failure webhook send failed",
                                "warning",
                            )
                            await self._push_log(we)
                    except Exception:
                        pass
                await self._push_log(entry)
                self.status = "idle"

        except asyncio.CancelledError:
            pass
        except Exception as e:
            entry = self._create_log_entry(f"Error reading output: {str(e)}", "error")
            await self._push_log(entry)


# Global singleton
crawler_manager = CrawlerManager()
