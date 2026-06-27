# -*- coding: utf-8 -*-

"""
Feishu Group Chat Webhook Notification
Alternative to Bitable API when personal version restricts write access.

Usage:
  1. Create a Feishu group chat
  2. Add a "群机器人" -> "自定义机器人" webhook
  3. Set FEISHU_WEBHOOK_URL environment variable or configure in Dashboard
"""

from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import httpx


def get_webhook_url() -> Optional[str]:
    """Get the configured Feishu webhook URL"""
    url = os.getenv("FEISHU_WEBHOOK_URL", "").strip()
    return url if url and url.startswith("https://") else None


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
    if not webhook_url:
        webhook_url = get_webhook_url()
    if not webhook_url:
        return False

    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    status_emoji = "OK" if stats.get("success", 0) > 0 else "NO" if stats.get("failed", 0) > 0 else "II"

    fields_lines = [
        "**采集时间：** " + now,
        "**平台：** " + platform,
        "**采集类型：** " + crawler_type,
    ]
    if keywords:
        fields_lines.append("**关键词：** " + keywords)

    fields_lines.append("")
    fields_lines.append("**统计：**")
    fields_lines.append("- 成功：" + str(stats.get('success', 0)) + " 条")
    fields_lines.append("- 跳过：" + str(stats.get('skipped', 0)) + " 条")
    fields_lines.append("- 失败：" + str(stats.get('failed', 0)) + " 条")

    if file_paths:
        fields_lines.append("")
        fields_lines.append("**输出文件：**")
        for fp in file_paths[:5]:
            fields_lines.append("- " + fp)
        if len(file_paths) > 5:
            fields_lines.append("- ... 共 " + str(len(file_paths)) + " 个文件")
    if content_items:
        fields_lines.append("")
        fields_lines.append("**采集内容：**")
        fields_lines.append("")
        for i, item in enumerate(content_items[:5], 1):
            title = item.get("title", "") or ""
            desc = item.get("desc", "") or ""
            nickname = item.get("nickname", "") or ""
            likes = item.get("likes", "0") or "0"
            url = item.get("url", "") or ""
            if not title and not desc:
                continue
            line = chr(9472) + chr(9472) + " " + str(i) + ". " + (title[:60] if title else desc[:60])
            fields_lines.append(line)
            if nickname:
                fields_lines.append("   作者: " + nickname + " | 赞: " + str(likes))
            if url:
                fields_lines.append("   链接: " + url)
            fields_lines.append("")
    if content_items:
        fields_lines.append("")
        fields_lines.append("**采集内容：**")
        fields_lines.append("")
        for i, item in enumerate(content_items[:5], 1):
            title = item.get("title", "") or ""
            desc = item.get("desc", "") or ""
            nickname = item.get("nickname", "") or ""
            likes = item.get("likes", "0") or "0"
            url = item.get("url", "") or ""
            if not title and not desc:
                continue
            fields_lines.append("── " + str(i) + ". " + (title[:50] if title else desc[:50]))
            if nickname:
                fields_lines.append("   作者: " + nickname + "  赞: " + str(likes))
            if url:
                fields_lines.append("   " + url)
            fields_lines.append("")

    payload = {
        "msg_type": "interactive",
        "card": {
            "header": {
                "title": {"tag": "plain_text", "content": status_emoji + " 采集任务完成"},
                "template": "green" if stats.get("success", 0) > 0 else "red",
            },
            "elements": [
                {"tag": "markdown", "content": "\n".join(fields_lines)},
                {"tag": "hr"},
                {
                    "tag": "note",
                    "elements": [{"tag": "plain_text", "content": "MediaCrawler 自动通知"}],
                },
            ],
        },
    }

    try:
        with httpx.Client(timeout=15.0) as client:
            response = client.post(webhook_url, json=payload)
            response.raise_for_status()
            return True
    except Exception as exc:
        print("[FeishuWebhook] Failed to send notification: " + str(exc))
        return False


def send_simple_message(
    title: str,
    content: str,
    template: str = "blue",
    webhook_url: Optional[str] = None,
) -> bool:
    """Send a simple card message to Feishu group chat"""
    if not webhook_url:
        webhook_url = get_webhook_url()
    if not webhook_url:
        return False

    payload = {
        "msg_type": "interactive",
        "card": {
            "header": {
                "title": {"tag": "plain_text", "content": title},
                "template": template,
            },
            "elements": [
                {"tag": "markdown", "content": content},
                {"tag": "hr"},
                {"tag": "note", "elements": [{"tag": "plain_text", "content": "MediaCrawler 通知"}]},
            ],
        },
    }

    try:
        with httpx.Client(timeout=15.0) as client:
            response = client.post(webhook_url, json=payload)
            response.raise_for_status()
            return True
    except Exception as exc:
        print("[FeishuWebhook] Failed to send message: " + str(exc))
        return False



