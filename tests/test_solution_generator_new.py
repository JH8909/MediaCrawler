"""Tests for AI solution generator - fallback and structured output"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from api.services.solution_generator import (
    ProductType,
    generate_solutions,
    generate_all_solutions,
    _fallback_solutions,
    _CATEGORY_FALLBACKS,
)


def test_product_type_enum():
    assert ProductType.MINI_PROGRAM.value == "小程序"
    assert ProductType.WEBSITE.value == "网站"
    assert ProductType.APP.value == "APP"
    assert ProductType.SCRIPT.value == "脚本"
    assert ProductType.CHROME_EXTENSION.value == "Chrome插件"
    assert ProductType.AUTOMATION_TOOL.value == "自动化工具"
    assert ProductType.WECHAT_BOT.value == "微信机器人"
    assert ProductType.CLI_TOOL.value == "命令行工具"


def test_fallback_solutions_exact_match():
    sols = _fallback_solutions("内容创作 & AI写作")
    assert len(sols) >= 1
    assert sols[0]["name"] == "AI内容创作助手"
    assert sols[0]["product_type"] == "小程序"


def test_fallback_solutions_partial_match():
    sols = _fallback_solutions("数据分析")
    assert len(sols) >= 1
    assert sols[0]["product_type"] in ("网站", "脚本")


def test_fallback_solutions_no_match():
    sols = _fallback_solutions("不存在的分类")
    assert len(sols) >= 1
    assert sols[0]["name"] == "「不存在的分类」痛点解决方案"


def test_fallback_all_categories_have_presets():
    """Every category in the rules should have a matching fallback"""
    from api.services.needs_analyzer import load_rules
    rules = load_rules()
    for cat in rules.get("categories", []):
        name = cat["name"]
        sols = _fallback_solutions(name)
        assert len(sols) >= 1, f"No fallback for {name}"
        assert "name" in sols[0], f"Missing name in fallback for {name}"
        assert "product_type" in sols[0], f"Missing product_type in fallback for {name}"
        assert "core_features" in sols[0], f"Missing core_features in fallback for {name}"
        assert isinstance(sols[0]["core_features"], list), f"core_features not a list for {name}"
        assert len(sols[0]["core_features"]) >= 1, f"Empty core_features for {name}"


def test_generate_solutions_returns_fallback_without_api_key(monkeypatch):
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    sols = generate_solutions(
        category="内容创作 & AI写作",
        count=5,
        rank=1,
        representative_text=["test feedback"],
    )
    assert len(sols) >= 1
    assert sols[0]["name"] == "AI内容创作助手"


def test_generate_all_solutions_structured_output():
    aggregation = [
        {"category": "内容创作 & AI写作", "count": 5, "hot_score": 3.5},
        {"category": "自动化 & 效率工具", "count": 3, "hot_score": 2.0},
    ]
    classified_records = [
        {
            "title": "AI写作问题",
            "desc": "用户反馈AI写作需要改进",
            "category_details": [{"category": "内容创作 & AI写作", "matched_keywords": ["写作"], "confidence": 0.8}],
            "categories": ["内容创作 & AI写作"],
            "extracted_text": "用户反馈AI写作需要改进",
        }
    ]
    result = generate_all_solutions(
        aggregation=aggregation,
        classified_records=classified_records,
        max_categories=2,
    )
    assert result["generated_count"] == 2
    assert len(result["solutions"]) == 2
    for s in result["solutions"]:
        assert "category" in s
        assert "count" in s
        assert "hot_score" in s
        assert "solutions" in s
        if s["solutions"]:
            sol = s["solutions"][0]
            assert "name" in sol
            assert "product_type" in sol
            assert "core_features" in sol


def test_fallback_solution_has_required_fields():
    for cat_key, solutions in _CATEGORY_FALLBACKS.items():
        for sol in solutions:
            assert "name" in sol, f"Missing name in {cat_key}"
            assert "product_type" in sol, f"Missing product_type in {cat_key}"
            assert "summary" in sol, f"Missing summary in {cat_key}"
            assert "target_users" in sol, f"Missing target_users in {cat_key}"
            assert "core_features" in sol, f"Missing core_features in {cat_key}"
            assert isinstance(sol["core_features"], list), f"core_features not list in {cat_key}"
            assert "cost" in sol, f"Missing cost in {cat_key}"
            assert "timeline" in sol, f"Missing timeline in {cat_key}"
            assert "monetization" in sol, f"Missing monetization in {cat_key}"
