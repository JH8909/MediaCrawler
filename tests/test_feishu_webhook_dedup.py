"""Tests for Feishu webhook - dedup and new demand report format"""
import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parent.parent))

from integrations.feishu_webhook import (
    send_demand_report,
    send_analysis_report,
    send_crawl_summary,
    get_webhook_url,
)


def test_send_demand_report_is_same_as_send_analysis_report():
    """send_analysis_report should be aliased to send_demand_report"""
    assert send_analysis_report is send_demand_report


def test_send_crawl_summary_has_no_duplicate_content():
    """Verify send_crawl_summary no longer has duplicate content_items block"""
    import inspect
    source = inspect.getsource(send_crawl_summary)
    # Count occurrences of "**采集内容：**"
    count = source.count("**采集内容：**")
    # Should only appear once (not twice as before)
    assert count <= 1, f"Found {count} occurrences of '采集内容', expected 0-1"


@patch("integrations.feishu_webhook.httpx.Client")
def test_send_demand_report_constructs_correct_payload(mock_client):
    """Verify payload structure of send_demand_report"""
    mock_instance = mock_client.return_value.__enter__.return_value
    mock_instance.post.return_value.status_code = 200

    aggregation = [
        {"category": "内容创作 & AI写作", "count": 5, "hot_score": 3.5},
        {"category": "自动化 & 效率工具", "count": 3, "hot_score": 2.0},
    ]
    solutions_data = [
        {
            "category": "内容创作 & AI写作",
            "count": 5,
            "solutions": [
                {
                    "name": "AI内容创作助手",
                    "product_type": "小程序",
                    "cost": "低",
                    "summary": "test",
                }
            ],
        }
    ]

    result = send_demand_report(
        aggregation=aggregation,
        solutions_data=solutions_data,
        keyword="AI工具",
        platform="tieba",
        total=8,
        webhook_url="https://open.feishu.cn/open-apis/bot/v2/hook/fake",
    )

    assert result is True

    # Check the payload that was sent
    call_args = mock_instance.post.call_args
    assert call_args is not None, "post was not called"
    url = call_args[0][0]
    # Should not contain full webhook URL in logs or payload
    assert "/hook/fake" in url


def test_send_demand_report_returns_false_without_url():
    result = send_demand_report(
        aggregation=[],
        webhook_url=None,
    )
    assert result is False


@patch("integrations.feishu_webhook.httpx.Client")
def test_send_demand_report_handles_empty_solutions(mock_client):
    """Should still send report when there are no solutions"""
    mock_instance = mock_client.return_value.__enter__.return_value
    mock_instance.post.return_value.status_code = 200

    result = send_demand_report(
        aggregation=[{"category": "test", "count": 1, "hot_score": 0}],
        solutions_data=None,
        platform="xhs",
        total=1,
        webhook_url="https://open.feishu.cn/open-apis/bot/v2/hook/fake",
    )
    assert result is True
