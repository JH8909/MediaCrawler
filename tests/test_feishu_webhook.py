from integrations import feishu_webhook


class _Response:
    def raise_for_status(self):
        return None


class _Client:
    payload = None

    def __init__(self, timeout):
        self.timeout = timeout

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def post(self, webhook_url, json):
        _Client.payload = json
        return _Response()


class _FailingClient(_Client):
    def post(self, webhook_url, json):
        raise RuntimeError("network down")


def test_send_crawl_summary_accepts_missing_stats(monkeypatch):
    monkeypatch.setattr(feishu_webhook.httpx, "Client", _Client)

    assert feishu_webhook.send_crawl_summary(
        platform="xhs",
        crawler_type="search",
        keywords="测试",
        webhook_url="https://example.com/hook",
    )
    assert _Client.payload["msg_type"] == "interactive"


def test_send_simple_message_returns_false_on_send_failure(monkeypatch):
    monkeypatch.setattr(feishu_webhook.httpx, "Client", _FailingClient)

    assert not feishu_webhook.send_simple_message(
        title="Collection Failed",
        content="Platform: xhs",
        webhook_url="https://example.com/hook",
    )
