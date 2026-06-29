# -*- coding: utf-8 -*-
"""Product opportunity evaluator for collected demand data.

This layer turns classified social data into PM-style decisions:
build now, validate first, or reject. It is intentionally deterministic first
and only uses LLM as an optional reviewer so report generation remains reliable.
"""

from __future__ import annotations

import json
import os
import re
from typing import Any, Dict, List, Optional

try:
    import httpx
except ImportError:  # pragma: no cover - optional dependency guard
    httpx = None

from tools.utils import logger


DEFAULT_API_URL = "https://api.deepseek.com/v1/chat/completions"
DEFAULT_MODEL = "deepseek-v4-flash"

BUILD = "build"
VALIDATE = "validate"
REJECT = "reject"

DECISION_LABELS = {
    BUILD: "推荐做",
    VALIDATE: "先验证",
    REJECT: "不建议做",
}

PAIN_KEYWORDS = [
    "麻烦", "太难", "不会", "求推荐", "有没有", "怎么", "需要", "希望",
    "避坑", "坑", "踩雷", "解决", "自动", "省时间", "效率", "成本",
    "贵", "便宜", "焦虑", "崩溃", "救命", "失败", "没人管",
]

PAYMENT_KEYWORDS = [
    "付费", "钱", "价格", "成本", "会员", "订阅", "工具", "服务", "商家",
    "企业", "报价", "接单", "订单", "客户", "老板", "团队", "预算",
]

MVP_FRIENDLY_KEYWORDS = [
    "ai", "AI", "自动化", "数据", "分析", "开发", "工具", "脚本", "内容",
    "学习", "电商", "效率", "运营", "插件", "网站", "小程序", "机器人",
]

BROAD_OR_OFFLINE_KEYWORDS = ["本地生活", "餐饮", "旅游", "房产", "汽车", "医疗", "金融"]
REJECT_CATEGORY_KEYWORDS = ["闲聊", "无效", "广告"]


def evaluate_opportunities(
    aggregation: List[Dict[str, Any]],
    classified_records: List[Dict[str, Any]],
    solutions_data: Optional[List[Dict[str, Any]]] = None,
    api_key: Optional[str] = None,
    api_url: Optional[str] = None,
    model: Optional[str] = None,
    max_opportunities: int = 12,
) -> Dict[str, Any]:
    """Evaluate classified demand clusters as product opportunities."""
    if not aggregation:
        return _empty_result()

    solutions_data = solutions_data or []
    total = sum(_safe_int(item.get("count")) for item in aggregation) or len(classified_records or [])
    sol_map = _solutions_by_category(solutions_data)

    opportunities = []
    for rank, item in enumerate(aggregation[:max_opportunities], 1):
        category = str(item.get("category") or item.get("name") or "未分类需求")
        count = _safe_int(item.get("count") or item.get("total"))
        hot_score = _safe_float(item.get("hot_score"))
        evidence = _evidence_for_category(category, classified_records, limit=8)
        solution_hint = sol_map.get(category)
        opportunity = _build_opportunity(
            category=category,
            rank=rank,
            count=count,
            total=total,
            hot_score=hot_score,
            evidence=evidence,
            solution_hint=solution_hint,
        )
        opportunities.append(opportunity)

    api_key = api_key if api_key is not None else os.getenv("LLM_API_KEY", "")
    if api_key:
        try:
            reviewed = _call_llm_pm_review(
                opportunities=opportunities,
                api_key=api_key,
                api_url=api_url or os.getenv("LLM_API_URL", DEFAULT_API_URL),
                model=model or os.getenv("LLM_MODEL", DEFAULT_MODEL),
            )
            opportunities = _merge_llm_review(opportunities, reviewed)
        except Exception as exc:
            logger.warning(f"[OpportunityEvaluator] LLM PM review failed: {exc}")

    opportunities.sort(key=lambda item: (
        # 1) Unclassified always last, regardless of score
        _contains_any(item["category"], ["未分类", "相关需求"]),
        # 2) Non-BUILD before BUILD...
        item["decision"] != BUILD,
        # 3) ...but BUILD unclassified still below VALIDATE others
        1 if _contains_any(item["category"], ["未分类", "相关需求"]) and item["decision"] != REJECT else 0,
        # 4) Within same tier: higher score first
        -item["score"],
        item["rank"],
    ))
    result = _assemble_result(opportunities)
    return result


