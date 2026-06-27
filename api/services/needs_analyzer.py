# -*- coding: utf-8 -*-
"""Needs analyzer - classify user pain points and aggregate by frequency"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

try:
    import jieba
except ImportError:
    jieba = None


RULES_PATH = Path(__file__).resolve().parent.parent / "data" / "category_rules.json"


def load_rules() -> dict:
    if not RULES_PATH.exists():
        return {"categories": [], "settings": {}}
    with open(RULES_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def segment_text(text: str) -> List[str]:
    if not text or not jieba:
        return []
    return list(jieba.cut(text))


def classify_single(text: str, categories: List[dict], settings: dict) -> List[Dict[str, Any]]:
    if not text or len(text) < settings.get("min_chinese_chars", 5):
        return []
    tokens = segment_text(text)
    token_set = set(tokens)
    max_cats = settings.get("max_categories_per_item", 3)
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


def analyze_records(records: List[Dict[str, Any]], text_fields: Optional[List[str]] = None) -> dict:
    if text_fields is None:
        text_fields = ["title", "desc", "tag_list", "content", "text"]
    rules = load_rules()
    categories = rules.get("categories", [])
    settings = rules.get("settings", {})
    classified_records = []
    freq = {}
    for record in records:
        texts = []
        for field in text_fields:
            val = record.get(field, "")
            if val and isinstance(val, str):
                texts.append(val)
            elif val and isinstance(val, (list, tuple)):
                texts.extend(str(v) for v in val)
        full_text = " ".join(texts)
        cats = classify_single(full_text, categories, settings)
        enriched = dict(record)
        enriched["categories"] = [c["category"] for c in cats]
        enriched["category_details"] = cats
        classified_records.append(enriched)
        for c in cats:
            freq[c["category"]] = freq.get(c["category"], 0) + 1
    aggregation = [{"category": name, "count": count} for name, count in sorted(freq.items(), key=lambda x: -x[1])]
    return {"classified_records": classified_records, "aggregation": aggregation, "total": len(records)}


def load_jsonl(filepath: str) -> List[Dict[str, Any]]:
    records = []
    with open(filepath, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                records.append(json.loads(line))
    return records
