# Auto Demand Excel Feishu Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a local automated demand-discovery workflow that uses existing MediaCrawler CLI output, generates an Excel report, and sends a Feishu webhook summary with the local file path.

**Architecture:** Add a new `integrations/demand_report/` package for keyword generation, demand extraction, Excel writing, and orchestration support. Add script and API/WebUI layers that call MediaCrawler through the existing CLI rather than changing any core crawler code. Reuse the existing Feishu webhook integration, but make it safe for report summaries and prevent sensitive logging.

**Tech Stack:** Python 3.11, FastAPI, Pydantic v2, `openpyxl`, `httpx`, pytest, plain static HTML/CSS/JS.

---

## Scope Rules

- Do not modify `media_platform/`, `base/`, or crawler core implementations.
- Do not use Feishu Bitable for this feature.
- Do not upload files to Feishu in this MVP.
- Do not log Cookie values, tokens, webhook URLs, or account credentials.
- Keep all Feishu API/webhook tests mocked.

## File Structure

- Create `integrations/demand_report/__init__.py`
  - Package exports for the demand-report modules.
- Create `integrations/demand_report/keywords.py`
  - Built-in domain words, demand words, deterministic keyword generation.
- Create `integrations/demand_report/models.py`
  - Dataclasses for `KeywordPlan`, `DemandItem`, `DemandReportStats`, `DemandRunResult`.
- Create `integrations/demand_report/extractor.py`
  - Read MediaCrawler export rows and convert candidate comments/body text into `DemandItem`.
- Create `integrations/demand_report/excel_writer.py`
  - Write `.xlsx` reports with stable columns and basic filtering.
- Create `integrations/demand_report/state.py`
  - Load/save synced hashes from `.sync_state/demand_excel_synced_hashes.json`.
- Create `integrations/demand_report/runner.py`
  - Orchestrate keyword generation, CLI execution, export discovery, extraction, Excel writing, and webhook notification.
- Modify `integrations/feishu_webhook.py`
  - Fix `stats=None` bug and add `send_demand_report_summary`.
- Create `scripts/auto_demand_report.py`
  - CLI entrypoint for manual/dry-run report generation.
- Create `scripts/auto_demand_scheduler.py`
  - CLI scheduler loop for 3h/6h/12h/day/week intervals.
- Create `api/schemas/auto_demand.py`
  - Request/response schemas for UI config and run controls.
- Create `api/services/auto_demand_manager.py`
  - In-process singleton manager for status, config, logs, non-reentry, subprocess start/stop.
- Create `api/routers/auto_demand.py`
  - FastAPI endpoints for status/config/run/start/stop/logs.
- Modify `api/routers/__init__.py`
  - Export `auto_demand_router`.
- Modify `api/main.py`
  - Include the auto-demand router.
- Modify `api/webui/index.html`
  - Add an “自动需求采集” panel.
- Modify `api/webui/dashboard.css`
  - Style the new panel in the existing console style.
- Modify `api/webui/dashboard.js`
  - Load status/config, save interval, manual run, start/stop scheduler, render logs.
- Modify `api/services/crawler_manager.py`
  - Redact `--cookies` values from logged commands.
- Test files:
  - Create `tests/test_demand_keywords.py`
  - Create `tests/test_demand_extractor.py`
  - Create `tests/test_demand_excel_writer.py`
  - Create `tests/test_auto_demand_runner.py`
  - Create `tests/test_auto_demand_api.py`
  - Create `tests/test_feishu_webhook_report.py`
  - Add/modify crawler-manager safety tests in `tests/test_crawler_manager_security.py`

---

### Task 1: Keyword Generation

**Files:**
- Create: `integrations/demand_report/__init__.py`
- Create: `integrations/demand_report/models.py`
- Create: `integrations/demand_report/keywords.py`
- Test: `tests/test_demand_keywords.py`

- [ ] **Step 1: Write failing tests for deterministic keyword plans**

Create `tests/test_demand_keywords.py`:

```python
from integrations.demand_report.keywords import (
    DEMAND_WORDS,
    DOMAIN_WORDS,
    generate_keyword_plans,
)


def test_generate_keyword_plans_uses_domain_and_demand_words():
    plans = generate_keyword_plans(count=3, offset=0)

    assert [plan.keyword for plan in plans] == [
        f"{DOMAIN_WORDS[0]} {DEMAND_WORDS[0]}",
        f"{DOMAIN_WORDS[1]} {DEMAND_WORDS[1]}",
        f"{DOMAIN_WORDS[2]} {DEMAND_WORDS[2]}",
    ]
    assert plans[0].domain == DOMAIN_WORDS[0]
    assert plans[0].demand_word == DEMAND_WORDS[0]


def test_generate_keyword_plans_supports_offset_rotation():
    plans = generate_keyword_plans(count=2, offset=14)

    assert len(plans) == 2
    assert plans[0].keyword == f"{DOMAIN_WORDS[14 % len(DOMAIN_WORDS)]} {DEMAND_WORDS[14 % len(DEMAND_WORDS)]}"


def test_generate_keyword_plans_rejects_invalid_count():
    try:
        generate_keyword_plans(count=0)
    except ValueError as exc:
        assert "count must be between 1 and 100" in str(exc)
    else:
        raise AssertionError("expected ValueError")
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
uv run pytest tests/test_demand_keywords.py -q
```

Expected: FAIL because `integrations.demand_report` does not exist.

- [ ] **Step 3: Add minimal models and keyword generator**

Create `integrations/demand_report/__init__.py`:

```python
# -*- coding: utf-8 -*-
```

Create `integrations/demand_report/models.py`:

```python
# -*- coding: utf-8 -*-

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List


@dataclass(frozen=True)
class KeywordPlan:
    keyword: str
    domain: str
    demand_word: str


@dataclass(frozen=True)
class DemandItem:
    title: str
    raw_text: str
    content_type: str
    platform: str
    keyword: str
    domain: str
    demand_word: str
    source_url: str
    author: str
    publish_time: object
    crawl_time: object
    content_hash: str
    note: str = ""


@dataclass(frozen=True)
class DemandReportStats:
    total: int = 0
    comment_count: int = 0
    body_count: int = 0
    skipped: int = 0
    duplicates: int = 0
    failed_tasks: int = 0


@dataclass(frozen=True)
class DemandRunResult:
    excel_path: Path | None
    stats: DemandReportStats
    keywords: List[KeywordPlan]
    export_files: List[Path]
    errors: List[str]

    def stats_dict(self) -> Dict[str, int]:
        return {
            "total": self.stats.total,
            "comment_count": self.stats.comment_count,
            "body_count": self.stats.body_count,
            "skipped": self.stats.skipped,
            "duplicates": self.stats.duplicates,
            "failed_tasks": self.stats.failed_tasks,
        }
```

