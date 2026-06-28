# -*- coding: utf-8 -*-
"""Extract demand rows from MediaCrawler export records."""

from __future__ import annotations

import hashlib
import re
from datetime import datetime
from typing import Any, Dict, Optional

from .models import DemandItem, KeywordPlan


DEMAND_SIGNALS = (
    "求推荐",
    "避坑",
    "踩雷",
    "哪个好",
    "怎么选",
    "怎么买",
    "值不值",
    "预算",
    "平替",
    "后悔",
    "有没有必要",
    "攻略",
    "推荐一下",
    "真实体验",
    "注意事项",
    "?",
    "？",
)

COMMENT_FIELDS = ("comment_content", "comment_text", "comment", "content")
BODY_FIELDS = ("title", "desc", "description", "note_desc", "text")


def extract_demand_item(
    record: Dict[str, Any],
    keyword_plan: KeywordPlan,
    platform: str,
    collected_at: Optional[str] = None,
) -> Optional[DemandItem]:
    """Convert one export record into a demand item when it contains demand intent."""

    raw_text, content_type = _pick_text(record)
    if not raw_text or not _looks_like_demand(raw_text):
        return None

    source_url = _first_value(record, "note_url", "url", "source_url", "web_url", default="")
    author = _first_value(record, "nickname", "user_nickname", "author", "user_name", default="")
    publish_time = _first_value(record, "time", "publish_time", "last_modify_ts", "create_time", default="")
    collected_at = collected_at or datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    content_hash = _content_hash(platform=platform, source_url=source_url, raw_text=raw_text)

    return DemandItem(
        title=_make_title(raw_text),
        raw_text=raw_text,
        content_type=content_type,
        platform=platform,
        keyword=keyword_plan.keyword,
        domain=keyword_plan.domain,
        demand_word=keyword_plan.demand_word,
        source_url=source_url,
        author=author,
        publish_time=str(publish_time or ""),
        collected_at=collected_at,
        content_hash=content_hash,
    )


def _pick_text(record: Dict[str, Any]) -> tuple[str, str]:
    for field in COMMENT_FIELDS:
        value = str(record.get(field) or "").strip()
        if value:
            return value, "评论"

    parts = []
    for field in BODY_FIELDS:
        value = str(record.get(field) or "").strip()
        if value:
            parts.append(value)
    return " ".join(parts).strip(), "正文"


def _looks_like_demand(text: str) -> bool:
    chinese_chars = re.findall(r"[\u4e00-\u9fff]", text)
    if len(chinese_chars) < 6:
        return False
    return any(signal in text for signal in DEMAND_SIGNALS)


def _first_value(record: Dict[str, Any], *keys: str, default: str = "") -> str:
    for key in keys:
        value = record.get(key)
        if value:
            return str(value)
    return default


def _make_title(text: str) -> str:
    compact = re.sub(r"\s+", " ", text).strip()
    return compact[:32]


def _content_hash(platform: str, source_url: str, raw_text: str) -> str:
    value = platform + "|" + source_url + "|" + raw_text
    return hashlib.sha256(value.encode("utf-8")).hexdigest()

