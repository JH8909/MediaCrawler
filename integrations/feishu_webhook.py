# -*- coding: utf-8 -*-

"""
Feishu Group Chat Webhook Notification
Webhook notification helper for Feishu group bot messages.

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
    webhook_url: Optional[str] = None,
) -> bool:
    """Send a concise crawl completion summary to Feishu group chat."""
    if not webhook_url:
        webhook_url = get_webhook_url()
    if not webhook_url:
        return False
    stats = stats or {}

    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    has_data = any(v > 0 for v in stats.values())

    lines = [
        "**采集时间：** " + now,
        "**平台：** " + platform,
        "**采集类型：** " + crawler_type,
    ]
    if keywords:
        lines.append("**关键词：** " + keywords)
    lines.append("")
    lines.append("**统计：**")
    for key, val in stats.items():
        if val:
            lines.append(f"- {key}：{val} 条")

    payload = {
        "msg_type": "interactive",
        "card": {
            "header": {
                "title": {"tag": "plain_text", "content": "✅ 采集完成" if has_data else "⏹ 采集完成"},
                "template": "green" if has_data else "red",
            },
            "elements": [
                {"tag": "markdown", "content": "\n".join(lines)},
                {"tag": "hr"},
                {"tag": "note", "elements": [{"tag": "plain_text", "content": "MediaCrawler 自动通知"}]},
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
    classified_records: list = None,
    webhook_url=None,
) -> bool:
    """Send crawled data as formatted requirements document.

    Accepts both legacy 'requirements' (list of dicts with Chinese keys)
    and 'classified_records' (from needs_analyzer output).
    """
    if webhook_url is None:
        webhook_url = get_webhook_url()
    if not webhook_url:
        return False

    # Use classified_records if requirements not provided
    items = requirements or classified_records or []
    if not items:
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
    lines.append("**共获取** " + str(len(items)) + " **条需求**")
    lines.append("")
    lines.append("---")
    lines.append("")

    for i, item in enumerate(items[:8], 1):
        # Try classified_records format first, then legacy format
        title = (
            item.get("extracted_text", "")[:30]
            or item.get("需求标题", "")
            or "未命名"
        )
        ctext = item.get("extracted_text", "") or item.get("原文内容", "") or ""
        source = item.get("来源平台", "") or ""
        link = item.get("note_url", "") or item.get("来源链接", "") or ""
        cats = item.get("categories", [])
        rtype = (cats[0] if cats else "") or item.get("需求类型", "未分类")
        hs = item.get("hot_score", 0)
        priority = "高" if hs > 5 else "中" if hs > 2 else "低"

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
                {"tag": "markdown", "content": "\n".join(lines)},
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



def send_demand_report(
    aggregation: list,
    solutions_data: list = None,
    keyword: str = "",
    platform: str = "",
    total: int = 0,
    classified_records: list = None,
    category_rules: dict = None,
    webhook_url: str = None,
) -> bool:
    """Send a concise demand discovery summary to Feishu group chat.

    One card with: platform/keyword, top 5 pain points, 1 AI tip, timestamp.
    """
    if not webhook_url:
        webhook_url = get_webhook_url()
    if not webhook_url:
        return False

    emojis = ["🔴", "🟠", "🟡", "🟢", "⚪"]

    lines = []
    lines.append("**📊 需求发现报告**")
    if platform:
        lines.append("**平台：** " + platform + ("  |  **关键词：** " + keyword if keyword else ""))
    lines.append("**数据：** " + str(total) + " 条  |  " + str(len(aggregation)) + " 个分类")
    lines.append("")

    # Top 5 pain points — one line each
    lines.append("**🔥 痛点 Top " + str(min(5, len(aggregation))) + "**")
    for i, item in enumerate(aggregation[:5]):
        emoji = emojis[i] if i < len(emojis) else "⚫"
        cat_name = item["category"]
        count = item["count"]
        hs = item.get("hot_score", 0)
        lines.append(f"{emoji} **{cat_name}** · {count}次" + (f"  ★{hs}" if hs else ""))

    lines.append("")

    # One AI tip
    if solutions_data and solutions_data[0].get("solutions"):
        top_sol = solutions_data[0]
        sols = top_sol.get("solutions", [])
        if sols:
            best = sols[0]
            name = best.get("name", best.get("solution_name", ""))
            ptype = best.get("product_type", best.get("solution_type", ""))
            lines.append(f"💡 **AI方案建议**：{name}" + (f"（{ptype}）" if ptype else ""))

    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    lines.append("")
    lines.append(f"🕐 {now}  · 详情查看控制台")

    payload = {
        "msg_type": "interactive",
        "card": {
            "header": {
                "title": {"tag": "plain_text", "content": "📊 需求发现报告"},
                "template": "blue",
            },
            "elements": [
                {"tag": "markdown", "content": "\n".join(lines)},
                {"tag": "hr"},
                {"tag": "note", "elements": [{"tag": "plain_text", "content": "MediaCrawler 自动需求发现"}]},
            ],
        },
    }

    try:
        with httpx.Client(timeout=15.0) as client:
            response = client.post(webhook_url, json=payload)
            response.raise_for_status()
    except Exception as exc:
        print("[FeishuWebhook] Failed to send demand report: " + str(exc))
        return False

    return True


# Keep the old name as alias for backward compatibility
send_analysis_report = send_demand_report


def send_demand_report_summary(
    platforms: list,
    keyword_plans: list,
    stats: Any,
    excel_path: str,
    webhook_url: str = None,
) -> bool:
    """Send an automated demand report summary with the local Excel path."""

    if not webhook_url:
        webhook_url = get_webhook_url()
    if not webhook_url:
        return False

    keywords = [getattr(plan, "keyword", str(plan)) for plan in keyword_plans]
    lines = [
        "**MediaCrawler 自动需求采集完成**",
        "",
        "**平台：** " + "、".join(platforms),
        "**本轮关键词：** " + " / ".join(keywords),
        "**新增需求：** " + str(getattr(stats, "new_items", 0)) + " 条",
        "**评论需求：** " + str(getattr(stats, "comment_items", 0)) + " 条",
        "**正文需求：** " + str(getattr(stats, "body_items", 0)) + " 条",
        "**跳过重复：** " + str(getattr(stats, "skipped_duplicates", 0)) + " 条",
        "**失败任务：** " + str(getattr(stats, "failed_tasks", 0)) + " 个",
    ]
    if excel_path:
        lines.extend(["", "**Excel 文件：**", excel_path])
    else:
        lines.extend(["", "**Excel 文件：** 本轮未发现新增需求"])

    payload = {
        "msg_type": "interactive",
        "card": {
            "header": {"title": {"tag": "plain_text", "content": "自动需求采集完成"}, "template": "blue"},
            "elements": [
                {"tag": "markdown", "content": "\n".join(lines)},
                {"tag": "hr"},
                {"tag": "note", "elements": [{"tag": "plain_text", "content": "仅发送本地文件路径，不上传文件"}]},
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