Create `integrations/demand_report/keywords.py`:

```python
# -*- coding: utf-8 -*-

from __future__ import annotations

from .models import KeywordPlan


DOMAIN_WORDS = [
    "AI工具",
    "装修",
    "旅游",
    "副业",
    "母婴",
    "数码",
    "美妆",
    "教育",
    "职场",
    "健康",
    "宠物",
    "家居",
    "汽车",
    "餐饮",
    "本地生活",
]

DEMAND_WORDS = [
    "求推荐",
    "避坑",
    "踩雷",
    "哪个好",
    "值不值",
    "怎么选",
    "怎么买",
    "预算",
    "平替",
    "后悔",
    "有没有必要",
    "攻略",
    "推荐一下",
    "真实体验",
    "注意事项",
]


def generate_keyword_plans(count: int = 5, offset: int = 0) -> list[KeywordPlan]:
    if count < 1 or count > 100:
        raise ValueError("count must be between 1 and 100")

    plans: list[KeywordPlan] = []
    for index in range(count):
        position = offset + index
        domain = DOMAIN_WORDS[position % len(DOMAIN_WORDS)]
        demand_word = DEMAND_WORDS[position % len(DEMAND_WORDS)]
        plans.append(
            KeywordPlan(
                keyword=f"{domain} {demand_word}",
                domain=domain,
                demand_word=demand_word,
            )
        )
    return plans
```

- [ ] **Step 4: Run keyword tests**

Run:

```bash
uv run pytest tests/test_demand_keywords.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add integrations/demand_report/__init__.py integrations/demand_report/models.py integrations/demand_report/keywords.py tests/test_demand_keywords.py
git commit -m "feat: add demand keyword generation"
```

---

### Task 2: Demand Extraction and Dedup State

**Files:**
- Create: `integrations/demand_report/extractor.py`
- Create: `integrations/demand_report/state.py`
- Test: `tests/test_demand_extractor.py`

- [ ] **Step 1: Write failing extraction tests**

Create `tests/test_demand_extractor.py`:

```python
from pathlib import Path

from integrations.demand_report.extractor import extract_demand_item
from integrations.demand_report.keywords import generate_keyword_plans
from integrations.demand_report.state import load_hashes, save_hashes


def test_extract_comment_demand_has_comment_priority():
    plan = generate_keyword_plans(count=1)[0]
    item = extract_demand_item(
        {
            "platform": "xhs",
            "comment": "预算有限，求推荐一个适合新手用的AI工具？",
            "desc": "这是一篇普通正文介绍",
            "note_url": "https://example.com/note/1",
            "nickname": "用户A",
            "create_time": "2026-06-27",
        },
        keyword_plan=plan,
    )

    assert item is not None
    assert item.content_type == "评论"
    assert item.raw_text == "预算有限，求推荐一个适合新手用的AI工具？"
    assert item.keyword == plan.keyword
    assert item.domain == plan.domain
    assert item.demand_word == plan.demand_word
    assert len(item.content_hash) == 64


def test_extract_body_demand_when_comment_missing():
    plan = generate_keyword_plans(count=1)[0]
    item = extract_demand_item(
        {
            "platform": "wb",
            "title": "装修避坑经验",
            "desc": "装修预算有限，到底怎么选材料才不会踩雷？",
            "url": "https://example.com/post/1",
        },
        keyword_plan=plan,
    )

    assert item is not None
    assert item.content_type == "正文"
    assert "怎么选材料" in item.raw_text


def test_extract_skips_short_or_non_demand_text():
    plan = generate_keyword_plans(count=1)[0]
    item = extract_demand_item({"platform": "xhs", "comment": "好看"}, keyword_plan=plan)

    assert item is None


def test_hash_state_roundtrip(tmp_path: Path):
    state_path = tmp_path / "hashes.json"

    assert load_hashes(state_path) == set()
    save_hashes({"a", "b"}, state_path)
    assert load_hashes(state_path) == {"a", "b"}
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
uv run pytest tests/test_demand_extractor.py -q
```

Expected: FAIL because extractor and state modules do not exist.

- [ ] **Step 3: Implement extractor and state**

Create `integrations/demand_report/state.py`:

```python
# -*- coding: utf-8 -*-

from __future__ import annotations

import json
from pathlib import Path
from typing import Set


DEFAULT_DEMAND_STATE_PATH = Path(".sync_state") / "demand_excel_synced_hashes.json"


def load_hashes(state_path: Path = DEFAULT_DEMAND_STATE_PATH) -> Set[str]:
    if not state_path.exists():
        return set()
    data = json.loads(state_path.read_text(encoding="utf-8"))
    if isinstance(data, list):
        return {str(item) for item in data}
    if isinstance(data, dict):
        return {str(item) for item in data.get("hashes", [])}
    raise ValueError(f"Invalid demand state format: {state_path}")


def save_hashes(hashes: Set[str], state_path: Path = DEFAULT_DEMAND_STATE_PATH) -> None:
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text(
        json.dumps(sorted(hashes), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
```

Create `integrations/demand_report/extractor.py`:

