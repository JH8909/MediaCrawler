# -*- coding: utf-8 -*-
"""Schemas for automated demand report controls."""

from __future__ import annotations

from typing import List

from pydantic import BaseModel, Field


class AutoDemandConfig(BaseModel):
    interval: str = Field(default="6h", pattern="^(3h|6h|12h|day|week)$")
    platforms: List[str] = Field(default_factory=lambda: ["xhs", "tieba", "zhihu"])
    keyword_count: int = Field(default=3, ge=1, le=100)
    keyword_offset: int = Field(default=0, ge=0)
    max_notes_count: int = Field(default=15, ge=1, le=100)


class AutoDemandRunRequest(BaseModel):
    dry_run: bool = False