def _build_opportunity(
    category: str,
    rank: int,
    count: int,
    total: int,
    hot_score: float,
    evidence: List[Dict[str, Any]],
    solution_hint: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    evidence_text = " ".join(item.get("text", "") for item in evidence)
    category_text = category + " " + evidence_text

    demand_strength = _score_demand_strength(count, total)
    evidence_quality = min(5, max(1, len(evidence)))
    pain_intensity = _keyword_score(evidence_text, PAIN_KEYWORDS, base=2)
    payment_potential = _keyword_score(category_text, PAYMENT_KEYWORDS, base=2)
    mvp_feasibility = _mvp_feasibility(category_text, solution_hint)
    acquisition_ease = _acquisition_ease(count, evidence_text)
    competition_risk = _competition_risk(category_text, count, total)

    score = round(
        demand_strength * 3
        + evidence_quality * 3
        + pain_intensity * 3
        + payment_potential * 3
        + mvp_feasibility * 4
        + acquisition_ease * 2
        + (5 - competition_risk) * 2
    )
    # Scale: max possible = 5*18 + 4*2 = 98.  Cap at 100.
    score = max(5, min(100, score))

    # Unclassified / smart-relabel categories get a slight score penalty
    # because they lack a clear product thesis, but not outright rejection.
    is_unclassified = _contains_any(category, ["未分类", "相关需求"])
    if is_unclassified:
        score = round(score * 0.75)

    is_reject_category = _contains_any(category, REJECT_CATEGORY_KEYWORDS)
    if is_reject_category or count <= 1 or score < 40:
        decision = REJECT
    elif score >= 65 and mvp_feasibility >= 3 and evidence_quality >= 3:
        decision = BUILD
    else:
        decision = VALIDATE

    priority = "P0" if decision == BUILD and score >= 78 else "P1" if decision != REJECT else "P2"

    why = _why_points(
        decision=decision,
        count=count,
        demand_strength=demand_strength,
        pain_intensity=pain_intensity,
        payment_potential=payment_potential,
        mvp_feasibility=mvp_feasibility,
        evidence_quality=evidence_quality,
    )
    risks = _risk_points(
        decision=decision,
        competition_risk=competition_risk,
        evidence_quality=evidence_quality,
        payment_potential=payment_potential,
        mvp_feasibility=mvp_feasibility,
    )

    return {
        "category": category,
        "rank": rank,
        "decision": decision,
        "decision_label": DECISION_LABELS[decision],
        "priority": priority,
        "score": score,
        "count": count,
        "hot_score": hot_score,
        "scores": {
            "demand_strength": demand_strength,
            "evidence_quality": evidence_quality,
            "pain_intensity": pain_intensity,
            "payment_potential": payment_potential,
            "mvp_feasibility": mvp_feasibility,
            "acquisition_ease": acquisition_ease,
            "competition_risk": competition_risk,
        },
        "why": why,
        "risks": risks,
        "mvp": _mvp_plan(category, solution_hint),
        "validation": _validation_plan(category, decision),
        "evidence": evidence[:5],
        "solution_hint": solution_hint,
    }


def _call_llm_pm_review(
    opportunities: List[Dict[str, Any]],
    api_key: str,
    api_url: str,
    model: str,
    timeout: int = 90,
) -> List[Dict[str, Any]]:
    if not httpx:
        return []

    payload = []
    for item in opportunities[:10]:
        payload.append({
            "category": item["category"],
            "current_decision": item["decision"],
            "score": item["score"],
            "count": item["count"],
            "scores": item["scores"],
            "evidence": [e.get("text", "")[:120] for e in item.get("evidence", [])[:4]],
            "mvp": item.get("mvp", {}),
        })

    prompt = f"""你是一个面向独立开发者和小团队的产品经理。
请基于以下用户需求簇，判断哪些可以做、哪些要先验证、哪些不建议做。

判断标准：
1. 优先推荐低成本、能快速 MVP、能通过 AI/自动化形成差异化的机会。
2. 即使数据量高，如果缺少明确付费场景、证据弱、实施重或合规风险高，也要降级为先验证或不建议做。
3. 每个结论必须能被原始证据支持。

输入机会：
{json.dumps(payload, ensure_ascii=False)}

只输出 JSON 数组，不要输出解释文字。每项格式：
[
  {{
    "category": "原分类名",
    "decision": "build|validate|reject",
    "score": 0-100,
    "priority": "P0|P1|P2",
    "why": ["不超过3条原因"],
    "risks": ["不超过3条风险"],
    "mvp": {{
      "positioning": "一句话产品定位",
      "core_features": ["功能1", "功能2", "功能3"],
      "first_version": "第一版怎么做"
    }},
    "validation": ["验证动作1", "验证动作2", "验证动作3"]
  }}
]"""

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
                    {"role": "system", "content": "你是产品经理，只输出可解析 JSON。"},
                    {"role": "user", "content": prompt},
                ],
                "temperature": 0.2,
                "max_tokens": 4000,
            },
        )
        resp.raise_for_status()
        data = resp.json()
        content = data["choices"][0]["message"]["content"]
    parsed = _parse_json_content(content)
    return parsed if isinstance(parsed, list) else []