```python
# -*- coding: utf-8 -*-

from __future__ import annotations

import hashlib
import json
import re
from typing import Any, Dict, Optional

from .models import DemandItem, KeywordPlan


COMMENT_FIELDS = ["comment", "comment_content", "content", "评论内容"]
BODY_FIELDS = ["desc", "description", "content_text", "full_text", "text", "正文"]
TITLE_FIELDS = ["title", "标题"]
URL_FIELDS = ["source_url", "url", "note_url", "share_url", "content_url", "video_url", "原文链接", "来源链接"]
AUTHOR_FIELDS = ["nickname", "author", "user_name", "用户名", "作者"]
PUBLISH_FIELDS = ["publish_time", "create_time", "created_time", "time", "发布时间"]
CRAWL_FIELDS = ["crawl_time", "add_ts", "last_modify_ts", "采集时间"]
DEMAND_PATTERNS = [
    "求推荐",
    "避坑",
    "踩雷",
    "哪个好",
    "值不值",
    "怎么选",
    "怎么买",
    "预算",
    "平替",
    "后悔",
    "有没有必要",
    "攻略",
    "推荐一下",
    "真实体验",
    "注意事项",
    "吗",
    "？",
    "?",
]


def extract_demand_item(record: Dict[str, Any], keyword_plan: KeywordPlan) -> Optional[DemandItem]:
    raw_text = _clean_text(_first_text(record, COMMENT_FIELDS))
    content_type = "评论"
    if not raw_text:
        body_text = _first_text(record, BODY_FIELDS)
        title_text = _first_text(record, TITLE_FIELDS)
        raw_text = _clean_text(" ".join(part for part in [title_text, body_text] if part))
        content_type = "正文"

    if not _is_demand_text(raw_text):
        return None

    source_url = _first_text(record, URL_FIELDS)
    platform = _infer_platform(record, source_url)
    content_hash = build_content_hash(platform, source_url, raw_text)

    return DemandItem(
        title=_make_title(raw_text),
        raw_text=raw_text,
        content_type=content_type,
        platform=platform,
        keyword=keyword_plan.keyword,
        domain=keyword_plan.domain,
        demand_word=keyword_plan.demand_word,
        source_url=source_url,
        author=_first_text(record, AUTHOR_FIELDS),
        publish_time=_first_value(record, PUBLISH_FIELDS),
        crawl_time=_first_value(record, CRAWL_FIELDS),
        content_hash=content_hash,
        note="",
    )


def build_content_hash(platform: str, source_url: str, raw_text: str) -> str:
    payload = f"{platform}{source_url}{raw_text}".encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _is_demand_text(value: str) -> bool:
    text = _clean_text(value)
    if _count_chinese_chars(text) < 10:
        return False
    if _looks_like_noise(text):
        return False
    return any(pattern in text for pattern in DEMAND_PATTERNS)


def _looks_like_noise(value: str) -> bool:
    text = value.strip()
    if not text:
        return True
    if re.fullmatch(r"https?://\S+", text):
        return True
    if re.fullmatch(r"[\W_]+", text):
        return True
    ad_words = ["抽奖", "关注我", "私信领取", "领券", "返现"]
    return any(word in text for word in ad_words)


def _first_text(record: Dict[str, Any], keys: list[str]) -> str:
    value = _first_value(record, keys)
    if value is None:
        return ""
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False, sort_keys=True)
    return str(value).strip()


def _first_value(record: Dict[str, Any], keys: list[str]) -> Any:
    for key in keys:
        value = record.get(key)
        if value not in (None, ""):
            return value
    return ""


def _clean_text(value: str) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _count_chinese_chars(value: str) -> int:
    return len(re.findall(r"[\u4e00-\u9fff]", value or ""))


def _make_title(value: str, max_len: int = 60) -> str:
    text = _clean_text(value)
    if len(text) <= max_len:
        return text
    return text[:max_len].rstrip() + "..."


def _infer_platform(record: Dict[str, Any], source_url: str) -> str:
    explicit = _first_text(record, ["platform", "source_platform", "来源平台"])
    if explicit:
        return explicit
    url = (source_url or "").lower()
    if "xiaohongshu.com" in url or "rednote.com" in url:
        return "xhs"
    if "douyin.com" in url:
        return "dy"
    if "kuaishou.com" in url:
        return "ks"
    if "bilibili.com" in url:
        return "bili"
    if "weibo.com" in url:
        return "wb"
    if "tieba.baidu.com" in url:
        return "tieba"
    if "zhihu.com" in url:
        return "zhihu"
    return "unknown"
```

- [ ] **Step 4: Run extraction tests**

Run:

```bash
uv run pytest tests/test_demand_extractor.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add integrations/demand_report/extractor.py integrations/demand_report/state.py tests/test_demand_extractor.py
git commit -m "feat: extract demand rows from exports"
```

---

### Task 3: Excel Writer

**Files:**
- Create: `integrations/demand_report/excel_writer.py`
- Test: `tests/test_demand_excel_writer.py`

- [ ] **Step 1: Write failing Excel writer tests**

Create `tests/test_demand_excel_writer.py`:

```python
from pathlib import Path

from openpyxl import load_workbook

from integrations.demand_report.excel_writer import DEMAND_REPORT_COLUMNS, write_demand_report
from integrations.demand_report.keywords import generate_keyword_plans
from integrations.demand_report.models import DemandItem


def test_write_demand_report_creates_xlsx(tmp_path: Path):
    plan = generate_keyword_plans(count=1)[0]
    item = DemandItem(
        title="预算有限求推荐AI工具",
        raw_text="预算有限，求推荐一个适合新手用的AI工具？",
        content_type="评论",
        platform="xhs",
        keyword=plan.keyword,
        domain=plan.domain,
        demand_word=plan.demand_word,
        source_url="https://example.com/note/1",
        author="用户A",
        publish_time="2026-06-27",
        crawl_time="2026-06-27 12:00:00",
        content_hash="a" * 64,
    )

    output_path = write_demand_report([item], output_dir=tmp_path, now_text="2026-06-27-1200")

    assert output_path.exists()
    assert output_path.name == "2026-06-27-1200-demand-report.xlsx"
    workbook = load_workbook(output_path)
    sheet = workbook.active
    assert [cell.value for cell in sheet[1]] == DEMAND_REPORT_COLUMNS
    assert sheet["A2"].value == "预算有限求推荐AI工具"
    assert sheet["C2"].value == "评论"
    assert sheet.auto_filter.ref == "A1:M2"


def test_write_demand_report_rejects_empty_items(tmp_path: Path):
    try:
        write_demand_report([], output_dir=tmp_path, now_text="2026-06-27-1200")
    except ValueError as exc:
        assert "no demand items to write" in str(exc)
    else:
        raise AssertionError("expected ValueError")
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
uv run pytest tests/test_demand_excel_writer.py -q
```

Expected: FAIL because writer does not exist.

- [ ] **Step 3: Implement Excel writer**

Create `integrations/demand_report/excel_writer.py`:

```python
# -*- coding: utf-8 -*-

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill

from .models import DemandItem


DEMAND_REPORT_COLUMNS = [
    "需求标题",
    "需求原文",
    "内容类型",
    "来源平台",
    "自动关键词",
    "领域",
    "需求词",
    "来源链接",
    "作者/昵称",
    "发布时间",
    "采集时间",
    "内容哈希",
    "备注",
]


def write_demand_report(
    items: list[DemandItem],
    output_dir: Path = Path("output") / "demand_reports",
    now_text: str | None = None,
) -> Path:
    if not items:
        raise ValueError("no demand items to write")

    output_dir.mkdir(parents=True, exist_ok=True)
    if now_text is None:
        now_text = datetime.now().strftime("%Y-%m-%d-%H%M")
    output_path = output_dir / f"{now_text}-demand-report.xlsx"

    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "需求采集"
    sheet.append(DEMAND_REPORT_COLUMNS)

    for item in items:
        sheet.append(
            [
                item.title,
                item.raw_text,
                item.content_type,
                item.platform,
                item.keyword,
                item.domain,
                item.demand_word,
                item.source_url,
                item.author,
                item.publish_time,
                item.crawl_time,
                item.content_hash,
                item.note,
            ]
        )

    header_fill = PatternFill("solid", fgColor="EAF2FF")
    for cell in sheet[1]:
        cell.font = Font(bold=True)
        cell.fill = header_fill
    sheet.freeze_panes = "A2"
    sheet.auto_filter.ref = f"A1:M{len(items) + 1}"
    widths = [24, 60, 12, 12, 18, 14, 14, 36, 18, 20, 20, 20, 20]
    for index, width in enumerate(widths, start=1):
        sheet.column_dimensions[chr(64 + index)].width = width

    workbook.save(output_path)
    return output_path
```

