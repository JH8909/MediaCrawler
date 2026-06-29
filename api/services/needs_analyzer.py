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


# ── Soft token matching (jieba → keyword partial overlap) ──

# High-frequency domain-signal tokens that hint at a category even when
# no exact keyword match exists. Maps token → category name.
_DOMAIN_SIGNAL_TOKENS: Dict[str, str] = {}
_DOMAIN_SIGNALS_BUILT = False


def _build_domain_signals(categories: List[dict]) -> None:
    """One-time build of domain signal token → category mapping from keyword lists."""
    global _DOMAIN_SIGNAL_TOKENS, _DOMAIN_SIGNALS_BUILT
    if _DOMAIN_SIGNALS_BUILT:
        return
    for cat in categories:
        name = cat["name"]
        if name == "其他需求 & 未分类":
            continue
        for kw in cat.get("keywords", []):
            # Split compound keywords into 2-char+ fragments as signals
            if len(kw) <= 4:
                _DOMAIN_SIGNAL_TOKENS[kw] = name
            else:
                # e.g. "内容创作" → "内容" and "创作" both hint at that category
                for i in range(0, len(kw) - 1):
                    frag = kw[i:i+2]
                    if frag not in _DOMAIN_SIGNAL_TOKENS:
                        _DOMAIN_SIGNAL_TOKENS[frag] = name
    _DOMAIN_SIGNALS_BUILT = True


def _token_soft_match(
    text: str,
    categories: List[dict],
    settings: dict,
) -> List[Dict[str, Any]]:
    """Soft-match text to categories using jieba token → keyword partial overlap.

    This is the bridge between strict exact-match and the "未分类" dump.
    It handles natural-language expressions that don't contain any pre-defined
    keyword verbatim but are semantically close (e.g. "团购洗鞋" → 生活用品,
    "本地AI模型" → 开发者工具).
    """
    tokens = segment_text(text)
    if not tokens:
        return []

    # Filter: only keep meaningful Chinese tokens (2+ chars, no pure punctuation)
    meaningful = [t for t in tokens if len(t) >= 2 and re.search(r'[一-鿿]', t)]
    if not meaningful:
        return []

    _build_domain_signals(categories)
    min_match = settings.get("min_match_count", 2)
    max_cats = settings.get("max_categories_per_item", 3)

    # Pre-compute character bigrams for each meaningful token
    token_bigrams: Dict[str, set] = {}
    for token in meaningful:
        bigrams = set()
        for i in range(len(token) - 1):
            bigrams.add(token[i:i+2])
        token_bigrams[token] = bigrams

    results: List[Dict[str, Any]] = []
    for cat in categories:
        name = cat["name"]
        if name == "其他需求 & 未分类" or not cat.get("keywords"):
            continue

        keywords = cat["keywords"]
        matched: List[str] = []

        # Pre-compute keyword bigrams for this category
        kw_bigrams: Dict[str, set] = {}
        for kw in keywords:
            bg = set()
            for i in range(len(kw) - 1):
                bg.add(kw[i:i+2])
            kw_bigrams[kw] = bg

        for token in meaningful:
            # Direct: token IS a keyword
            if token in keywords:
                matched.append(token)
                continue

            # Domain signal lookup (2-char fragments from keyword list)
            if token in _DOMAIN_SIGNAL_TOKENS and _DOMAIN_SIGNAL_TOKENS[token] == name:
                matched.append(token)
                continue

            # Partial overlap: token is substring of a keyword, or vice versa
            found_kw = None
            for kw in keywords:
                if len(kw) >= 2:
                    if token in kw or kw in token:
                        found_kw = kw
                        break
            if found_kw:
                matched.append(found_kw)
                continue

            # Character bigram overlap (catches near-misses like 服务↔服务态度)
            if len(token) >= 2:
                t_bigrams = token_bigrams.get(token, set())
                if not t_bigrams:
                    continue
                best_kw = None
                best_overlap = 0
                for kw in keywords:
                    if len(kw) < 2:
                        continue
                    k_bigrams = kw_bigrams.get(kw, set())
                    if not k_bigrams:
                        continue
                    overlap = len(t_bigrams & k_bigrams)
                    if overlap >= 1 and overlap > best_overlap:
                        best_overlap = overlap
                        best_kw = kw
                if best_kw:
                    matched.append(best_kw)

        if matched and len(matched) >= min_match:
            unique = list(dict.fromkeys(matched))  # dedup preserving order
            results.append({
                "category": name,
                "matched_keywords": unique[:5],
                "confidence": round(min(0.65, 0.25 + len(unique) * 0.08), 2),
            })

    results.sort(key=lambda x: x["confidence"], reverse=True)
    return results[:max_cats]