def _merge_llm_review(
    opportunities: List[Dict[str, Any]],
    reviewed: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    if not reviewed:
        return opportunities

    review_map = {
        str(item.get("category", "")): item
        for item in reviewed
        if isinstance(item, dict) and item.get("category")
    }
    merged = []
    for item in opportunities:
        override = review_map.get(item["category"])
        if not override:
            merged.append(item)
            continue

        updated = dict(item)
        decision = override.get("decision")
        if decision in DECISION_LABELS:
            updated["decision"] = decision
            updated["decision_label"] = DECISION_LABELS[decision]
        if isinstance(override.get("score"), (int, float)):
            updated["score"] = max(0, min(100, round(float(override["score"]))))
        if override.get("priority") in {"P0", "P1", "P2"}:
            updated["priority"] = override["priority"]
        for key in ("why", "risks", "validation"):
            if isinstance(override.get(key), list) and override[key]:
                updated[key] = [str(x) for x in override[key][:4]]
        if isinstance(override.get("mvp"), dict):
            updated["mvp"] = _normalize_mvp(override["mvp"], item["category"])
        merged.append(updated)
    return merged


def _assemble_result(opportunities: List[Dict[str, Any]]) -> Dict[str, Any]:
    build = [item for item in opportunities if item["decision"] == BUILD]
    validate = [item for item in opportunities if item["decision"] == VALIDATE]
    reject = [item for item in opportunities if item["decision"] == REJECT]
    top = opportunities[0] if opportunities else None
    return {
        "viewpoint": "indie_mvp",
        "summary": {
            "total_opportunities": len(opportunities),
            "recommended": len(build),
            "validate": len(validate),
            "rejected": len(reject),
            "top_decision": top["decision"] if top else "none",
            "top_reason": (top.get("why") or ["暂无可用机会"])[0] if top else "暂无可用机会",
        },
        "opportunities": opportunities,
        "build": build,
        "validate": validate,
        "reject": reject,
        "workflow": [
            "清洗原始内容，过滤无效闲聊和重复数据",
            "按真实痛点聚类，保留每个结论的原文证据",
            "从需求强度、痛点强度、付费潜力、MVP可行性、获客难度和竞争风险打分",
            "把机会分成推荐做、先验证、不建议做三类",
            "对推荐机会输出第一版定位、核心功能和验证动作",
        ],
    }


def _empty_result() -> Dict[str, Any]:
    return _assemble_result([])


def _solutions_by_category(solutions_data: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    result = {}
    for item in solutions_data:
        category = str(item.get("category") or "")
        if category:
            result[category] = item
    return result


def _evidence_for_category(
    category: str,
    classified_records: List[Dict[str, Any]],
    limit: int = 8,
) -> List[Dict[str, Any]]:
    rows = []
    for record in classified_records or []:
        cats = record.get("categories") or []
        if category not in cats:
            details = record.get("category_details") or []
            if not any(d.get("category") == category for d in details if isinstance(d, dict)):
                continue
        text = (
            record.get("extracted_text")
            or record.get("content")
            or record.get("desc")
            or record.get("title")
            or ""
        )
        text = re.sub(r"\s+", " ", str(text)).strip()
        if not text:
            continue
        rows.append({
            "text": text[:180],
            "hot_score": _safe_float(record.get("hot_score")),
            "nickname": record.get("nickname") or record.get("author") or "",
            "liked_count": record.get("liked_count", record.get("like_count", 0)),
        })
    rows.sort(key=lambda r: _safe_float(r.get("hot_score")), reverse=True)
    return rows[:limit]


def _score_demand_strength(count: int, total: int) -> int:
    if total <= 0:
        return 1
    ratio = count / max(total, 1)
    if count >= 20 or ratio >= 0.25:
        return 5
    if count >= 10 or ratio >= 0.15:
        return 4
    if count >= 5 or ratio >= 0.08:
        return 3
    if count >= 2:
        return 2
    return 1


def _keyword_score(text: str, keywords: List[str], base: int = 1) -> int:
    hits = sum(1 for kw in keywords if kw and kw in text)
    return max(1, min(5, base + hits))


def _mvp_feasibility(text: str, solution_hint: Optional[Dict[str, Any]]) -> int:
    score = 2 + sum(1 for kw in MVP_FRIENDLY_KEYWORDS if kw in text)
    if solution_hint and solution_hint.get("solutions"):
        score += 1
    if _contains_any(text, BROAD_OR_OFFLINE_KEYWORDS):
        score -= 1
    return max(1, min(5, score))


def _acquisition_ease(count: int, evidence_text: str) -> int:
    score = 1
    if count >= 5:
        score += 1
    if count >= 15:
        score += 1
    if _contains_any(evidence_text, ["求推荐", "有没有", "哪里", "平台", "群", "小红书", "抖音", "知乎"]):
        score += 1
    if _contains_any(evidence_text, ["分享", "收藏", "关注", "评论区"]):
        score += 1
    return max(1, min(5, score))


def _competition_risk(text: str, count: int, total: int) -> int:
    score = 2
    if _contains_any(text, BROAD_OR_OFFLINE_KEYWORDS):
        score += 1
    if _contains_any(text, ["电商", "内容", "写作", "数据分析", "SaaS", "平台"]):
        score += 1
    if total and count / max(total, 1) > 0.35:
        score += 1
    return max(1, min(5, score))


def _why_points(
    decision: str,
    count: int,
    demand_strength: int,
    pain_intensity: int,
    payment_potential: int,
    mvp_feasibility: int,
    evidence_quality: int,
) -> List[str]:
    points = []
    if decision == BUILD:
        points.append(f"需求重复出现 {count} 次，已具备优先验证的集中度")
        if mvp_feasibility >= 4:
            points.append("可用 AI/自动化做出第一版，MVP 实施成本相对可控")
        if payment_potential >= 3:
            points.append("文本中存在工具、服务、成本或付费相关信号")
    elif decision == VALIDATE:
        points.append("已有需求信号，但证据或商业场景还不够扎实")
        if evidence_quality < 4:
            points.append("需要补更多高质量原文证据再进入开发")
        if payment_potential < 3:
            points.append("付费意愿不明确，建议先做访谈或落地页验证")
    else:
        points.append("当前证据不足以支持投入开发")
        if demand_strength <= 2:
            points.append("重复出现次数较少，可能只是零散需求")
        if pain_intensity <= 2:
            points.append("痛点表达不够强，缺少必须解决的迫切性")
    return points[:3]


def _risk_points(
    decision: str,
    competition_risk: int,
    evidence_quality: int,
    payment_potential: int,
    mvp_feasibility: int,
) -> List[str]:
    risks = []
    if competition_risk >= 4:
        risks.append("赛道可能偏宽或竞品成熟，需要找到更细的切入场景")
    if evidence_quality < 3:
        risks.append("可引用证据不足，容易误判真实需求")
    if payment_potential < 3:
        risks.append("商业化信号较弱，需要先验证用户是否愿意付费")
    if mvp_feasibility < 3:
        risks.append("第一版落地复杂度偏高，不适合直接开做")
    if decision == BUILD and not risks:
        risks.append("需要控制第一版范围，避免做成大而全平台")
    return risks[:3]


def _mvp_plan(category: str, solution_hint: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    if solution_hint:
        solutions = solution_hint.get("solutions") or []
        if solutions:
            first = solutions[0]
            return _normalize_mvp({
                "positioning": first.get("summary") or f"面向「{category}」的轻量解决工具",
                "core_features": first.get("core_features") or [],
                "first_version": first.get("name") or "先做一个可手动辅助、可验证转化的最小版本",
            }, category)
    return {
        "positioning": f"面向「{category}」的轻量 MVP 工具",
        "core_features": ["收集关键输入", "AI 提炼建议", "导出可执行清单"],
        "first_version": "先用单页面或脚本完成核心流程，只验证一个高频场景",
    }


def _normalize_mvp(value: Dict[str, Any], category: str) -> Dict[str, Any]:
    features = value.get("core_features") or []
    if not isinstance(features, list):
        features = [str(features)]
    features = [str(item) for item in features if str(item).strip()][:4]
    if not features:
        features = ["收集关键输入", "AI 提炼建议", "导出可执行清单"]
    return {
        "positioning": str(value.get("positioning") or f"面向「{category}」的轻量 MVP 工具"),
        "core_features": features,
        "first_version": str(value.get("first_version") or "先做最小闭环验证"),
    }


def _validation_plan(category: str, decision: str) -> List[str]:
    if decision == BUILD:
        return [
            "用 20 条原始内容复核痛点是否同质",
            "做一个落地页或表单收集 10 个目标用户联系方式",
            "用无代码/脚本跑通一次人工交付闭环",
        ]
    if decision == VALIDATE:
        return [
            "继续采集同类关键词，确认重复痛点是否稳定",
            "找 5-10 个用户访谈使用场景和付费意愿",
            "先做内容/模板/服务试卖，不立刻投入完整开发",
        ]
    return [
        "暂不投入开发资源",
        "如果继续关注，只保留关键词监控",
        "等待出现更高频、更明确付费场景后再评估",
    ]


def _parse_json_content(content: str) -> Any:
    cleaned = str(content or "").strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.split("\n", 1)[-1]
        if "```" in cleaned:
            cleaned = cleaned.rsplit("```", 1)[0]
    if cleaned.startswith("json"):
        cleaned = cleaned[4:].strip()
    return json.loads(cleaned)


def _contains_any(text: str, keywords: List[str]) -> bool:
    return any(kw in text for kw in keywords)


def _safe_int(value: Any) -> int:
    try:
        return int(float(str(value).replace(",", "")))
    except (TypeError, ValueError):
        return 0


def _safe_float(value: Any) -> float:
    try:
        return float(str(value).replace(",", ""))
    except (TypeError, ValueError):
        return 0.0