- [ ] **Step 4: Run Excel writer tests**

Run:

```bash
uv run pytest tests/test_demand_excel_writer.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add integrations/demand_report/excel_writer.py tests/test_demand_excel_writer.py
git commit -m "feat: write demand report excel files"
```

---

### Task 4: Feishu Webhook Report Notification

**Files:**
- Modify: `integrations/feishu_webhook.py`
- Test: `tests/test_feishu_webhook_report.py`

- [ ] **Step 1: Write failing webhook tests**

Create `tests/test_feishu_webhook_report.py`:

```python
from integrations.feishu_webhook import send_crawl_summary, send_demand_report_summary


class FakeResponse:
    status_code = 200
    text = '{"StatusCode":0}'

    def raise_for_status(self):
        return None


class FakeClient:
    def __init__(self, timeout):
        self.timeout = timeout
        self.requests = []

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def post(self, url, json):
        self.requests.append((url, json))
        FakeClient.last_request = (url, json)
        return FakeResponse()


def test_send_crawl_summary_accepts_missing_stats(monkeypatch):
    monkeypatch.setattr("integrations.feishu_webhook.httpx.Client", FakeClient)

    assert send_crawl_summary(
        platform="xhs",
        crawler_type="search",
        keywords="AI工具 推荐",
        stats=None,
        webhook_url="https://example.com/webhook",
    )


def test_send_demand_report_summary_sends_path_without_upload(monkeypatch):
    monkeypatch.setattr("integrations.feishu_webhook.httpx.Client", FakeClient)

    assert send_demand_report_summary(
        interval_label="每 6 小时",
        platforms=["xhs", "wb"],
        keywords=["AI工具 推荐", "装修 避坑"],
        stats={"total": 2, "comment_count": 1, "body_count": 1, "duplicates": 3, "failed_tasks": 0},
        excel_path="E:/demo/report.xlsx",
        webhook_url="https://example.com/webhook",
    )

    _, payload = FakeClient.last_request
    content = payload["card"]["elements"][0]["content"]
    assert "自动需求采集完成" in payload["card"]["header"]["title"]["content"]
    assert "E:/demo/report.xlsx" in content
    assert "AI工具 推荐 / 装修 避坑" in content
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
uv run pytest tests/test_feishu_webhook_report.py -q
```

Expected: FAIL because `send_crawl_summary` currently breaks with `stats=None` and `send_demand_report_summary` does not exist.

- [ ] **Step 3: Fix webhook functions**

Modify `integrations/feishu_webhook.py`:

```python
def send_crawl_summary(
    platform: str,
    crawler_type: str,
    keywords: str,
    stats: Optional[Dict[str, int]] = None,
    file_paths: Optional[List[str]] = None,
    content_items: Optional[List[Dict[str, str]]] = None,
    webhook_url: Optional[str] = None,
) -> bool:
    """Send a crawl completion summary to Feishu group chat via webhook"""
    stats = stats or {}
    if not webhook_url:
        webhook_url = get_webhook_url()
    if not webhook_url:
        return False
    ...
```

Add this function in the same file:

```python
def send_demand_report_summary(
    interval_label: str,
    platforms: List[str],
    keywords: List[str],
    stats: Dict[str, int],
    excel_path: str,
    webhook_url: Optional[str] = None,
) -> bool:
    if not webhook_url:
        webhook_url = get_webhook_url()
    if not webhook_url:
        return False

    stats = stats or {}
    fields_lines = [
        "**周期：** " + interval_label,
        "**平台：** " + ("、".join(platforms) if platforms else "-"),
        "**本轮关键词：** " + (" / ".join(keywords) if keywords else "-"),
        "",
        "**统计：**",
        "- 新增需求：" + str(stats.get("total", 0)) + " 条",
        "- 评论需求：" + str(stats.get("comment_count", 0)) + " 条",
        "- 正文需求：" + str(stats.get("body_count", 0)) + " 条",
        "- 跳过重复：" + str(stats.get("duplicates", 0)) + " 条",
        "- 失败任务：" + str(stats.get("failed_tasks", 0)) + " 个",
        "",
        "**Excel 文件：**",
        excel_path or "本轮没有生成 Excel 文件",
    ]
    payload = {
        "msg_type": "interactive",
        "card": {
            "header": {
                "title": {"tag": "plain_text", "content": "MediaCrawler 自动需求采集完成"},
                "template": "green" if stats.get("failed_tasks", 0) == 0 else "orange",
            },
            "elements": [
                {"tag": "markdown", "content": "\n".join(fields_lines)},
                {"tag": "hr"},
                {"tag": "note", "elements": [{"tag": "plain_text", "content": "仅发送本机文件路径，不上传文件"}]},
            ],
        },
    }
    try:
        with httpx.Client(timeout=15.0) as client:
            response = client.post(webhook_url, json=payload)
            response.raise_for_status()
            return True
    except Exception as exc:
        print("[FeishuWebhook] Failed to send demand report summary: " + str(exc))
        return False
```

- [ ] **Step 4: Run webhook tests**

Run:

```bash
uv run pytest tests/test_feishu_webhook_report.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add integrations/feishu_webhook.py tests/test_feishu_webhook_report.py
git commit -m "feat: send demand report feishu summary"
```

---

### Task 5: Runner Orchestration and CLI

**Files:**
- Create: `integrations/demand_report/runner.py`
- Create: `scripts/auto_demand_report.py`
- Test: `tests/test_auto_demand_runner.py`

- [ ] **Step 1: Write failing runner tests**

Create `tests/test_auto_demand_runner.py`:

