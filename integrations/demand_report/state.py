# -*- coding: utf-8 -*-
"""Persistent deduplication state for demand reports."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Set


DEFAULT_DEMAND_STATE_PATH = Path(".sync_state") / "demand_excel_synced_hashes.json"


def load_hashes(path: Path = DEFAULT_DEMAND_STATE_PATH) -> Set[str]:
    """Load previously exported content hashes."""

    if not path.exists():
        return set()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return set()
    if not isinstance(data, list):
        return set()
    return {str(item) for item in data if item}


def save_hashes(hashes: Set[str], path: Path = DEFAULT_DEMAND_STATE_PATH) -> None:
    """Save exported content hashes as a stable sorted list."""

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(sorted(hashes), ensure_ascii=False, indent=2), encoding="utf-8")