# ── Smart unclassified labeling ──

# Stop words that don't carry domain signal by themselves
_UNCLASSIFIED_STOP = {
    "可以", "一个", "这个", "那个", "什么", "怎么", "没有", "还是",
    "已经", "不是", "因为", "所以", "如果", "而且", "但是", "不过",
    "一下", "一点", "比较", "非常", "特别", "真的", "还是", "觉得",
    "现在", "今天", "昨天", "明天", "最近", "一直", "已经", "还有",
    "就是", "可能", "应该", "需要", "知道", "看到", "听到", "想到",
}


def _extract_meaningful_tokens(text: str, top_n: int = 5) -> List[str]:
    """Extract the most domain-meaningful tokens (including bigrams) from a short text.

    Returns a mix of single tokens and consecutive-token bigrams.
    Bigrams (e.g. "本地生活", "团购服务") are more distinctive for clustering
    than individual tokens alone.
    """
    tokens = segment_text(text)
    if not tokens:
        return []

    # Filter to meaningful single tokens
    scored: Dict[str, float] = {}
    meaningful_singles: List[str] = []
    for t in tokens:
        t = t.strip()
        if len(t) < 2:
            continue
        if not re.search(r'[一-鿿]', t):
            continue
        if t in _UNCLASSIFIED_STOP:
            continue
        meaningful_singles.append(t)
        score = len(t) * 0.3
        if len(t) >= 3:
            score += 0.5
        if re.search(r'(工具|平台|服务|产品|方案|推荐|测评|攻略|教程|方法|技巧|经验)', t):
            score += 1.0
        scored[t] = scored.get(t, 0) + score

    # Generate consecutive bigrams from meaningful singles (order-preserving)
    for i in range(len(meaningful_singles) - 1):
        bigram = meaningful_singles[i] + meaningful_singles[i + 1]
        # Cap at 4 chars: longer compounds are too specific for clustering
        if 4 <= len(bigram) <= 5:
            scored[bigram] = scored.get(meaningful_singles[i], 0) + scored.get(meaningful_singles[i + 1], 0) + 1.5

    ranked = sorted(scored.items(), key=lambda x: -x[1])
    return [t for t, _ in ranked[:top_n]]


