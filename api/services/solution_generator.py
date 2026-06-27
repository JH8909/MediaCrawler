# -*- coding: utf-8 -*-
"""AI Solution Generator - call LLM to generate solutions for each pain point category"""

from __future__ import annotations

import json
import os
from typing import Any, Dict, List, Optional

import httpx


# Default config - uses DeepSeek via OpenAI-compatible API
DEFAULT_API_URL = "https://api.deepseek.com/v1/chat/completions"
DEFAULT_MODEL = "deepseek-v4-flash"
SOLUTION_PROMPT = """你是一个产品解决方案专家。请针对以下用户痛点，生成可落地的解决方案。

痛点分类：{category}
该分类出现次数：{count} 次（在所有反馈中排第 {rank} 位）
代表用户反馈：
{representative_text}

要求：
1. 生成 2-3 个不同的解决方案
2. 每个方案包含：
   - 方案名称（简洁明了）
   - 方案形式（功能改进 / 小程序 / App / 网站 / 后台系统 / 业务流程改进 / 新产品）
   - 核心功能描述（3-5 点，每点一句话）
   - 落地成本（低 / 中 / 高）
   - 预期效果（一句话）
3. 方案要具体、可落地，不要泛泛而谈
4. 输出格式为 JSON，不要包含其他文字

输出格式示例：
[
  {{
    "solution_name": "方案名称",
    "solution_type": "功能改进",
    "core_features": ["功能点1", "功能点2", "功能点3"],
    "cost": "中",
    "expected_effect": "预期效果描述"
  }}
]
"""


def generate_solutions(
    category: str,
    count: int,
    rank: int,
    representative_text: List[str],
    api_url: str = None,
    api_key: str = None,
    model: str = None,
    timeout: int = 60,
) -> List[Dict[str, Any]]:
    """Call LLM to generate solutions for one pain point category.
    
    Returns list of solution dicts, or empty list on failure.
    """
    if api_url is None:
        api_url = os.getenv("LLM_API_URL", DEFAULT_API_URL)
    if api_key is None:
        api_key = os.getenv("LLM_API_KEY", "")
    if model is None:
        model = os.getenv("LLM_MODEL", DEFAULT_MODEL)

    if not api_key:
        return _fallback_solutions(category)

    prompt = SOLUTION_PROMPT.format(
        category=category,
        count=count,
        rank=rank,
        representative_text="\n".join(
            f"- {t[:120]}" for t in representative_text[:5]
        ),
    )

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
                        {"role": "system", "content": "你是一个专业的产品解决方案专家。只输出 JSON，不要任何其他文字。"},
                        {"role": "user", "content": prompt},
                    ],
                    "temperature": 0.7,
                    "max_tokens": 2000,
                },
            )
            resp.raise_for_status()
            data = resp.json()
            content_text = data["choices"][0]["message"]["content"]

            # Try to parse JSON from the response
            # Clean markdown code blocks if present
            cleaned = content_text.strip()
            if cleaned.startswith("```"):
                cleaned = cleaned.split("\n", 1)[-1]
                if "```" in cleaned:
                    cleaned = cleaned.rsplit("```", 1)[0]
            if cleaned.startswith("```json"):
                cleaned = cleaned[7:].strip()
                if cleaned.endswith("```"):
                    cleaned = cleaned[:-3].strip()

            solutions = json.loads(cleaned)
            if isinstance(solutions, list):
                return solutions
            return []
    except Exception as exc:
        print(f"[SolutionGenerator] LLM call failed for '{category}': {exc}")
        return _fallback_solutions(category)


def _fallback_solutions(category: str) -> List[Dict[str, Any]]:
    """Return template solutions when LLM is unavailable"""
    return [
        {
            "solution_name": f"针对「{category}」的专项改进方案",
            "solution_type": "功能改进",
            "core_features": [
                "收集用户关于此类问题的详细反馈",
                "分析问题根因并制定改进计划",
                "实施改进并跟踪效果",
                "建立持续监控机制",
                "定期回访用户确认问题已解决",
            ],
            "cost": "中",
            "expected_effect": "有效降低该类痛点的发生率",
        }
    ]


def generate_all_solutions(
    aggregation: List[Dict[str, Any]],
    classified_records: List[Dict[str, Any]],
    api_url: str = None,
    api_key: str = None,
    model: str = None,
    max_categories: int = 5,
) -> Dict[str, Any]:
    """Generate solutions for top N pain point categories.
    
    Args:
        aggregation: [{"category": str, "count": int}, ...]
        classified_records: records with categories field
        api_url/api_key/model: LLM config
        
    Returns:
        {
            "solutions": [{"category": str, "count": int, "solutions": [...]}, ...],
            "generated_count": int
        }
    """
    # Build representative texts per category
    category_samples: Dict[str, List[str]] = {}
    for record in classified_records:
        for cat_detail in record.get("category_details", []):
            cat_name = cat_detail["category"]
            if cat_name not in category_samples:
                category_samples[cat_name] = []
            title = record.get("title", "") or ""
            desc = record.get("desc", "") or ""
            text = (title + " " + desc).strip()
            if text and len(category_samples[cat_name]) < 5:
                category_samples[cat_name].append(text)

    solutions = []
    for rank, item in enumerate(aggregation[:max_categories], 1):
        cat = item["category"]
        count = item["count"]
        samples = category_samples.get(cat, [])

        sols = generate_solutions(
            category=cat,
            count=count,
            rank=rank,
            representative_text=samples,
            api_url=api_url,
            api_key=api_key,
            model=model,
        )
        solutions.append({
            "category": cat,
            "count": count,
            "rank": rank,
            "solutions": sols,
        })

    return {
        "solutions": solutions,
        "generated_count": len(solutions),
    }
