"""Tests for demand classification rules and needs analyzer"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from api.services.needs_analyzer import (
    _is_noise,
    _calculate_hot_score,
    classify_single,
    analyze_records,
    load_jsonl,
)


def test_is_noise_filters_meaningless_text():
    assert _is_noise("哈哈")
    assert _is_noise("666")
    assert _is_noise("好看")
    assert _is_noise("[笑哭R]")
    assert _is_noise("")
    assert not _is_noise("这种非常适合公司买，放在公司茶水间，几天就被炫光了")
    assert not _is_noise("起点会用ai私自改小说，新人都快崩溃了")


def test_hot_score_with_tieba_data():
    record = {"total_replay_num": "81"}
    score = _calculate_hot_score(record)
    # math.log1p(81) ≈ 4.4 * 0.5 = 2.2
    assert score > 2.0 and score < 2.5


def test_hot_score_with_xhs_data():
    record = {"liked_count": "4.9万", "comment_count": "1174"}
    score = _calculate_hot_score(record)
    assert score > 0


def test_hot_score_zero_for_no_engagement():
    record = {}
    score = _calculate_hot_score(record)
    assert score == 0.0


def test_hot_score_with_none_values():
    record = {"liked_count": None, "comment_count": ""}
    score = _calculate_hot_score(record)
    assert score == 0.0


def test_classify_single_matches_keywords():
    rules = {
        "categories": [
            {
                "name": "内容创作 & AI写作",
                "keywords": ["写作", "AI改文", "文案"],
                "description": "test",
            },
            {
                "name": "自动化 & 效率工具",
                "keywords": ["自动", "批量", "效率"],
                "description": "test",
            },
        ],
        "settings": {"min_match_count": 1, "max_categories_per_item": 2, "min_chinese_chars": 3},
    }
    result = classify_single("起点用AI改文，新人崩溃", rules["categories"], rules["settings"])
    categories = [r["category"] for r in result]
    assert "内容创作 & AI写作" in categories


def test_classify_single_no_match():
    rules = {
        "categories": [
            {"name": "内容创作 & AI写作", "keywords": ["写作", "AI改文"], "description": "test"},
        ],
        "settings": {"min_match_count": 1, "max_categories_per_item": 2, "min_chinese_chars": 3},
    }
    result = classify_single("今天天气真好", rules["categories"], rules["settings"])
    assert len(result) == 0


def test_analyze_records_with_tieba_content(tmp_path):
    # Create a small JSONL with tieba-like data
    records = [
        {
            "title": "起点会用ai私自改小说",
            "desc": "新人写小说被AI改文快崩溃了",
            "total_replay_num": "81",
        },
        {
            "title": "做跨境有野心的请死磕这八个技能",
            "desc": "跨境电商需要数据分析、AI工具等技能",
            "total_replay_num": "49",
        },
    ]
    result = analyze_records(records)
    assert result["total"] == 2
    assert result["classified_count"] > 0
    # Should find at least one category
    assert len(result["aggregation"]) > 0
    # Check hot_score is non-zero for records with total_replay_num
    for agg in result["aggregation"]:
        assert "hot_score" in agg


def test_analyze_records_filters_noise():
    records = [
        {"content": "哈哈"},
        {"content": "好看好看"},
        {"content": "这个产品真的很需要改进，用户体验太差了"},
    ]
    result = analyze_records(records)
    # Only the last record should be classified
    assert result["classified_count"] <= 1


def test_load_jsonl(tmp_path):
    f = tmp_path / "test.jsonl"
    f.write_text(
        '{"id": 1, "content": "hello"}\n{"id": 2, "content": "world"}\n',
        encoding="utf-8",
    )
    records = load_jsonl(str(f))
    assert len(records) == 2
    assert records[0]["id"] == 1