def _smart_unclassified_label(texts: List[str]) -> str:
    """Given a batch of unclassified texts, suggest a descriptive label.

    Used as a last resort to avoid a single giant "未分类" bucket.
    Falls back to the generic label when texts are too diverse.
    """
    if not texts:
        return "其他需求 & 未分类"

    if len(texts) <= 3:
        # Too few to cluster meaningfully — pick top tokens
        all_tokens: List[str] = []
        for t in texts:
            all_tokens.extend(_extract_meaningful_tokens(t, top_n=2))
        if not all_tokens:
            return "其他需求 & 未分类"
        # Count and pick top 2
        from collections import Counter
        top = Counter(all_tokens).most_common(2)
        label = " & ".join(t for t, _ in top)
        return f"「{label}」相关" if label else "其他需求 & 未分类"

    # Collect top tokens across all texts
    token_counter: Dict[str, int] = {}
    for text in texts:
        for token in _extract_meaningful_tokens(text, top_n=3):
            token_counter[token] = token_counter.get(token, 0) + 1

    if not token_counter:
        return "其他需求 & 未分类"

    # Only keep tokens that appear in >= 2 texts (signal, not noise)
    from collections import Counter as _Counter
    repeated = {t: c for t, c in token_counter.items() if c >= 2}
    if not repeated:
        return "其他需求 & 未分类"

    top_tokens = _Counter(repeated).most_common(3)
    label = " & ".join(t for t, _ in top_tokens[:3])
    return f"「{label}」相关需求" if label else "其他需求 & 未分类"


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
    """Three-tier classification pipeline:

    Tier 1 — Exact token match: jieba tokens ∩ category keywords (strictest).
    Tier 2 — Soft token match: jieba tokens ↔ keyword partial overlap.
    Tier 3 — Unguarded substring match (fallback when jieba unavailable).

    Records that pass all three tiers are assigned to "其他需求 & 未分类".
    """
    if not text or len(text) < settings.get("min_chinese_chars", 10):
        return []

    tokens = segment_text(text)
    token_set = set(tokens) if tokens else set()
    min_match = settings.get("min_match_count", 2)
    max_cats = settings.get("max_categories_per_item", 3)
    orig_text = text

    results: List[Dict[str, Any]] = []

    for cat in categories:
        name = cat["name"]
        keywords = cat.get("keywords", [])
        if not keywords or name == "其他需求 & 未分类":
            continue

        # ── Tier 1: Exact token-set intersection ──
        matched: List[str] = []
        if token_set:
            matched = [kw for kw in keywords if kw in token_set]

        # ── Tier 2: Soft token overlap (NEW) ──
        if not matched and token_set:
            soft = _token_soft_match(text, [cat], settings)
            if soft:
                results.extend(soft)
                continue

        # ── Tier 3: Raw substring (jieba unavailable) ──
        if not matched and not token_set:
            matched = [kw for kw in keywords if kw in orig_text]

        if matched and len(matched) >= min_match:
            confidence = min(1.0, len(matched) / max(len(keywords), 1) * 2)
            results.append({
                "category": name,
                "matched_keywords": matched[:5],
                "confidence": round(confidence, 2),
            })

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
    unclassified_texts: List[str] = []
    unclassified_indices: List[int] = []

    for orig_idx, full_text, record in texts_with_records:
        cats = llm_results.get(orig_idx, [])

        # Fall back to keyword matching if LLM didn't return results
        if not cats:
            cats = classify_single(full_text, categories, settings)

        # If still unmatched, collect for smart labeling
        if not cats:
            unclassified_texts.append(full_text)
            unclassified_indices.append(orig_idx)
            # Temporary placeholder — will be replaced below
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

    # ── Smart unclassified relabeling ──
    # When > 25% of records land in "其他需求 & 未分类", the category
    # system is missing important domains.  Try to auto-discover sub-clusters
    # from the unclassified texts and split the monolith.
    total_classified = len(texts_with_records)
    unclassified_count = freq.get("其他需求 & 未分类", 0)
    unclassified_ratio = unclassified_count / max(total_classified, 1)

    if unclassified_count >= 5 and unclassified_ratio >= 0.15:
        logger.info(
            f"[NeedsAnalyzer] {unclassified_count}/{total_classified} records "
            f"({unclassified_ratio:.0%}) unclassified — running smart relabeling"
        )
        _relabel_unclassified(
            classified_records=classified_records,
            freq=freq,
            hot_scores=hot_scores,
            hit_counts=hit_counts,
            min_cluster_size=max(2, round(unclassified_count * 0.04)),
        )
    elif unclassified_count > 0:
        logger.info(
            f"[NeedsAnalyzer] {unclassified_count}/{total_classified} records "
            f"({unclassified_ratio:.0%}) unclassified — ratio below threshold, keeping generic label"
        )

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