```python
import json
import subprocess
from pathlib import Path

from integrations.demand_report.runner import run_auto_demand_report


def test_run_auto_demand_report_dry_run_does_not_execute(tmp_path: Path):
    calls = []

    result = run_auto_demand_report(
        platforms=["xhs"],
        keyword_count=2,
        max_notes_count=5,
        output_dir=tmp_path / "reports",
        export_root=tmp_path / "exports",
        dry_run=True,
        run_command=lambda *args, **kwargs: calls.append((args, kwargs)),
        send_summary=lambda **kwargs: True,
    )

    assert result.excel_path is None
    assert len(result.keywords) == 2
    assert calls == []


def test_run_auto_demand_report_reads_exports_and_writes_excel(tmp_path: Path):
    export_root = tmp_path / "exports"
    export_file = export_root / "xhs" / "jsonl" / "search_comments.jsonl"
    export_file.parent.mkdir(parents=True)
    export_file.write_text(
        json.dumps(
            {
                "platform": "xhs",
                "comment": "预算有限，求推荐一个适合新手用的AI工具？",
                "note_url": "https://example.com/note/1",
            },
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )

    commands = []
    notifications = []

    def fake_run(cmd, **kwargs):
        commands.append(cmd)
        return subprocess.CompletedProcess(cmd, 0, stdout="ok", stderr="")

    result = run_auto_demand_report(
        platforms=["xhs"],
        keyword_count=1,
        max_notes_count=5,
        output_dir=tmp_path / "reports",
        export_root=export_root,
        dry_run=False,
        run_command=fake_run,
        send_summary=lambda **kwargs: notifications.append(kwargs) or True,
    )

    assert result.excel_path is not None
    assert result.excel_path.exists()
    assert result.stats.total == 1
    assert result.stats.comment_count == 1
    assert commands
    assert notifications
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
uv run pytest tests/test_auto_demand_runner.py -q
```

Expected: FAIL because runner does not exist.

- [ ] **Step 3: Implement runner**

Create `integrations/demand_report/runner.py`:

```python
# -*- coding: utf-8 -*-

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Callable, Iterable

from integrations.feishu_webhook import send_demand_report_summary
from scripts.sync_to_feishu import read_input_records

from .excel_writer import write_demand_report
from .extractor import extract_demand_item
from .keywords import generate_keyword_plans
from .models import DemandItem, DemandReportStats, DemandRunResult
from .state import DEFAULT_DEMAND_STATE_PATH, load_hashes, save_hashes


PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent


def run_auto_demand_report(
    platforms: list[str],
    keyword_count: int,
    max_notes_count: int,
    output_dir: Path = Path("output") / "demand_reports",
    export_root: Path = Path("data"),
    state_path: Path = DEFAULT_DEMAND_STATE_PATH,
    dry_run: bool = False,
    interval_label: str = "手动运行",
    run_command: Callable[..., subprocess.CompletedProcess] = subprocess.run,
    send_summary: Callable[..., bool] = send_demand_report_summary,
) -> DemandRunResult:
    keyword_plans = generate_keyword_plans(count=keyword_count)
    if dry_run:
        return DemandRunResult(
            excel_path=None,
            stats=DemandReportStats(),
            keywords=keyword_plans,
            export_files=[],
            errors=[],
        )

    errors: list[str] = []
    failed_tasks = 0
    for platform in platforms:
        for plan in keyword_plans:
            cmd = build_crawler_command(platform, plan.keyword, max_notes_count)
            result = run_command(
                cmd,
                cwd=str(PROJECT_ROOT),
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=3600,
            )
            if result.returncode != 0:
                failed_tasks += 1
                errors.append(f"{platform} {plan.keyword}: crawler exited {result.returncode}")

    export_files = list(find_export_files(export_root, platforms))
    hashes = load_hashes(state_path)
    items: list[DemandItem] = []
    skipped = 0
    duplicates = 0
    for export_file in export_files:
        input_format = infer_format(export_file)
        for record in read_input_records(export_file, input_format):
            for plan in keyword_plans:
                item = extract_demand_item(record, plan)
                if item is None:
                    skipped += 1
                    continue
                if item.content_hash in hashes:
                    duplicates += 1
                    continue
                hashes.add(item.content_hash)
                items.append(item)
                break

    excel_path = write_demand_report(items, output_dir=output_dir) if items else None
    save_hashes(hashes, state_path)
    stats = DemandReportStats(
        total=len(items),
        comment_count=sum(1 for item in items if item.content_type == "评论"),
        body_count=sum(1 for item in items if item.content_type == "正文"),
        skipped=skipped,
        duplicates=duplicates,
        failed_tasks=failed_tasks,
    )
    send_summary(
        interval_label=interval_label,
        platforms=platforms,
        keywords=[plan.keyword for plan in keyword_plans],
        stats={
            "total": stats.total,
            "comment_count": stats.comment_count,
            "body_count": stats.body_count,
            "duplicates": stats.duplicates,
            "failed_tasks": stats.failed_tasks,
        },
        excel_path=str(excel_path) if excel_path else "",
    )
    return DemandRunResult(
        excel_path=excel_path,
        stats=stats,
        keywords=keyword_plans,
        export_files=export_files,
        errors=errors,
    )


def build_crawler_command(platform: str, keyword: str, max_notes_count: int) -> list[str]:
    return [
        "uv",
        "run",
        "python",
        "main.py",
        "--platform",
        platform,
        "--type",
        "search",
        "--keywords",
        keyword,
        "--save_data_option",
        "jsonl",
        "--crawler_max_notes_count",
        str(max_notes_count),
    ]


def find_export_files(export_root: Path, platforms: Iterable[str]) -> Iterable[Path]:
    if not export_root.exists():
        return []
    allowed = set(platforms)
    files: list[Path] = []
    for path in export_root.rglob("*"):
        if not path.is_file() or path.suffix.lower() not in {".jsonl", ".csv", ".sqlite", ".db"}:
            continue
        rel_parts = set(path.relative_to(export_root).parts)
        if allowed and not rel_parts.intersection(allowed):
            continue
        files.append(path)
    return sorted(files)


def infer_format(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix == ".jsonl":
        return "jsonl"
    if suffix == ".csv":
        return "csv"
    if suffix in {".sqlite", ".db"}:
        return "sqlite"
    raise ValueError(f"Unsupported export format: {path}")
```

Create `scripts/auto_demand_report.py`:

