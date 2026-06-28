# -*- coding: utf-8 -*-
"""Auto keyword generation - domain words + demand words combinator"""

from __future__ import annotations

from typing import List

from .models import KeywordPlan


# Domain words - broad categories where users have needs
DOMAIN_WORDS: List[str] = [
    "AI工具",
    "装修",
    "旅游",
    "副业",
    "母婴",
    "数码",
    "美妆",
    "教育",
    "职场",
    "健康",
    "宠物",
    "家居",
    "汽车",
    "餐饮",
    "本地生活",
]

# Demand words - intent signals that indicate user needs/problems
DEMAND_WORDS: List[str] = [
    "求推荐",
    "避坑",
    "哪个好",
    "怎么选",
    "值不值",
    "预算",
    "平替",
    "后悔",
    "攻略",
    "真实体验",
    "注意事项",
    "测评",
    "推荐一下",
    "有没有必要",
    "踩雷",
]

# Platforms to crawl for demand discovery
DEFAULT_PLATFORMS: List[str] = ["xhs", "tieba", "zhihu"]


def generate_keyword_plans(
    count: int = 5,
    offset: int = 0,
    domain_words: List[str] = None,
    demand_words: List[str] = None,
) -> List[KeywordPlan]:
    """Generate deterministic keyword plans by pairing domain + demand words.

    Args:
        count: Number of keyword plans to generate.
        offset: Starting index (for rotation across multiple runs).
        domain_words: Override default domain words.
        demand_words: Override default demand words.

    Returns:
        List of KeywordPlan with deterministic ordering.
    """
    if count < 1 or count > 100:
        raise ValueError("count must be between 1 and 100")
    if domain_words is None:
        domain_words = DOMAIN_WORDS
    if demand_words is None:
        demand_words = DEMAND_WORDS
    if not domain_words or not demand_words:
        raise ValueError("domain_words and demand_words must not be empty")

    plans: List[KeywordPlan] = []
    for i in range(count):
        di = (offset + i) % len(domain_words)
        dwi = (offset + i) % len(demand_words)
        domain = domain_words[di]
        demand = demand_words[dwi]
        plans.append(KeywordPlan(
            keyword=f"{domain} {demand}",
            domain=domain,
            demand_word=demand,
        ))
    return plans


def next_offset(current_offset: int, total_domains: int = None) -> int:
    """Calculate the next offset for round-robin rotation across runs."""
    if total_domains is None:
        total_domains = len(DOMAIN_WORDS)
    return (current_offset + 1) % total_domains
