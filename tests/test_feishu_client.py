# -*- coding: utf-8 -*-

import pytest

from integrations.feishu_client import FeishuAPIError, FeishuBitableClient


class FakeResponse:
    def __init__(self, status_code=200, payload=None, text=""):
        self.status_code = status_code
        self._payload = payload or {}
        self.text = text

    def json(self):
        return self._payload


class FakeHttpClient:
    def __init__(self, responses):
        self.responses = list(responses)
        self.requests = []

    def get(self, url, **kwargs):
        self.requests.append({"method": "GET", "url": url, **kwargs})
        return self.responses.pop(0)

    def post(self, url, **kwargs):
        self.requests.append({"method": "POST", "url": url, **kwargs})
        return self.responses.pop(0)

    def put(self, url, **kwargs):
        self.requests.append({"method": "PUT", "url": url, **kwargs})
        return self.responses.pop(0)


def test_build_batch_payload_wraps_fields_as_records():
    payload = FeishuBitableClient.build_batch_payload([
        {"需求标题": "需求1", "内容哈希": "hash1"},
        {"需求标题": "需求2", "内容哈希": "hash2"},
    ])

    assert payload == {
        "records": [
            {"fields": {"需求标题": "需求1", "内容哈希": "hash1"}},
            {"fields": {"需求标题": "需求2", "内容哈希": "hash2"}},
        ]
    }


def test_batch_create_rejects_more_than_500_records():
    client = FeishuBitableClient(
        app_id="app_id",
        app_secret="app_secret",
        app_token="app_token",
        table_id="table_id",
        http_client=FakeHttpClient([]),
    )

    with pytest.raises(ValueError, match="500"):
        client.batch_create_records([{"需求标题": str(i)} for i in range(501)])


def test_batch_create_fetches_token_and_posts_records_without_logging_token():
    http_client = FakeHttpClient([
        FakeResponse(payload={"code": 0, "tenant_access_token": "tenant-token"}),
        FakeResponse(payload={"code": 0, "data": {"records": [{"record_id": "rec1"}]}}),
    ])
    client = FeishuBitableClient(
        app_id="app_id",
        app_secret="app_secret",
        app_token="app_token",
        table_id="table_id",
        http_client=http_client,
    )

    result = client.batch_create_records([{"需求标题": "需求1"}])

    assert result == {"records": [{"record_id": "rec1"}]}
    assert http_client.requests[0]["json"] == {
        "app_id": "app_id",
        "app_secret": "app_secret",
    }
    assert http_client.requests[1]["headers"]["Authorization"] == "Bearer tenant-token"
    assert "tenant-token" not in repr(result)


def test_batch_create_retries_http_errors_then_succeeds():
    http_client = FakeHttpClient([
        FakeResponse(payload={"code": 0, "tenant_access_token": "tenant-token"}),
        FakeResponse(status_code=500, payload={"code": 999, "msg": "server error"}),
        FakeResponse(payload={"code": 0, "data": {"records": []}}),
    ])
    client = FeishuBitableClient(
        app_id="app_id",
        app_secret="app_secret",
        app_token="app_token",
        table_id="table_id",
        http_client=http_client,
        max_retries=2,
        retry_interval=0,
    )

    assert client.batch_create_records([{"需求标题": "需求1"}]) == {"records": []}
    assert len(http_client.requests) == 3


def test_batch_create_raises_clear_error_after_api_failure():
    http_client = FakeHttpClient([
        FakeResponse(payload={"code": 0, "tenant_access_token": "tenant-token"}),
        FakeResponse(payload={"code": 1254000, "msg": "bad request"}),
    ])
    client = FeishuBitableClient(
        app_id="app_id",
        app_secret="app_secret",
        app_token="app_token",
        table_id="table_id",
        http_client=http_client,
        max_retries=1,
        retry_interval=0,
    )

    with pytest.raises(FeishuAPIError, match="bad request"):
        client.batch_create_records([{"需求标题": "需求1"}])


def test_list_records_paginates_until_done():
    http_client = FakeHttpClient([
        FakeResponse(payload={"code": 0, "tenant_access_token": "tenant-token"}),
        FakeResponse(payload={
            "code": 0,
            "data": {
                "items": [{"record_id": "rec1", "fields": {"状态": "待执行"}}],
                "has_more": True,
                "page_token": "next-token",
            },
        }),
        FakeResponse(payload={
            "code": 0,
            "data": {
                "items": [{"record_id": "rec2", "fields": {"状态": "已完成"}}],
                "has_more": False,
            },
        }),
    ])
    client = FeishuBitableClient(
        app_id="app_id",
        app_secret="app_secret",
        app_token="app_token",
        table_id="task_table_id",
        http_client=http_client,
    )

    records = client.list_records(page_size=1)

    assert [item["record_id"] for item in records] == ["rec1", "rec2"]
    assert http_client.requests[1]["method"] == "GET"
    assert http_client.requests[1]["params"] == {"page_size": 1}
    assert http_client.requests[2]["params"] == {
        "page_size": 1,
        "page_token": "next-token",
    }


def test_update_record_puts_fields():
    http_client = FakeHttpClient([
        FakeResponse(payload={"code": 0, "tenant_access_token": "tenant-token"}),
        FakeResponse(payload={"code": 0, "data": {"record": {"record_id": "rec1"}}}),
    ])
    client = FeishuBitableClient(
        app_id="app_id",
        app_secret="app_secret",
        app_token="app_token",
        table_id="task_table_id",
        http_client=http_client,
    )

    result = client.update_record("rec1", {"状态": "运行中"})

    assert result == {"record": {"record_id": "rec1"}}
    assert http_client.requests[1]["method"] == "PUT"
    assert http_client.requests[1]["json"] == {"fields": {"状态": "运行中"}}