```python
# -*- coding: utf-8 -*-

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from integrations.demand_report.runner import run_auto_demand_report


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate an automated demand Excel report")
    parser.add_argument("--platforms", default="xhs,wb,zhihu", help="Comma-separated platform ids")
    parser.add_argument("--keyword-count", type=int, default=5)
    parser.add_argument("--max-notes-count", type=int, default=20)
    parser.add_argument("--output-dir", type=Path, default=Path("output") / "demand_reports")
    parser.add_argument("--export-root", type=Path, default=Path("data"))
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--interval-label", default="手动运行")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    result = run_auto_demand_report(
        platforms=[item.strip() for item in args.platforms.split(",") if item.strip()],
        keyword_count=args.keyword_count,
        max_notes_count=args.max_notes_count,
        output_dir=args.output_dir,
        export_root=args.export_root,
        dry_run=args.dry_run,
        interval_label=args.interval_label,
    )
    print(
        json.dumps(
            {
                "excel_path": str(result.excel_path) if result.excel_path else "",
                "stats": result.stats_dict(),
                "keywords": [plan.keyword for plan in result.keywords],
                "errors": result.errors,
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run runner tests**

Run:

```bash
uv run pytest tests/test_auto_demand_runner.py -q
```

Expected: PASS.

- [ ] **Step 5: Smoke test dry-run CLI**

Run:

```bash
uv run python scripts/auto_demand_report.py --platforms xhs --keyword-count 2 --dry-run
```

Expected: JSON output with two generated keywords and empty `excel_path`.

- [ ] **Step 6: Commit**

```bash
git add integrations/demand_report/runner.py scripts/auto_demand_report.py tests/test_auto_demand_runner.py
git commit -m "feat: add auto demand report runner"
```

---

### Task 6: Scheduler and API Manager

**Files:**
- Create: `scripts/auto_demand_scheduler.py`
- Create: `api/schemas/auto_demand.py`
- Create: `api/services/auto_demand_manager.py`
- Create: `api/routers/auto_demand.py`
- Modify: `api/routers/__init__.py`
- Modify: `api/main.py`
- Test: `tests/test_auto_demand_api.py`

- [ ] **Step 1: Write failing API tests**

Create `tests/test_auto_demand_api.py`:

```python
from fastapi.testclient import TestClient

from api.main import app


def test_auto_demand_status_endpoint():
    client = TestClient(app)

    response = client.get("/api/auto-demand/status")

    assert response.status_code == 200
    data = response.json()
    assert "running" in data
    assert "config" in data
    assert data["config"]["interval"] in ["manual", "3h", "6h", "12h", "1d", "1w"]


def test_auto_demand_config_update():
    client = TestClient(app)

    response = client.post(
        "/api/auto-demand/config",
        json={"enabled": True, "interval": "6h", "platforms": ["xhs"], "keyword_count": 2, "max_notes_count": 5},
    )

    assert response.status_code == 200
    assert response.json()["config"]["interval"] == "6h"


def test_auto_demand_rejects_invalid_interval():
    client = TestClient(app)

    response = client.post(
        "/api/auto-demand/config",
        json={"enabled": True, "interval": "2h", "platforms": ["xhs"], "keyword_count": 2, "max_notes_count": 5},
    )

    assert response.status_code == 422
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
uv run pytest tests/test_auto_demand_api.py -q
```

Expected: FAIL because router does not exist.

- [ ] **Step 3: Implement schemas**

Create `api/schemas/auto_demand.py`:

```python
# -*- coding: utf-8 -*-

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


AutoDemandInterval = Literal["manual", "3h", "6h", "12h", "1d", "1w"]


class AutoDemandConfig(BaseModel):
    enabled: bool = False
    interval: AutoDemandInterval = "manual"
    platforms: list[str] = Field(default_factory=lambda: ["xhs", "wb", "zhihu"])
    keyword_count: int = Field(default=5, ge=1, le=100)
    max_notes_count: int = Field(default=20, ge=1, le=1000)


class AutoDemandRunRequest(BaseModel):
    dry_run: bool = False
```

- [ ] **Step 4: Implement manager and router**

Create `api/services/auto_demand_manager.py`:

```python
# -*- coding: utf-8 -*-

from __future__ import annotations

import json
import subprocess
import threading
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

from api.schemas.auto_demand import AutoDemandConfig


PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
CONFIG_PATH = PROJECT_ROOT / ".sync_state" / "auto_demand_config.json"


class AutoDemandManager:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._logs: List[Dict[str, Any]] = []
        self._log_id = 0
        self.process: subprocess.Popen[str] | None = None
        self.config = self._load_config()

    def _load_config(self) -> AutoDemandConfig:
        if not CONFIG_PATH.exists():
            return AutoDemandConfig()
        return AutoDemandConfig.model_validate_json(CONFIG_PATH.read_text(encoding="utf-8"))

    def save_config(self, config: AutoDemandConfig) -> AutoDemandConfig:
        CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
        CONFIG_PATH.write_text(config.model_dump_json(indent=2), encoding="utf-8")
        self.config = config
        self._append_log("info", f"自动需求采集配置已更新：{config.interval}")
        return config

    def start_once(self, dry_run: bool = False) -> bool:
        with self._lock:
            if self.process and self.process.poll() is None:
                self._append_log("warning", "上一轮自动需求采集仍在运行，本次跳过。")
                return False
            cmd = [
                "uv",
                "run",
                "python",
                "scripts/auto_demand_report.py",
                "--platforms",
                ",".join(self.config.platforms),
                "--keyword-count",
                str(self.config.keyword_count),
                "--max-notes-count",
                str(self.config.max_notes_count),
                "--interval-label",
                _interval_label(self.config.interval),
            ]
            if dry_run:
                cmd.append("--dry-run")
            self._append_log("info", "启动自动需求采集: " + " ".join(cmd))
            self.process = subprocess.Popen(
                cmd,
                cwd=str(PROJECT_ROOT),
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
                env=None,
            )
            threading.Thread(target=self._read_output, daemon=True).start()
            return True

    def get_status(self) -> Dict[str, Any]:
        running = self.process is not None and self.process.poll() is None
        return {"running": running, "config": self.config.model_dump(), "logs": self._logs[-200:]}

    def _read_output(self) -> None:
        process = self.process
        if not process or not process.stdout:
            return
        for line in process.stdout:
            text = line.strip()
            if text:
                self._append_log("info", text)
        returncode = process.wait()
        self._append_log("success" if returncode == 0 else "error", f"自动需求采集退出，返回码: {returncode}")

    def _append_log(self, level: str, message: str) -> None:
        self._log_id += 1
        self._logs.append(
            {"id": self._log_id, "timestamp": datetime.now().strftime("%H:%M:%S"), "level": level, "message": message}
        )
        if len(self._logs) > 500:
            self._logs = self._logs[-500:]


def _interval_label(interval: str) -> str:
    return {"manual": "手动运行", "3h": "每 3 小时", "6h": "每 6 小时", "12h": "每 12 小时", "1d": "每天", "1w": "每周"}[interval]


auto_demand_manager = AutoDemandManager()
```

Create `api/routers/auto_demand.py`:

```python
# -*- coding: utf-8 -*-

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from api.schemas.auto_demand import AutoDemandConfig, AutoDemandRunRequest
from api.services.auto_demand_manager import auto_demand_manager


router = APIRouter(prefix="/auto-demand", tags=["auto-demand"])


@router.get("/status")
async def get_status():
    return auto_demand_manager.get_status()


@router.post("/config")
async def save_config(config: AutoDemandConfig):
    return {"status": "ok", "config": auto_demand_manager.save_config(config).model_dump()}


