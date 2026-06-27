# -*- coding: utf-8 -*-

from fastapi.testclient import TestClient

from api.main import app


def test_list_data_files_includes_jsonl_and_sqlite(monkeypatch, tmp_path):
    data_file = tmp_path / "xhs" / "jsonl" / "search_contents.jsonl"
    db_file = tmp_path / "xhs" / "sqlite" / "crawler.db"
    data_file.parent.mkdir(parents=True)
    db_file.parent.mkdir(parents=True)
    data_file.write_text('{"title":"需要自动整理评论需求"}\n', encoding="utf-8")
    db_file.write_bytes(b"sqlite")
    monkeypatch.setattr("api.routers.data.DATA_DIR", tmp_path)

    client = TestClient(app)
    response = client.get("/api/data/files")

    assert response.status_code == 200
    paths = {item["path"] for item in response.json()["files"]}
    assert "xhs\\jsonl\\search_contents.jsonl" in paths or "xhs/jsonl/search_contents.jsonl" in paths
    assert "xhs\\sqlite\\crawler.db" in paths or "xhs/sqlite/crawler.db" in paths


def test_sync_data_file_to_feishu_dry_run(monkeypatch, tmp_path):
    input_file = tmp_path / "xhs" / "jsonl" / "search_contents.jsonl"
    input_file.parent.mkdir(parents=True)
    input_file.write_text('{"title":"需要自动整理评论需求"}\n', encoding="utf-8")
    monkeypatch.setattr("api.routers.data.DATA_DIR", tmp_path)
    captured = {}

    def fake_run_sync(**kwargs):
        captured.update(kwargs)
        return type("Stats", (), {"success": 0, "skipped": 1, "failed": 0, "pending": 2})()

    monkeypatch.setattr("api.routers.data.run_sync", fake_run_sync)
    client = TestClient(app)

    response = client.post(
        "/api/data/sync-to-feishu",
        json={"file_path": "xhs/jsonl/search_contents.jsonl", "dry_run": True, "batch_size": 50},
    )

    assert response.status_code == 200
    assert response.json()["stats"] == {"success": 0, "skipped": 1, "failed": 0, "pending": 2}
    assert captured["input_path"] == input_file
    assert captured["input_format"] == "jsonl"
    assert captured["dry_run"] is True
    assert captured["batch_size"] == 50


def test_sync_data_file_rejects_path_traversal(monkeypatch, tmp_path):
    monkeypatch.setattr("api.routers.data.DATA_DIR", tmp_path)
    client = TestClient(app)

    response = client.post(
        "/api/data/sync-to-feishu",
        json={"file_path": "../secret.jsonl", "dry_run": True},
    )

    assert response.status_code == 403
