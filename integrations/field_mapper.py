# -*- coding: utf-8 -*-

from __future__ import annotations

import hashlib
import json
import re
from typing import Any, Dict, Optional


FEISHU_FIELD_NAMES = [
    "需求标题",
    "来源平台",
    "关键词",
    "原文内容",
    "来源链接",
    "发布时间",
    "采集时间",
    "内容哈希",
    "需求分类",
    "需求类型",
    "优先级",
    "状态",
    "备注",
]


def map_record_to_feishu_fields(record: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Map one MediaCrawler export row to Feishu Bitable fields.

    Returns None when the row does not contain enough public content to sync.
    """

    raw_text = _first_text(
        record,
        [
            "comment",
            "content",
            "content_text",
            "desc",
            "description",
            "text",
            "full_text",
            "正文",
            "评论内容",
        ],
    )
    if not raw_text:
        raw_text = _first_text(record, ["title", "标题"])

    raw_text = _clean_text(raw_text)
    if _count_chinese_chars(raw_text) < 10:
        return None

    source_url = _first_text(
        record,
        [
            "source_url",
            "url",
            "note_url",
            "share_url",
            "content_url",
            "video_url",
            "原文链接",
            "来源链接",
        ],
    )
    platform = _infer_platform(record, source_url)
    title = _first_text(record, ["title", "标题"]) or _make_title(raw_text)
    keyword = _first_text(
        record,
        ["keyword", "keywords", "source_keyword", "search_keyword", "关键词"],
    )
    publish_time = _first_value(
        record,
        ["publish_time", "create_time", "created_time", "time", "发布时间"],
    )
    crawl_time = _first_value(
        record,
        ["crawl_time", "add_ts", "last_modify_ts", "采集时间"],
    )
    content_hash = build_content_hash(platform, source_url, raw_text)

    return {
        "需求标题": _make_title(title),
        "来源平台": platform,
        "关键词": keyword,
        "原文内容": raw_text,
        "来源链接": source_url,
        "发布时间": publish_time,
        "采集时间": crawl_time,
        "内容哈希": content_hash,
        "需求分类": "",
        "需求类型": "未分类",
        "优先级": "中",
        "状态": "待处理",
        "备注": "",
    }


def build_content_hash(platform: str, source_url: str, raw_text: str) -> str:
    payload = f"{platform}{source_url}{raw_text}".encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


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


def _make_title(value: str, max_len: int = 80) -> str:
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

    if record.get("aweme_id"):
        return "dy"
    if record.get("photo_id"):
        return "ks"
    if record.get("bvid") or record.get("aid"):
        return "bili"
    if record.get("mblogid") or record.get("mid"):
        return "wb"
    if record.get("tieba_id") or record.get("thread_id"):
        return "tieba"
    if record.get("url_token") or record.get("content_type"):
        return "zhihu"
    if record.get("note_id"):
        return "xhs"

    return "unknown"