@router.post("/run-once")
async def run_once(request: AutoDemandRunRequest):
    started = auto_demand_manager.start_once(dry_run=request.dry_run)
    if not started:
        raise HTTPException(status_code=400, detail="Auto demand report is already running")
    return {"status": "ok", "runner": auto_demand_manager.get_status()}
```

Modify `api/routers/__init__.py`:

```python
from .auto_demand import router as auto_demand_router
```

Add `auto_demand_router` to `__all__` and import list.

Modify `api/main.py`:

```python
from .routers import auto_demand_router, crawler_router, data_router, feishu_router, feishu_webhook_router, local_tasks_router, websocket_router

app.include_router(auto_demand_router, prefix="/api")
```

- [ ] **Step 5: Implement scheduler CLI**

Create `scripts/auto_demand_scheduler.py`:

```python
# -*- coding: utf-8 -*-

from __future__ import annotations

import argparse
import subprocess
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent

INTERVAL_SECONDS = {
    "3h": 3 * 60 * 60,
    "6h": 6 * 60 * 60,
    "12h": 12 * 60 * 60,
    "1d": 24 * 60 * 60,
    "1w": 7 * 24 * 60 * 60,
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run auto demand report on a schedule")
    parser.add_argument("--interval", choices=INTERVAL_SECONDS.keys(), required=True)
    parser.add_argument("--platforms", default="xhs,wb,zhihu")
    parser.add_argument("--keyword-count", type=int, default=5)
    parser.add_argument("--max-notes-count", type=int, default=20)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    while True:
        cmd = [
            "uv",
            "run",
            "python",
            "scripts/auto_demand_report.py",
            "--platforms",
            args.platforms,
            "--keyword-count",
            str(args.keyword_count),
            "--max-notes-count",
            str(args.max_notes_count),
            "--interval-label",
            args.interval,
        ]
        subprocess.run(cmd, cwd=str(PROJECT_ROOT), check=False)
        time.sleep(INTERVAL_SECONDS[args.interval])


if __name__ == "__main__":
    main()
```

- [ ] **Step 6: Run API tests**

Run:

```bash
uv run pytest tests/test_auto_demand_api.py -q
```

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add scripts/auto_demand_scheduler.py api/schemas/auto_demand.py api/services/auto_demand_manager.py api/routers/auto_demand.py api/routers/__init__.py api/main.py tests/test_auto_demand_api.py
git commit -m "feat: add auto demand api controls"
```

---

### Task 7: WebUI Panel

**Files:**
- Modify: `api/webui/index.html`
- Modify: `api/webui/dashboard.css`
- Modify: `api/webui/dashboard.js`

- [ ] **Step 1: Add WebUI structure**

Modify `api/webui/index.html` by adding this section near the existing crawler/data panels:

```html
<section class="panel auto-demand-panel" id="autoDemandSection">
  <div class="panel-head">
    <h2>自动需求采集</h2>
    <div class="actions">
      <span class="status-pill" id="autoDemandStatus">状态：读取中</span>
      <button id="autoDemandDryRunBtn">Dry-Run</button>
      <button id="autoDemandRunBtn" class="primary">手动运行一次</button>
    </div>
  </div>
  <form class="control-form" id="autoDemandForm">
    <label>采集周期
      <select name="interval">
        <option value="manual">手动运行</option>
        <option value="3h">每 3 小时</option>
        <option value="6h">每 6 小时</option>
        <option value="12h">每 12 小时</option>
        <option value="1d">每天</option>
        <option value="1w">每周</option>
      </select>
    </label>
    <label>平台
      <input name="platforms" value="xhs,wb,zhihu" />
    </label>
    <label>每轮关键词数
      <input name="keyword_count" type="number" min="1" max="100" value="5" />
    </label>
    <label>单关键词最大内容数
      <input name="max_notes_count" type="number" min="1" max="1000" value="20" />
    </label>
    <label class="checkline"><input name="enabled" type="checkbox" /> 启用定时自动采集</label>
  </form>
  <div class="actions inline-actions">
    <button id="autoDemandSaveBtn">保存配置</button>
    <button id="autoDemandRefreshBtn">刷新状态</button>
  </div>
  <pre class="command-box preview-box" id="autoDemandPreview">自动需求采集会生成 Excel，并通过飞书机器人发送本机路径。</pre>
</section>
```

- [ ] **Step 2: Add WebUI JavaScript**

Modify `api/webui/dashboard.js` by adding functions:

```javascript
async function loadAutoDemandStatus() {
  try {
    const data = await api("/api/auto-demand/status");
    const config = data.config || {};
    $("autoDemandStatus").textContent = data.running ? "状态：运行中" : "状态：空闲";
    const form = $("autoDemandForm");
    if (form) {
      setFormValue(form, "interval", config.interval || "manual");
      form.elements.platforms.value = (config.platforms || ["xhs", "wb", "zhihu"]).join(",");
      form.elements.keyword_count.value = config.keyword_count || 5;
      form.elements.max_notes_count.value = config.max_notes_count || 20;
      form.elements.enabled.checked = Boolean(config.enabled);
    }
    renderAutoDemandPreview(config);
  } catch (error) {
    appendLocalLog("error", `读取自动需求采集状态失败：${error.message}`);
  }
}

function readAutoDemandConfig() {
  const form = $("autoDemandForm");
  return {
    enabled: form.elements.enabled.checked,
    interval: form.elements.interval.value,
    platforms: String(form.elements.platforms.value || "")
      .split(",")
      .map((item) => item.trim())
      .filter(Boolean),
    keyword_count: Number(form.elements.keyword_count.value || 5),
    max_notes_count: Number(form.elements.max_notes_count.value || 20),
  };
}

function renderAutoDemandPreview(config = readAutoDemandConfig()) {
  $("autoDemandPreview").textContent = JSON.stringify(
    {
      interval: config.interval || "manual",
      platforms: config.platforms || ["xhs", "wb", "zhihu"],
      keyword_count: config.keyword_count || 5,
      max_notes_count: config.max_notes_count || 20,
      output: "output/demand_reports/*.xlsx",
      notification: "Feishu webhook summary + local file path",
    },
    null,
    2
  );
}

async function saveAutoDemandConfig() {
  const config = readAutoDemandConfig();
  try {
    await api("/api/auto-demand/config", { method: "POST", body: JSON.stringify(config) });
    appendLocalLog("success", "自动需求采集配置已保存。");
    await loadAutoDemandStatus();
  } catch (error) {
    appendLocalLog("error", `保存自动需求采集配置失败：${error.message}`);
  }
}

async function runAutoDemandOnce(dryRun) {
  try {
    await api("/api/auto-demand/run-once", {
      method: "POST",
      body: JSON.stringify({ dry_run: dryRun }),
    });
    appendLocalLog("info", `${dryRun ? "Dry-Run" : "手动运行"}自动需求采集已启动。`);
    await loadAutoDemandStatus();
  } catch (error) {
    appendLocalLog("error", `启动自动需求采集失败：${error.message}`);
  }
}
```

Register events in the existing initializer:

```javascript
$("autoDemandSaveBtn")?.addEventListener("click", saveAutoDemandConfig);
$("autoDemandRefreshBtn")?.addEventListener("click", loadAutoDemandStatus);
$("autoDemandDryRunBtn")?.addEventListener("click", () => runAutoDemandOnce(true));
$("autoDemandRunBtn")?.addEventListener("click", () => runAutoDemandOnce(false));
$("autoDemandForm")?.addEventListener("input", () => renderAutoDemandPreview());
loadAutoDemandStatus();
```

- [ ] **Step 3: Add CSS**

Modify `api/webui/dashboard.css`:

```css
.auto-demand-panel {
  margin-top: 16px;
}

.inline-actions {
  justify-content: flex-start;
  margin-top: 12px;
}
```

- [ ] **Step 4: Browser verify**

Start server:

```bash
uv run python -m api.main
```

Open:

```text
http://127.0.0.1:8080/
```

Expected:

- Page contains `自动需求采集`.
- Interval selector has `3h`, `6h`, `12h`, `1d`, `1w`.
- `Dry-Run` calls `/api/auto-demand/run-once` with `{dry_run: true}`.
- No horizontal overflow at desktop width.

- [ ] **Step 5: Commit**

```bash
git add api/webui/index.html api/webui/dashboard.css api/webui/dashboard.js
git commit -m "feat: add auto demand controls to webui"
```

---

### Task 8: Sensitive Logging Safety

**Files:**
- Modify: `api/services/crawler_manager.py`
- Test: `tests/test_crawler_manager_security.py`

- [ ] **Step 1: Write failing redaction test**

Create `tests/test_crawler_manager_security.py`:

```python
from api.services.crawler_manager import safe_command_text


def test_safe_command_text_redacts_cookie_value():
    command = ["uv", "run", "python", "main.py", "--cookies", "secret-cookie-value", "--platform", "xhs"]

    text = safe_command_text(command)

    assert "secret-cookie-value" not in text
    assert "--cookies <REDACTED>" in text
    assert "--platform xhs" in text
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
uv run pytest tests/test_crawler_manager_security.py -q
```

Expected: FAIL because `safe_command_text` does not exist.

- [ ] **Step 3: Add redaction helper and use it**

Modify `api/services/crawler_manager.py`:

```python
def safe_command_text(cmd: list[str]) -> str:
    safe_parts: list[str] = []
    skip_next = False
    for part in cmd:
        if skip_next:
            safe_parts.append("<REDACTED>")
            skip_next = False
            continue
        safe_parts.append(part)
        if part in {"--cookies", "--cookie", "--token"}:
            skip_next = True
    return " ".join(safe_parts)
```

Replace:

```python
entry = self._create_log_entry(f"Starting crawler: {' '.join(cmd)}", "info")
```

with:

```python
entry = self._create_log_entry(f"Starting crawler: {safe_command_text(cmd)}", "info")
```

- [ ] **Step 4: Run security test**

Run:

```bash
uv run pytest tests/test_crawler_manager_security.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add api/services/crawler_manager.py tests/test_crawler_manager_security.py
git commit -m "fix: redact sensitive crawler command values"
```

---

### Task 9: Final Verification

**Files:**
- No new files required.

- [ ] **Step 1: Run focused demand tests**

Run:

```bash
uv run pytest tests/test_demand_keywords.py tests/test_demand_extractor.py tests/test_demand_excel_writer.py tests/test_auto_demand_runner.py tests/test_auto_demand_api.py tests/test_feishu_webhook_report.py tests/test_crawler_manager_security.py -q
```

Expected: all selected tests PASS.

- [ ] **Step 2: Run full test suite**

Run:

```bash
uv run pytest -q
```

Expected: full suite PASS or existing environment-dependent tests SKIP when services are unavailable.

- [ ] **Step 3: Compile changed Python packages**

Run:

```bash
uv run python -m compileall integrations scripts api
```

Expected: no syntax errors.

- [ ] **Step 4: Dry-run auto demand CLI**

Run:

```bash
uv run python scripts/auto_demand_report.py --platforms xhs --keyword-count 2 --max-notes-count 3 --dry-run
```

Expected:

- JSON output includes generated keywords.
- No crawler process starts.
- No Feishu webhook request is sent.

- [ ] **Step 5: Generate Excel from fixture export without real Feishu**

Create a local fixture under a temp directory and run runner through pytest or direct Python with `send_summary=lambda **kwargs: True`. Expected:

- `.xlsx` file exists.
- Excel has the required 13 columns.
- Stats include `comment_count >= 1`.

- [ ] **Step 6: WebUI smoke check**

Run:

```bash
uv run python -m api.main
```

Open `http://127.0.0.1:8080/`.

Expected:

- Auto demand panel visible.
- Config save returns HTTP 200.
- Dry-run run-once returns HTTP 200.
- Logs do not contain webhook URL, token, or Cookie values.

- [ ] **Step 7: Git hygiene check**

Run:

```bash
git status --short
```

Expected:

- Only intended code/test/docs files are modified or staged.
- `.env`, screenshots, `.sync_state`, and generated Excel files are not staged.

- [ ] **Step 8: Commit final verification docs if needed**

If a short verification note is added, commit it separately:

```bash
git add docs/superpowers/plans/2026-06-27-auto-demand-excel-feishu.md
git commit -m "docs: add auto demand implementation plan"
```

## Plan Self-Review

- Spec coverage:
  - Automatic keyword generation: Task 1.
  - Existing MediaCrawler CLI usage without core changes: Task 5.
  - Read exported JSONL/CSV/SQLite: Task 5 reuses `read_input_records`.
  - Comment-first demand extraction and body fallback: Task 2.
  - Hash dedup state: Task 2 and Task 5.
  - Excel `.xlsx` output: Task 3.
  - Feishu webhook summary with local path: Task 4.
  - Manual/interval controls: Task 6 and Task 7.
  - Non-sensitive logging: Task 8.
  - Full verification: Task 9.
- Placeholder scan:
  - No unfinished placeholder markers are present.
- Type consistency:
  - `KeywordPlan`, `DemandItem`, `DemandReportStats`, and `DemandRunResult` are introduced in Task 1 and reused consistently in later tasks.
  - API interval values are consistently `manual`, `3h`, `6h`, `12h`, `1d`, and `1w`.
