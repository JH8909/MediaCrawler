# -*- coding: utf-8 -*-

from fastapi.testclient import TestClient

from api.main import app


def test_api_updates_feishu_task(monkeypatch):
    captured = {}

    def fake_update(record_id, fields):
        captured["record_id"] = record_id
        captured["fields"] = fields
        return {"record": {"record_id": record_id}}

    monkeypatch.setattr("api.routers.feishu.update_feishu_task", fake_update)
    client = TestClient(app)

    response = client.put(
        "/api/feishu/tasks/rec1",
        json={
            "platform": "微博",
            "crawler_type": "关键词",
            "keywords": "科技新闻",
            "max_notes_count": 20,
            "login_type": "无需登录",
            "status": "待执行",
            "enable_comments": True,
            "enable_sub_comments": False,
        },
    )

    assert response.status_code == 200
    assert captured == {
        "record_id": "rec1",
        "fields": {
            "状态": "待执行",
            "平台": "微博",
            "采集类型": "关键词",
            "关键词": "科技新闻",
            "指定ID": "",
            "创作者ID": "",
            "最大数量": 20,
            "一级评论": True,
            "二级评论": False,
            "登录方式": "无需登录",
        },
    }
