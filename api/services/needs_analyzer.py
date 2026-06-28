# -*- coding: utf-8 -*-
"""Needs analyzer - classify user pain points and aggregate by frequency"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

try:
    import jieba
except ImportError:
    jieba = None


RULES_PATH = Path(__file__).resolve().parent.parent / "data" / "category_rules.json"

# Patterns to filter out meaningless chatter
_NOISE_PATTERNS = [
    re.compile(r"^[哈哈呵呵嘿嘿噗嗤]+$"),
    re.compile(r"^[666]+$"),
    re.compile(r"^[好看不错赞棒厉害]+$"),
    re.compile(r"^[。，！？\s]+$"),
    re.compile(r"^\d+$"),
    re.compile(r"^[😀-🙏🫠🫡🫢🫣🫤🫥🫨🫩🫪🫫🫬]+$"),
]


def load_rules() -> dict:
    if not RULES_PATH.exists():
        return {"categories": [], "settings": {}}
    with open(RULES_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def _is_noise(text: str) -> bool:
    """Check if text is meaningless chatter"""
    text = text.strip()
    if not text:
        return True
    # Single emoji / sticker reference
    if re.match(r"^\[.*?\]$", text):
        return True
    # Pure emoji / punctuation
    for pattern in _NOISE_PATTERNS:
        if pattern.fullmatch(text):
            return True
    # Too short (less than 4 meaningful chars)
    chinese_chars = len(re.findall(r"[\u4e00-\u9fff]", text))
    if chinese_chars < 4:
        return True
    return False


def _calculate_hot_score(record: Dict[str, Any], weights: Optional[Dict[str, float]] = None) -> float:
    """Calculate hot score from engagement metrics"""
    if weights is None:
        weights = {"like_weight": 0.3, "comment_weight": 0.5, "sub_comment_weight": 0.2}

    def _safe_float(val) -> float:
        if val is None or val == "":
            return 0.0
        try:
            val_str = str(val).replace(",", "").replace("万", "0000")
            return float(val_str)
        except (ValueError, TypeError):
            return 0.0

    like_count = _safe_float(record.get("liked_count", record.get("like_count", 0)))
    comment_count = _safe_float(record.get("comment_count", record.get("sub_comment_count", record.get("total_replay_num", 0))))
    sub_comment_count = _safe_float(record.get("sub_comment_count", 0))

    # Normalize: log scale to avoid extreme values dominating
    import math
    score = (
        weights["like_weight"] * math.log1p(like_count) +
        weights["comment_weight"] * math.log1p(comment_count) +
        weights["sub_comment_weight"] * math.log1p(sub_comment_count)
    )
    return round(score, 2)


def segment_text(text: str) -> List[str]:
    if not text or not jieba:
        return []
    return list(jieba.cut(text))


def classify_single(text: str, categories: List[dict], settings: dict) -> List[Dict[str, Any]]:
    if not text or len(text) < settings.get("min_chinese_chars", 5):
        return []
    tokens = segment_text(text)
    token_set = set(tokens)
    max_cats = settings.get("max_categories_per_item", 2)
    results = []
    for cat in categories:
        name = cat["name"]
        keywords = cat.get("keywords", [])
        matched = [kw for kw in keywords if kw in text]
        if not matched:
            matched = [kw for kw in keywords if kw in token_set]
        if matched and len(matched) >= settings.get("min_match_count", 1):
            confidence = min(1.0, len(matched) / max(len(keywords), 1) * 2)
            results.append({"category": name, "matched_keywords": matched, "confidence": round(confidence, 2)})
    results.sort(key=lambda x: x["confidence"], reverse=True)
    return results[:max_cats]


def _extract_text_from_record(record: Dict[str, Any]) -> str:
    """Extract meaningful text from a record, prioritizing comments content field."""
    # Comment records: content is the gold mine
    content = record.get("content", "") or ""
    if content and not _is_noise(content):
        return content

    # Content records: use title + desc
    title = record.get("title", "") or ""
    desc = record.get("desc", "") or ""
    text_parts = [p for p in [title, desc] if p and not _is_noise(p)]
    if text_parts:
        return " ".join(text_parts)

    # Fallback: any non-noise text field
    for field in ["text", "tag_list"]:
        val = record.get(field, "")
        if val and isinstance(val, str) and not _is_noise(val):
            return val
        elif val and isinstance(val, (list, tuple)):
            joined = " ".join(str(v) for v in val if v)
            if joined and not _is_noise(joined):
                return joined

    return ""


def analyze_records(records: List[Dict[str, Any]], text_fields: Optional[List[str]] = None) -> dict:
    rules = load_rules()
    categories = rules.get("categories", [])
    settings = rules.get("settings", {})
    hot_weights = settings.get("hot_score_weights", None)
    classified_records = []
    freq = {}
    hot_scores: Dict[str, float] = {}
    hit_counts: Dict[str, int] = {}  # How many records contributed to each category

    for record in records:
        full_text = _extract_text_from_record(record)
        if not full_text:
            continue

        cats = classify_single(full_text, categories, settings)
        if not cats:
            continue

        hot_score = _calculate_hot_score(record, hot_weights)
        enriched = dict(record)
        enriched["categories"] = [c["category"] for c in cats]
        enriched["category_details"] = cats
        enriched["hot_score"] = hot_score
        enriched["extracted_text"] = full_text[:200]
        classified_records.append(enriched)

        for c in cats:
            name = c["category"]
            freq[name] = freq.get(name, 0) + 1
            hot_scores[name] = hot_scores.get(name, 0) + hot_score
            hit_counts[name] = hit_counts.get(name, 0) + 1

    # Build aggregation with hot score
    aggregation = []
    for name, count in sorted(freq.items(), key=lambda x: -x[1]):
        avg_hot = round(hot_scores.get(name, 0) / max(hit_counts.get(name, 1), 1), 2)
        aggregation.append({
            "category": name,
            "count": count,
            "hot_score": avg_hot,
        })

    return {
        "classified_records": classified_records,
        "aggregation": aggregation,
        "total": len(records),
        "classified_count": len(classified_records),
    }


def load_jsonl(filepath: str) -> List[Dict[str, Any]]:
    records = []
    with open(filepath, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                records.append(json.loads(line))
    return records
