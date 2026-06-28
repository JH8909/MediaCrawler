# -*- coding: utf-8 -*-
"""Data models for the automated demand report workflow."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional


@dataclass(frozen=True)
class KeywordPlan:
    """A single keyword plan for one crawl task."""

    keyword: str
    domain: str
    demand_word: str


@dataclass
class DemandItem:
    """One extracted user demand row for the Excel report."""

    title: str
    raw_text: str
    content_type: str
    platform: str
    keyword: str
    domain: str
    demand_word: str
    source_url: str
    author: str
    publish_time: str
    collected_at: str
    content_hash: str
    remark: str = ""


@dataclass
class DemandReportStats:
    """Counters collected during one report run."""

    total_keywords: int = 0
    total_records: int = 0
    new_items: int = 0
    skipped_duplicates: int = 0
    failed_tasks: int = 0
    comment_items: int = 0
    body_items: int = 0


@dataclass
class DemandRunResult:
    """Result returned by the report runner and CLI."""

    dry_run: bool
    platforms: List[str]
    keyword_plans: List[KeywordPlan]
    stats: DemandReportStats
    excel_path: Optional[Path] = None
    logs: List[str] = field(default_factory=list)
    notification_sent: bool = False

