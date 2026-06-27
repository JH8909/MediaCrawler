# -*- coding: utf-8 -*-

import json
from pathlib import Path

from scripts.run_feishu_tasks import (
    CrawlerTask,
    build_crawler_command,
    load_pending_tasks,
    run_task,
)
from scripts.sync_to_feishu import SyncStats


class FakeTaskClient:
    def __init__(self, records=None):
        self.records = records or []
        self.updates = []

    def list_records(self, page_size=500):
        return self.records

    def update_record(self, record_id, fields):
        self.updates.append((record_id, fields))
        return {"record": {"record_id": record_id}}


class FakeResultClient:
    pass


class FakeCompletedProcess:
    def __init__(self, returncode=0, stdout="", stderr=""):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


def test_load_pending_tasks_filters_status():
    client = FakeTaskClient([
        {"record_id": "rec1", "fields": {"状态": "待执行", "平台": "xhs", "采集类型": "search", "关键词": "AI工具"}},
        {"record_id": "rec2", "fields": {"状态": "已完成", "平台": "dy", "采集类型": "search", "关键词": "副业"}},
    ])

    tasks = load_pending_tasks(client)

    assert [task.record_id for task in tasks] == ["rec1"]
    assert tasks[0].platform == "xhs"
    assert tasks[0].keywords == "AI工具"


def test_load_pending_tasks_normalizes_feishu_choices():
    client = FakeTaskClient([
        {
            "record_id": "rec1",
            "fields": {
                "状态": "待执行",
                "平台": "微博",
                "采集类型": "关键词",
                "关键词": "AI工具",
                "登录方式": "无需登录",
            },
        },
    ])

    tasks = load_pending_tasks(client)

    assert tasks[0].platform == "wb"
    assert tasks[0].crawler_type == "search"
    assert tasks[0].login_type == "qrcode"


def test_load_pending_tasks_can_filter_record_id():
    client = FakeTaskClient([
        {"record_id": "rec1", "fields": {"状态": "待执行", "平台": "xhs", "采集类型": "search", "关键词": "AI工具"}},
        {"record_id": "rec2", "fields": {"状态": "待执行", "平台": "dy", "采集类型": "search", "关键词": "旅游"}},
    ])

    tasks = load_pending_tasks(client, record_id="rec2")

    assert [task.record_id for task in tasks] == ["rec2"]


def test_build_crawler_command_for_search_task(tmp_path):
    task = CrawlerTask(
        record_id="rec1",
        platform="xhs",
        crawler_type="search",
        keywords="AI工具",
        max_notes_count=20,
        enable_comments=True,
        enable_sub_comments=False,
        login_type="qrcode",
    )

    cmd = build_crawler_command(task, tmp_path)

    assert cmd == [
        "uv",
        "run",
        "python",
        "main.py",
        "--platform",
        "xhs",
        "--lt",
        "qrcode",
        "--type",
        "search",
        "--save_data_option",
        "jsonl",
        "--save_data_path",
        str(tmp_path),
        "--crawler_max_notes_count",
        "20",
        "--get_comment",
        "true",
        "--get_sub_comment",
        "false",
        "--keywords",
        "AI工具",
    ]


def test_run_task_updates_status_runs_crawler_and_syncs_jsonl(tmp_path):
    task = CrawlerTask(
        record_id="rec1",
        platform="xhs",
        crawler_type="search",
        keywords="AI工具",
        max_notes_count=5,
    )
    task_client = FakeTaskClient()
    result_client = FakeResultClient()
    commands = []
    synced_inputs = []

    def fake_run_command(cmd, cwd, capture_output, text, encoding, errors, timeout):
        commands.append(cmd)
        output_file = tmp_path / "feishu_task_runs" / "rec1" / "xhs" / "jsonl" / "search_contents_20260101.jsonl"
        output_file.parent.mkdir(parents=True, exist_ok=True)
        output_file.write_text(
            json.dumps(
                {
                    "platform": "xhs",
                    "title": "需要自动整理评论需求",
                    "desc": "希望把公开评论里的需求自动整理到飞书多维表格并去重。",
                    "note_url": "https://www.xiaohongshu.com/explore/1",
                },
                ensure_ascii=False,
            )
            + "\n",
            encoding="utf-8",
        )
        return FakeCompletedProcess(returncode=0, stdout="ok")

    def fake_sync_func(**kwargs):
        synced_inputs.append(kwargs["input_path"])
        assert kwargs["client_factory"]() is result_client
        return SyncStats(success=2, skipped=1, failed=0)

    stats = run_task(
        task=task,
        task_client=task_client,
        result_client=result_client,
        project_root=Path("."),
        state_dir=tmp_path,
        run_command=fake_run_command,
        sync_func=fake_sync_func,
    )

    assert stats.success == 2
    assert commands[0][commands[0].index("--platform") + 1] == "xhs"
    assert synced_inputs[0].name == "search_contents_20260101.jsonl"
    assert task_client.updates[0] == ("rec1", {"状态": "运行中", "错误信息": ""})
    assert task_client.updates[-1][0] == "rec1"
    assert task_client.updates[-1][1]["状态"] == "已完成"
    assert task_client.updates[-1][1]["成功条数"] == 2
    assert task_client.updates[-1][1]["跳过条数"] == 1


def test_run_task_dry_run_does_not_execute_or_update(tmp_path):
    task = CrawlerTask(
        record_id="rec1",
        platform="xhs",
        crawler_type="search",
        keywords="AI工具",
    )
    task_client = FakeTaskClient()

    def fail_run_command(*args, **kwargs):
        raise AssertionError("dry-run must not run crawler")

    stats = run_task(
        task=task,
        task_client=task_client,
        result_client=FakeResultClient(),
        project_root=Path("."),
        state_dir=tmp_path,
        run_command=fail_run_command,
        dry_run=True,
    )

    assert stats.pending == 1
    assert task_client.updates == []
