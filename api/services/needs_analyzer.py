# -*- coding: utf-8 -*-
"""Needs analyzer - classify user pain points and aggregate by frequency"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

try:
    import httpx
except ImportError:
    httpx = None

try:
    import jieba
except ImportError:
    jieba = None

from tools.utils import logger


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


# ── LLM-based semantic classification ──

_LLM_CLASSIFY_PROMPT = """你是一个用户需求分类专家。给定一段用户内容，判断它属于以下哪个（些）类别。

内容："{text}"

可选类别：
{categories_desc}

规则：
1. 只选择内容**明确涉及**的类别，最多选 {max_cats} 个
2. 如果内容不明确属于任何类别，返回空列表
3. 对每个选中的类别，给出 0-1 的置信度
4. 只返回 JSON 数组，格式：[{{"category": "类别名", "confidence": 0.8}}]
5. 不要返回任何其他文字"""


def llm_classify_single(
    text: str,
    categories: List[dict],
    settings: dict,
    api_key: str = "",
    api_url: str = "",
    model: str = "",
) -> List[Dict[str, Any]]:
    """Use LLM to semantically classify a single record into categories."""
    if not text or not api_key or not httpx:
        return []

    max_cats = settings.get("max_categories_per_item", 3)
    cat_descs = "\n".join(
        f"- {c['name']}: {c.get('description', '')}"
        for c in categories
        if c.get("name") != "其他需求 & 未分类"
    )

    prompt = _LLM_CLASSIFY_PROMPT.format(
        text=text[:400],
        categories_desc=cat_descs,
        max_cats=max_cats,
    )

    try:
        api_url = api_url or os.getenv("LLM_API_URL", "https://api.deepseek.com/v1/chat/completions")
        model = model or os.getenv("LLM_MODEL", "deepseek-v4-flash")

        with httpx.Client(timeout=30) as client:
            resp = client.post(
                api_url,
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": model,
                    "messages": [
                        {"role": "system", "content": "你是一个用户需求分类专家。只输出 JSON，不要任何其他文字。"},
                        {"role": "user", "content": prompt},
                    ],
                    "temperature": 0.1,
                    "max_tokens": 500,
                },
            )
            resp.raise_for_status()
            data = resp.json()
            content_text = data["choices"][0]["message"]["content"]
            cleaned = content_text.strip()
            if cleaned.startswith("```"):
                cleaned = cleaned.split("\n", 1)[-1]
                if "```" in cleaned:
                    cleaned = cleaned.rsplit("```", 1)[0]
            if cleaned.startswith("```json"):
                cleaned = cleaned[7:].strip()
                if cleaned.endswith("```"):
                    cleaned = cleaned[:-3].strip()
            result = json.loads(cleaned)
            if isinstance(result, list):
                return [
                    {"category": r["category"], "confidence": r.get("confidence", 0.5)}
                    for r in result
                ]
    except Exception as exc:
        logger.warning(f"[LLMClassifier] Classification failed for text: {exc}")

    return []


def llm_batch_classify(
    texts_with_indices: List[Tuple[int, str]],
    categories: List[dict],
    settings: dict,
    api_key: str = "",
    api_url: str = "",
    model: str = "",
) -> Dict[int, List[Dict[str, Any]]]:
    """Batch-classify multiple records using a single LLM call.

    Returns dict mapping original index -> list of classification results.
    """
    if not texts_with_indices or not api_key or not httpx:
        return {}

    max_cats = settings.get("max_categories_per_item", 3)
    cat_descs = "\n".join(
        f"- {c['name']}: {c.get('description', '')}"
        for c in categories
        if c.get("name") != "其他需求 & 未分类"
    )

    items_text = "\n\n".join(
        f"[{idx}] {text[:200]}"
        for idx, text in texts_with_indices
    )

    prompt = f"""你是用户需求分类专家。下面有{len(texts_with_indices)}条用户内容，请逐一分类。

可选类别：
{cat_descs}

内容列表：
{items_text}

