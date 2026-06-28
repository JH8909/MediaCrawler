# -*- coding: utf-8 -*-
"""In-process manager for automated demand report runs."""

from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Any, Dict, List

from api.schemas.auto_demand import AutoDemandConfig
from integrations.demand_report.runner import PROJECT_ROOT, run_auto_demand_report


CONFIG_PATH = PROJECT_ROOT / ".sync_state" / "auto_demand_config.json"


class AutoDemandManager:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._running = False
        self._logs: List[str] = []
        self._last_result: Dict[str, Any] | None = None
        self._config = self._load_config()

    def get_status(self) -> Dict[str, Any]:
        return {
            "running": self._running,
            "config": self._config.model_dump(),
            "logs": self._logs[-100:],
            "last_result": self._last_result,
        }

    def save_config(self, config: AutoDemandConfig) -> AutoDemandConfig:
        CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
        CONFIG_PATH.write_text(config.model_dump_json(indent=2), encoding="utf-8")
        self._config = config
        return config

    def run_once(self, dry_run: bool = False) -> Dict[str, Any]:
        with self._lock:
            if self._running:
                return {"status": "running", "message": "auto demand task already running"}
            self._running = True
        try:
            result = run_auto_demand_report(
                platforms=self._config.platforms,
                keyword_count=self._config.keyword_count,
                keyword_offset=self._config.keyword_offset,
                max_notes_count=self._config.max_notes_count,
                dry_run=dry_run,
            )
            data = {
                "dry_run": result.dry_run,
                "platforms": result.platforms,
                "keywords": [plan.keyword for plan in result.keyword_plans],
                "stats": result.stats.__dict__,
                "excel_path": str(result.excel_path) if result.excel_path else "",
                "notification_sent": result.notification_sent,
            }
            self._logs.extend(result.logs)
            self._last_result = data
            return {"status": "ok", "result": data}
        finally:
            self._running = False

    def _load_config(self) -> AutoDemandConfig:
        if not CONFIG_PATH.exists():
            return AutoDemandConfig()
        try:
            data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
            return AutoDemandConfig(**data)
        except Exception:
            return AutoDemandConfig()


auto_demand_manager = AutoDemandManager()