def send_requirements_doc(
    platform: str = "",
    keywords: str = "",
    requirements=None,
    webhook_url=None,
) -> bool:
    """Send crawled data as formatted requirements document"""
    if webhook_url is None:
        webhook_url = get_webhook_url()
    if not webhook_url or not requirements:
        return False

    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    pname = platform
    for k, v in {"xhs": "小红书", "dy": "抖音", "ks": "快手", "bili": "Bilibili", "wb": "微博", "tieba": "贴吧", "zhihu": "知乎"}.items():
        if platform == k:
            pname = v
            break

    lines = []
    lines.append("**采集时间：** " + now)
    lines.append("**平台：** " + pname)
    if keywords:
        lines.append("**关键词：** " + keywords)
    lines.append("**共获取** " + str(len(requirements)) + " **条需求**")
    lines.append("")
    lines.append("---")
    lines.append("")

    for i, req in enumerate(requirements[:8], 1):
        title = req.get("需求标题", req.get("需求标题", "")) or "未命名"
        ctext = req.get("原文内容", "") or ""
        source = req.get("来源平台", "") or ""
        link = req.get("来源链接", "") or ""
        rtype = req.get("需求类型", "未分类") or "未分类"
        priority = req.get("优先级", "中") or "中"

        lines.append("**" + str(i) + ". " + title[:50] + "**")
        if ctext:
            lines.append("> " + ctext[:120].replace(chr(10), " "))
        lines.append("- 需求类型：" + rtype + " | 优先级：" + priority)
        if source:
            lines.append("- 来源：" + source)
        if link:
            lines.append("- " + link)
        lines.append("")

    payload = {
        "msg_type": "interactive",
        "card": {
            "header": {"title": {"tag": "plain_text", "content": "采集需求报告"}, "template": "blue"},
            "elements": [
                {"tag": "markdown", "content": nl.join(lines)},
                {"tag": "hr"},
                {"tag": "note", "elements": [{"tag": "plain_text", "content": "MediaCrawler 自动需求分析"}]},
            ],
        },
    }

    try:
        import httpx
        with httpx.Client(timeout=15.0) as client:
            response = client.post(webhook_url, json=payload)
            response.raise_for_status()
            return True
    except Exception as exc:
        print("[FeishuWebhook] Failed: " + str(exc))
        return False



def send_analysis_report(
    aggregation: list,
    solutions_data: list = None,
    keyword: str = "",
    platform: str = "",
    total: int = 0,
    webhook_url: str = None,
) -> bool:
    """Send pain point analysis + AI solutions report to Feishu group chat"""
    if not webhook_url:
        webhook_url = get_webhook_url()
    if not webhook_url:
        return False

    # Emoji map for top categories
    emojis = ["\U0001f534", "\U0001f7e0", "\U0001f7e1", "\U0001f7e2", "\U000026aa", "\U0001f7e3", "\U0001f7e4"]

    lines = []
    lines.append("**\U0001f4ca 痛点分析报告**")
    lines.append("")
    if keyword:
        lines.append("**搜索关键词：** " + keyword)
    if platform:
        lines.append("**采集平台：** " + platform)
    lines.append("**有效数据：** " + str(total) + " 条")
    lines.append("")

    # Pain point aggregation
    lines.append("**\U0001f4cc 痛点频次排行**")
    lines.append("")
    for i, item in enumerate(aggregation):
        emoji = emojis[i] if i < len(emojis) else "\U000026ab"
        pct = round(item["count"] / max(total, 1) * 100, 1) if total > 0 else 0
        bar = "\U00002588" * max(1, int(pct / 10))
        lines.append(emoji + " **" + item["category"] + "**  " + str(item["count"]) + "次  (" + str(pct) + "%)")
    lines.append("")

    # AI Solutions
    if solutions_data:
        lines.append("**\U0001f916 AI 解决方案建议**")
        lines.append("")
        for sol_item in solutions_data[:3]:  # Top 3
            cat = sol_item["category"]
            count = sol_item["count"]
            solutions = sol_item.get("solutions", [])
            lines.append("**\U0001f4a1 " + cat + "**（" + str(count) + "次）")
            for sol in solutions[:2]:  # Top 2 solutions per category
                lines.append("- " + sol.get("solution_name", "") + " [" + sol.get("solution_type", "") + " / " + sol.get("cost", "") + "成本]")
            lines.append("")

    lines.append("\U0001f4dd 详情可查看飞书 Bitable")

    payload = {
        "msg_type": "interactive",
        "card": {
            "header": {
                "title": {"tag": "plain_text", "content": "\U0001f4ca 痛点分析报告"},
                "template": "blue",
            },
            "elements": [
                {"tag": "markdown", "content": "\n".join(lines)},
                {"tag": "hr"},
                {"tag": "note", "elements": [{"tag": "plain_text", "content": "MediaCrawler 痛点分析 - AI 自动生成"}]},
            ],
        },
    }

    try:
        with httpx.Client(timeout=15.0) as client:
            response = client.post(webhook_url, json=payload)
            response.raise_for_status()
            return True
    except Exception as exc:
        print("[FeishuWebhook] Failed to send analysis report: " + str(exc))
        return False


def test_webhook(webhook_url: str) -> Dict[str, Any]:
    """Test if a webhook URL is valid"""
    payload = {
        "msg_type": "text",
        "content": {"text": "MediaCrawler Webhook 连接测试成功！"},
    }
    try:
        with httpx.Client(timeout=10.0) as client:
            response = client.post(webhook_url, json=payload)
            response.raise_for_status()
            return {"success": True, "message": "Webhook 连接测试成功"}
    except httpx.HTTPStatusError as exc:
        return {"success": False, "message": "HTTP " + str(exc.response.status_code) + ": " + str(exc.response.text[:100])}
    except Exception as exc:
        return {"success": False, "message": type(exc).__name__ + ": " + str(exc)}
