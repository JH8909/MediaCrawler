# -*- coding: utf-8 -*-
"""LLM-driven deduplication and noise filter for crawled records.

Before classification, records pass through this module which uses the LLM to:
  1. Identify and remove semantically duplicate / near-duplicate content
  2. Filter out noise (ads, pure emoji, meaningless chatter)
  3. Retain high-quality records that express real user needs

When no LLM_API_KEY is available, the module falls back to a simple
rule-based dedup (title + content hash) so the pipeline still works.
"""

from __future__ import annotations

import hashlib
import json
import os
from typing import Any, Dict, List, Optional

import httpx

from tools.utils import logger

DEFAULT_API_URL = "https://api.deepseek.com/v1/chat/completions"
DEFAULT_MODEL = "deepseek-v4-flash"

DEDUP_PROMPT = """你是一个数据清洗专家。我给你一批从社交媒体采集的用户内容，请帮我做去重和筛选。

每条内容格式为：
{{index}}. [标题] {{title}} | [内容] {{content}}

任务：
1. **去重**：如果多条内容表达的是同一个用户需求/问题（即使用词不同），只保留信息量最大的那条。
2. **去噪**：过滤掉以下内容：
   - 纯广告/带货/促销文案
   - 无实质内容的纯表情、纯感叹（"哈哈哈"、"666"、"好棒"）
   - 只有链接或只有 @提及 的内容
   - 不含任何用户需求/痛点/问题表达的日常闲聊
3. **保留**：包含用户需求、问题、不满、期待的实质内容。

返回 JSON 格式：只包含应保留内容的索引列表（0-based），不要其他文字。
格式：{{"keep_indices": [0, 3, 5, ...]}}

内容列表：
{records_text}
"""


def llm_dedup_records(
    records: List[Dict[str, Any]],
    api_key: str = "",
    api_url: str = "",
    model: str = "",
    max_batch: int = 200,
    timeout: int = 90,
) -> tuple:
    """Use LLM to deduplicate and filter records.

    Returns (deduped_records, removed_count).
    When no LLM key is available, falls back to simple hash dedup.
    """
    if not records:
        return records, 0

    api_key = api_key or os.getenv("LLM_API_KEY", "")
    if not api_key:
        logger.info("[DedupFilter] No LLM_API_KEY, using hash-based dedup fallback")
        deduped, removed = _hash_dedup(records)
        logger.info(f"[DedupFilter] Hash dedup: {len(records)} → {len(deduped)} ({removed} removed)")
        return deduped, removed

    api_url = api_url or os.getenv("LLM_API_URL", DEFAULT_API_URL)
    model = model or os.getenv("LLM_MODEL", DEFAULT_MODEL)

    keep_indices = set()

    for batch_start in range(0, len(records), max_batch):
        batch = records[batch_start:batch_start + max_batch]
        if len(batch) <= 5:
            # Too small to dedup meaningfully — keep all
            keep_indices.update(range(batch_start, batch_start + len(batch)))
            continue

        # Build text for prompt
        text_parts = []
        for j, rec in enumerate(batch):
            title = (rec.get("title") or rec.get("desc") or "")[:80]
            content = (rec.get("content") or rec.get("desc") or rec.get("title") or "")[:120]
            text_parts.append(f"{j}. [标题] {title} | [内容] {content}")
        records_text = "\n".join(text_parts)

        prompt = DEDUP_PROMPT.format(records_text=records_text)

        try:
            with httpx.Client(timeout=timeout) as client:
                resp = client.post(
                    api_url,
                    headers={
                        "Authorization": f"Bearer {api_key}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": model,
                        "messages": [
                            {"role": "system", "content": "你是一个数据清洗专家。只输出 JSON，不要任何其他文字。"},
                            {"role": "user", "content": prompt},
                        ],
                        "temperature": 0.1,  # low temperature for deterministic output
                        "max_tokens": 2000,
                    },
                )
                resp.raise_for_status()
                data = resp.json()
                content_text = data["choices"][0]["message"]["content"]

                # Parse JSON from response
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
                batch_keep = result.get("keep_indices", [])
                for idx in batch_keep:
                    if isinstance(idx, int) and 0 <= idx < len(batch):
                        keep_indices.add(batch_start + idx)

        except Exception as exc:
            logger.warning(f"[DedupFilter] LLM dedup batch {batch_start} failed: {exc}, keeping all")
            keep_indices.update(range(batch_start, batch_start + len(batch)))

    # Build deduped list preserving original order
    original_count = len(records)
    max_idx = max(keep_indices) if keep_indices else -1
    removed = original_count - len(keep_indices)
    deduped = [records[i] for i in range(original_count) if i in keep_indices]

    logger.info(f"[DedupFilter] LLM dedup: {original_count} → {len(deduped)} ({removed} removed)")
    return deduped, removed


def _hash_dedup(records: List[Dict[str, Any]]) -> tuple:
    """Simple hash-based dedup. Returns (deduped_records, removed_count)."""
    seen = set()
    deduped = []
    for rec in records:
        title = (rec.get("title") or rec.get("desc") or "")
        content = (rec.get("content") or rec.get("desc") or rec.get("title") or "")
        h = hashlib.md5((title + content).encode("utf-8")).hexdigest()
        if h not in seen:
            seen.add(h)
            deduped.append(rec)
    removed = len(records) - len(deduped)
    return deduped, removed
