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
    file_paths: Optional[List[str]] = None,
    content_items: Optional[List[Dict[str, str]]] = None,
    webhook_url: Optional[str] = None,
) -> bool:
    """Send a crawl completion summary to Feishu group chat via webhook"""
    if not webhook_url:
        webhook_url = get_webhook_url()
    if not webhook_url:
        return False
    stats = stats or {}

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
    webhook_url: str = None,
) -> bool:
    """Send a clean, focused demand discovery report to Feishu group chat.

    Shows:
      - Pain point ranking (top 8)
      - AI product proposal preview (top 3 categories, top 1 solution each)
      - Local console link
    """
    if not webhook_url:
        return False

    emojis = ["🔴", "🟠", "🟡", "🟢", "⚪", "🟣", "🟤"]

    lines = []
    lines.append("**📊 需求发现报告**")
    lines.append("")
    if platform:
        lines.append("**平台：** " + platform + ("  |  **关键词：** " + keyword if keyword else ""))
    lines.append("**本期发现 " + str(total) + " 条有效数据**")
    lines.append("")

    lines.append("**🔥 痛点排行 & 方案建议**")
    lines.append("")
    for i, item in enumerate(aggregation[:8]):
        emoji = emojis[i] if i < len(emojis) else "⚫"
        cat = item["category"]
        count = item["count"]
        hs = item.get("hot_score", 0)
        lines.append(emoji + " **" + cat + "**  · " + str(count) + "次" + ("  ★ 热度" + str(hs) if hs else ""))
        if solutions_data:
            for sol_item in solutions_data:
                if sol_item.get("category") == cat:
                    sols = sol_item.get("solutions", [])
                    if sols:
                        sol = sols[0]
                        ptype = sol.get("product_type", sol.get("solution_type", ""))
                        cost = sol.get("cost", "")
                        name = sol.get("name", sol.get("solution_name", ""))
                        lines.append("  💡 " + name + " (" + ptype + ("/" + cost + "成本" if cost else "") + ")")
                    break
        lines.append("")

    lines.append("📝 详情可查看本地控制台：http://localhost:8081")

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
            return True
    except Exception as exc:
        print("[FeishuWebhook] Failed to send demand report: " + str(exc))
        return False


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
