# -*- coding: utf-8 -*-

import json
import subprocess
import sys
from pathlib import Path

from scripts.sync_to_feishu import (
    SyncStats,
    load_synced_hashes,
    read_input_records,
    run_sync,
    save_synced_hashes,
)


class FakeFeishuClient:
    def __init__(self):
        self.batches = []

    def batch_create_records(self, records):
        self.batches.append(records)
        return {"records": [{"record_id": str(i)} for i, _ in enumerate(records)]}


def test_synced_hash_state_round_trip(tmp_path):
    state_path = tmp_path / ".sync_state" / "feishu_synced_hashes.json"

    save_synced_hashes({"hash2", "hash1"}, state_path)

    assert load_synced_hashes(state_path) == {"hash1", "hash2"}


def test_read_jsonl_records(tmp_path):
    input_path = tmp_path / "data.jsonl"
    input_path.write_text(
        json.dumps({"title": "需求1"}, ensure_ascii=False) + "\n"
        + json.dumps({"title": "需求2"}, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    assert list(read_input_records(input_path, "jsonl")) == [
        {"title": "需求1"},
        {"title": "需求2"},
    ]


def test_read_jsonl_records_accepts_utf8_bom(tmp_path):
    input_path = tmp_path / "data_bom.jsonl"
    input_path.write_text(
        json.dumps({"title": "需求1"}, ensure_ascii=False) + "\n",
        encoding="utf-8-sig",
    )

    assert list(read_input_records(input_path, "jsonl")) == [{"title": "需求1"}]


def test_dry_run_does_not_create_client_or_write_state(tmp_path, capsys):
    input_path = tmp_path / "data.jsonl"
    input_path.write_text(
        json.dumps(
            {
                "platform": "xhs",
                "title": "需要AI绘画提示词工具",
                "desc": "想要一个可以根据商品图自动生成小红书风格提示词的工具。",
                "note_url": "https://www.xiaohongshu.com/explore/1",
            },
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )
    state_path = tmp_path / ".sync_state" / "feishu_synced_hashes.json"

    def fail_client_factory():
        raise AssertionError("dry-run must not create Feishu client")

    stats = run_sync(
        input_path=input_path,
        input_format="jsonl",
        dry_run=True,
        batch_size=100,
        state_path=state_path,
        client_factory=fail_client_factory,
    )

    captured = capsys.readouterr()
    assert "dry-run" in captured.out
    assert "需求标题" in captured.out
    assert stats == SyncStats(success=0, skipped=0, failed=0, pending=1)
    assert not state_path.exists()


def test_cli_dry_run_from_project_root_does_not_require_feishu_env(tmp_path):
    input_path = tmp_path / "data.jsonl"
    input_path.write_text(
        json.dumps(
            {
                "platform": "xhs",
                "title": "需要自动整理用户需求的工具",
                "desc": "希望从公开内容和评论中提取用户需求，自动去重并同步到飞书多维表格。",
                "note_url": "https://www.xiaohongshu.com/explore/cli-demo",
            },
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )

    result = subprocess.run(
        [
            sys.executable,
            "scripts/sync_to_feishu.py",
            "--input",
            str(input_path),
            "--format",
            "jsonl",
            "--dry-run",
        ],
        cwd=str(Path(__file__).parent.parent),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=30,
    )

    assert result.returncode == 0
    assert "dry-run" in result.stdout
    assert "需求标题" in result.stdout


def test_run_sync_skips_existing_hash_and_saves_new_hash(tmp_path):
    input_path = tmp_path / "data.jsonl"
    records = [
        {
            "platform": "xhs",
            "title": "需要AI绘画提示词工具",
            "desc": "想要一个可以根据商品图自动生成小红书风格提示词的工具。",
            "note_url": "https://www.xiaohongshu.com/explore/1",
        },
        {
            "platform": "xhs",
            "title": "需要视频剪辑自动化工具",
            "desc": "希望可以自动识别口播重点并生成短视频切片标题和字幕。",
            "note_url": "https://www.xiaohongshu.com/explore/2",
        },
    ]
    input_path.write_text(
        "\n".join(json.dumps(item, ensure_ascii=False) for item in records),
        encoding="utf-8",
    )
    state_path = tmp_path / ".sync_state" / "feishu_synced_hashes.json"

    first_client = FakeFeishuClient()
    first_stats = run_sync(
        input_path=input_path,
        input_format="jsonl",
        dry_run=False,
        batch_size=100,
        state_path=state_path,
        client_factory=lambda: first_client,
    )
    second_client = FakeFeishuClient()
    second_stats = run_sync(
        input_path=input_path,
        input_format="jsonl",
        dry_run=False,
        batch_size=100,
        state_path=state_path,
        client_factory=lambda: second_client,
    )

    assert first_stats.success == 2
    assert first_stats.skipped == 0
    assert len(first_client.batches) == 1
    assert second_stats.success == 0
    assert second_stats.skipped == 2
    assert second_client.batches == []
    assert len(load_synced_hashes(state_path)) == 2