def _relabel_unclassified(
    classified_records: List[Dict[str, Any]],
    freq: Dict[str, int],
    hot_scores: Dict[str, float],
    hit_counts: Dict[str, int],
    min_cluster_size: int = 3,
) -> None:
    """Split the monolithic "其他需求 & 未分类" bucket into auto-discovered sub-clusters.

    Mutates classified_records, freq, hot_scores, hit_counts in place.
    """
    # Collect unclassified record indices and their texts
    unclassified_entries: List[Tuple[int, str]] = []
    for idx, rec in enumerate(classified_records):
        cats = rec.get("categories") or []
        if "其他需求 & 未分类" in cats:
            text = rec.get("extracted_text", "") or ""
            unclassified_entries.append((idx, text))

    if len(unclassified_entries) < min_cluster_size:
        return

    # Extract signature tokens per entry
    entry_signatures: List[Tuple[int, List[str]]] = []
    for idx, text in unclassified_entries:
        tokens = _extract_meaningful_tokens(text, top_n=4)
        if tokens:
            entry_signatures.append((idx, tokens))

    if not entry_signatures:
        return

    # Greedy clustering: group entries that share ≥ 1 top token
    clusters: List[Dict[str, Any]] = []  # [{token: str, indices: [idx, ...]}]
    assigned = set()

    # Sort tokens by frequency across entries to find strongest signals first
    from collections import Counter as _C
    global_token_freq = _C()
    for _, tokens in entry_signatures:
        global_token_freq.update(tokens)

    # Build lookup: idx → token list
    entry_signatures_dict: Dict[int, List[str]] = {idx: tokens for idx, tokens in entry_signatures}

    # Try each frequent token as a cluster seed (prefer short tokens first)
    # Short tokens (2-4 chars) make better cluster labels than long bigrams
    sorted_seeds = sorted(global_token_freq.most_common(20), key=lambda x: (-x[1], len(x[0])))
    for seed_token, _ in sorted_seeds:
        cluster_indices: List[int] = []
        for idx, tokens in entry_signatures:
            if idx in assigned:
                continue
            if seed_token in tokens:
                cluster_indices.append(idx)
        if len(cluster_indices) >= min_cluster_size:
            for i in cluster_indices:
                assigned.add(i)
            # Pick the best label: shortest token that appears in most cluster members
            cluster_token_freq = _C()
            for idx in cluster_indices:
                for t in entry_signatures_dict.get(idx, []):
                    cluster_token_freq[t] += 1
            # Choose shortest token among the most frequent
            best_label = seed_token
            if cluster_token_freq:
                top_tokens = sorted(cluster_token_freq.items(), key=lambda x: (-x[1], len(x[0])))
                for t, _ in top_tokens[:5]:
                    if 2 <= len(t) <= 4:
                        best_label = t
                        break
            clusters.append({"token": best_label, "indices": cluster_indices})

    if not clusters:
        # No meaningful sub-clusters found — keep the generic label
        return

    # Rename the generic bucket and create sub-categories
    old_label = "其他需求 & 未分类"
    old_count = freq.pop(old_label, 0)
    old_hot = hot_scores.pop(old_label, 0.0)
    old_hits = hit_counts.pop(old_label, 0)

    for cluster in clusters:
        label = f"「{cluster['token']}」相关需求"
        freq[label] = len(cluster["indices"])
        # Distribute hot scores proportionally
        share = len(cluster["indices"]) / max(old_count, 1)
        hot_scores[label] = round(old_hot * share, 2)
        hit_counts[label] = len(cluster["indices"])

        for idx in cluster["indices"]:
            rec = classified_records[idx]
            rec["categories"] = [label]
            rec["category_details"] = [{
                "category": label,
                "matched_keywords": [cluster["token"]],
                "confidence": 0.25,
            }]

    # Remaining unclassified (not in any cluster): keep generic label
    leftover = old_count - len(assigned)
    if leftover > 0:
        freq[old_label] = leftover
        hot_scores[old_label] = round(old_hot * (leftover / max(old_count, 1)), 2)
        hit_counts[old_label] = leftover
        # These records keep their original "其他需求 & 未分类" label

    logger.info(
        f"[NeedsAnalyzer] Smart relabeling: split {old_count} unclassified → "
        f"{len(clusters)} sub-clusters ({sum(len(c['indices']) for c in clusters)} records), "
        f"{leftover} remain generic"
    )


def load_jsonl(filepath: str) -> List[Dict[str, Any]]:
    records = []
    with open(filepath, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                records.append(json.loads(line))
    return records