规则：
1. 为每一条内容最多选择 {max_cats} 个最相关的类别
2. 如果内容不明确属于任何类别，给它分配"其他需求 & 未分类"
3. 对每个选中类别给出0-1置信度
4. 只返回JSON数组，格式：[{{"index": 0, "classifications": [{{"category": "类别名", "confidence": 0.8}}]}}]
5. index 必须与内容前的[数字]对应
6. 不要返回任何其他文字"""

    try:
        api_url = api_url or os.getenv("LLM_API_URL", "https://api.deepseek.com/v1/chat/completions")
        model = model or os.getenv("LLM_MODEL", "deepseek-v4-flash")

        with httpx.Client(timeout=90) as client:
            resp = client.post(
                api_url,
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": model,
                    "messages": [
                        {"role": "system", "content": "你是一个用户需求分类专家。只输出 JSON，不要任何其他文字。"},
                        {"role": "user", "content": prompt},
                    ],
                    "temperature": 0.1,
                    "max_tokens": 3000,
                },
            )
            resp.raise_for_status()
            data = resp.json()
            content_text = data["choices"][0]["message"]["content"]
            cleaned = content_text.strip()
            if cleaned.startswith("```"):
                cleaned = cleaned.split("\n", 1)[-1]
                if "```" in cleaned:
                    cleaned = cleaned.rsplit("```", 1)[0]
            if cleaned.startswith("```json"):
                cleaned = cleaned[7:].strip()
                if cleaned.endswith("```"):
                    cleaned = cleaned[:-3].strip()
            result = json.loads(cleaned)
            if isinstance(result, list):
                try:
                    mapping = {}
                    for item in result:
                        if not isinstance(item, dict):
                            continue
                        idx = item.get("index", len(mapping))
                        if isinstance(idx, str) and idx.isdigit():
                            idx = int(idx)
                        elif not isinstance(idx, int):
                            idx = len(mapping)
                        mapping[idx] = item.get("classifications", [])
                    return mapping
                except Exception as idx_exc:
                    logger.warning(f"[LLMClassifier] Index extraction failed: {idx_exc}, result={json.dumps(result, ensure_ascii=False)[:300]}")
    except Exception as exc:
        logger.warning(f"[LLMClassifier] Batch classification failed: {exc}")

    return {}


def classify_single(text: str, categories: List[dict], settings: dict) -> List[Dict[str, Any]]:
    """Keyword-based classification using token (jieba) matching primarily.

    Substring matching (`kw in text`) is ONLY used as a fallback when jieba is unavailable.
    This prevents single-character keywords like '找' from matching everywhere.
    """
    if not text or len(text) < settings.get("min_chinese_chars", 10):
        return []
    tokens = segment_text(text)
    token_set = set(tokens) if tokens else set()
    min_match = settings.get("min_match_count", 2)
    max_cats = settings.get("max_categories_per_item", 3)
    orig_text = text  # keep original for substring fallback
    results = []
    for cat in categories:
        name = cat["name"]
        keywords = cat.get("keywords", [])
        # Skip "其他需求" fallback category during matching
        if not keywords or name == "其他需求 & 未分类":
            continue
        # Primary: token-set matching (jieba tokens ∩ keywords)
        # This ensures word boundary accuracy — "找" won't match "找到" unless it's a separate token
        matched = []
        if token_set:
            matched = [kw for kw in keywords if kw in token_set]
        # Fallback: substring matching only when jieba is unavailable
        if not matched and not token_set:
            matched = [kw for kw in keywords if kw in orig_text]
        if matched and len(matched) >= min_match:
            confidence = min(1.0, len(matched) / max(len(keywords), 1) * 2)
            results.append({"category": name, "matched_keywords": matched[:5], "confidence": round(confidence, 2)})
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


def analyze_records(
    records: List[Dict[str, Any]],
    text_fields: Optional[List[str]] = None,
    use_llm: bool = True,
) -> dict:
    """Analyze records: extract text, classify into categories, calculate hot scores.

    With use_llm=True and LLM_API_KEY set, uses LLM for semantic classification
    (much more accurate for non-tech content like food/lifestyle posts).
    Falls back to keyword matching when LLM is unavailable.
    Records that match no category are placed in "其他需求 & 未分类".
    """
    rules = load_rules()
    categories = rules.get("categories", [])
    settings = rules.get("settings", {})
    hot_weights = settings.get("hot_score_weights", None)
    classified_records = []
    freq = {}
    hot_scores: Dict[str, float] = {}
    hit_counts: Dict[str, int] = {}

    # Pre-extract text for all records
    texts_with_records: List[Tuple[int, str, dict]] = []
    for i, record in enumerate(records):
        full_text = _extract_text_from_record(record)
        if full_text:
            texts_with_records.append((i, full_text, record))

    # Try LLM batch classification
    llm_api_key = os.environ.get("LLM_API_KEY", "")
    llm_results: Dict[int, List[Dict[str, Any]]] = {}

    if use_llm and llm_api_key:
        try:
            llm_batch_size = 30
            for batch_start in range(0, len(texts_with_records), llm_batch_size):
                batch = texts_with_records[batch_start:batch_start + llm_batch_size]
                batch_input = [(orig_idx, text) for orig_idx, text, _ in batch]
                partial = llm_batch_classify(
                    batch_input,
                    categories=categories,
                    settings=settings,
                    api_key=llm_api_key,
                )
                llm_results.update(partial)
            if llm_results:
                logger.info(f"[LLMClassifier] Batch-classified {len(llm_results)} of {len(texts_with_records)} records")
        except Exception as llm_exc:
            logger.warning(f"[LLMClassifier] Batch classification failed: {llm_exc}")

    # Classify each record (LLM primary, keyword fallback)
    for orig_idx, full_text, record in texts_with_records:
        cats = llm_results.get(orig_idx, [])

        # Fall back to keyword matching if LLM didn't return results
        if not cats:
            cats = classify_single(full_text, categories, settings)

        # If still unmatched, assign to "其他需求 & 未分类"
        if not cats:
            cats = [{"category": "其他需求 & 未分类", "matched_keywords": [], "confidence": 0.0}]

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
