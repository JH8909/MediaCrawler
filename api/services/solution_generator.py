# -*- coding: utf-8 -*-
"""AI Solution Generator - call LLM to generate product solution proposals

Generates structured, actionable product ideas (mini-program / website / app / script / automation tool)
for each pain point category discovered from social media data.
"""

from __future__ import annotations

import json
import os
from enum import Enum
from typing import Any, Dict, List, Optional

import httpx


# Default config - uses DeepSeek via OpenAI-compatible API
DEFAULT_API_URL = "https://api.deepseek.com/v1/chat/completions"
DEFAULT_MODEL = "deepseek-v4-flash"


class ProductType(str, Enum):
    """Product form types that solutions can take"""
    MINI_PROGRAM = "小程序"
    WEBSITE = "网站"
    APP = "APP"
    SCRIPT = "脚本"
    CHROME_EXTENSION = "Chrome插件"
    AUTOMATION_TOOL = "自动化工具"
    WECHAT_BOT = "微信机器人"
    CLI_TOOL = "命令行工具"


SOLUTION_PROMPT = """你是一个产品经理 + 独立开发者。针对以下用户痛点，设计可落地的数字产品方案。

痛点分类：{category}
该分类出现次数：{count} 次（在所有反馈中排第 {rank} 位）
热度评分：{hot_score}
代表用户反馈：
{representative_text}

请生成 2 个具体的产品方案，每个方案包含以下完整结构：

方案名称：（简洁有力，20字以内）
产品形态：小程序 / 网站 / APP / 脚本 / Chrome插件 / 自动化工具 / 微信机器人 / 命令行工具
一句话简介：（50字以内说清做什么）
目标用户：（谁会用这个产品）
核心功能：（3点，每点一句话）
推荐技术栈：（前端 + 后端 + 基础设施）
开发成本：低 / 中 / 高
预估周期：X周 / X月
变现方式：（付费 / 广告 / 订阅 / 开源+托管 / 增值服务）
同类产品参考：（如果有的话）
创新点：（这个方案和现有方案比有什么不同）

要求：
1. 方案要具体、可落地，不要泛泛而谈
2. 输出 JSON 格式，不要包含其他文字
3. 优先考虑可以用 AI 技术实现的方案

输出格式：
[
  {{
    "name": "方案名称",
    "product_type": "小程序",
    "summary": "一句话简介",
    "target_users": "目标用户描述",
    "core_features": ["功能点1", "功能点2", "功能点3"],
    "tech_stack": "技术栈描述",
    "cost": "低",
    "timeline": "4周",
    "monetization": "变现方式",
    "reference": "同类产品参考",
    "innovation": "创新点说明"
  }}
]
"""


def generate_solutions(
    category: str,
    count: int,
    rank: int,
    representative_text: List[str],
    hot_score: float = 0.0,
    api_url: str = None,
    api_key: str = None,
    model: str = None,
    timeout: int = 60,
) -> List[Dict[str, Any]]:
    """Call LLM to generate product solutions for one pain point category.

    Returns list of solution dicts, or empty list on failure.
    """
    if api_url is None:
        api_url = os.getenv("LLM_API_URL", DEFAULT_API_URL)
    if api_key is None:
        api_key = os.getenv("LLM_API_KEY", "")
    if model is None:
        model = os.getenv("LLM_MODEL", DEFAULT_MODEL)

    if not api_key:
        return _fallback_solutions(category)

    prompt = SOLUTION_PROMPT.format(
        category=category,
        count=count,
        rank=rank,
        hot_score=hot_score,
        representative_text="\n".join(
            f"- {t[:150]}" for t in representative_text[:5]
        ),
    )

    try:
        with httpx.Client(timeout=timeout) as client:
            resp = client.post(
                api_url,
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": model,
                    "messages": [
                        {"role": "system", "content": "你是一个专业的产品经理和独立开发者。只输出 JSON，不要任何其他文字。"},
                        {"role": "user", "content": prompt},
                    ],
                    "temperature": 0.7,
                    "max_tokens": 2500,
                },
            )
            resp.raise_for_status()
            data = resp.json()
            content_text = data["choices"][0]["message"]["content"]

            # Try to parse JSON from the response
            cleaned = content_text.strip()
            if cleaned.startswith("```"):
                cleaned = cleaned.split("\n", 1)[-1]
                if "```" in cleaned:
                    cleaned = cleaned.rsplit("```", 1)[0]
            if cleaned.startswith("```json"):
                cleaned = cleaned[7:].strip()
                if cleaned.endswith("```"):
                    cleaned = cleaned[:-3].strip()

            solutions = json.loads(cleaned)
            if isinstance(solutions, list):
                return solutions
            return []
    except Exception as exc:
        print(f"[SolutionGenerator] LLM call failed for '{category}': {exc}")
        return _fallback_solutions(category)


# Preset product ideas per category for when LLM is unavailable
_CATEGORY_FALLBACKS = {
    "内容创作 & AI写作": [
        {
            "name": "AI内容创作助手",
            "product_type": "小程序",
            "summary": "帮助自媒体人快速生成小红书文案、标题和脚本",
            "target_users": "自媒体创作者、博主、新媒体运营",
            "core_features": ["一键生成小红书风格文案", "智能标题优化建议", "视频脚本提纲生成", "热点话题推荐"],
            "tech_stack": "微信小程序 + Python FastAPI + DeepSeek API",
            "cost": "低",
            "timeline": "3周",
            "monetization": "免费+高级版订阅",
            "reference": "写作蛙、Get写作",
            "innovation": "专注小红书平台，模板更精准",
        },
        {
            "name": "AI小说辅助写作工具",
            "product_type": "网站",
            "summary": "帮助网文作者防AI篡改、智能续写、敏感词自检",
            "target_users": "网络小说作者、起点/晋江作者",
            "core_features": ["AI篡改检测与对比", "智能续写建议", "敏感词提前预警", "章节连贯性检查"],
            "tech_stack": "React + Python + LLM API",
            "cost": "中",
            "timeline": "6周",
            "monetization": "月费订阅",
            "reference": "AI Writer、Jasper",
            "innovation": "专注网文场景的防篡改+辅助创作一体化",
        },
    ],
    "自动化 & 效率工具": [
        {
            "name": "自动化工作流搭建平台",
            "product_type": "网站",
            "summary": "拖拽式搭建自动化工作流，无需编程",
            "target_users": "运营人员、中小企业主、自由职业者",
            "core_features": ["可视化工作流编辑器", "集成常用API（微信/飞书/邮箱）", "定时任务调度", "执行日志与告警"],
            "tech_stack": "Vue3 + Node.js + n8n开源引擎",
            "cost": "中",
            "timeline": "8周",
            "monetization": "免费社区版+企业版",
            "reference": "n8n、Zapier、Make",
            "innovation": "针对国内用户优化，深度集成微信/飞书生态",
        },
        {
            "name": "批量文件处理助手",
            "product_type": "脚本",
            "summary": "一键批量重命名、格式转换、内容提取的桌面工具",
            "target_users": "办公人员、设计师、数据分析师",
            "core_features": ["拖拽式文件列表", "批量重命名规则预设", "图片/PDF/文档格式互转", "文本内容批量提取"],
            "tech_stack": "Python + PyQt6 / Electron",
            "cost": "低",
            "timeline": "2周",
            "monetization": "开源免费 + 付费高级功能",
            "reference": "Everything、Advanced Renamer",
            "innovation": "支持AI智能文件分类",
        },
    ],
    "数据分析 & 可视化": [
        {
            "name": "社交媒体数据监控看板",
            "product_type": "网站",
            "summary": "实时监控多平台热门话题、竞品动态和用户反馈",
            "target_users": "市场运营、产品经理、竞品分析人员",
            "core_features": ["多平台数据聚合（小红书/微博/知乎）", "热点趋势识别", "竞品内容对比分析", "自动生成数据报告"],
            "tech_stack": "React + ECharts + Python + MongoDB",
            "cost": "中",
            "timeline": "8周",
            "monetization": "月费订阅",
            "reference": "新榜、蝉妈妈",
            "innovation": "支持自定义监控维度和AI报告摘要",
        },
        {
            "name": "电商数据选品分析工具",
            "product_type": "脚本",
            "summary": "自动采集电商平台数据，辅助选品决策",
            "target_users": "跨境电商卖家、选品经理",
            "core_features": ["竞品价格监控", "销量趋势分析", "关键词搜索量排行", "利润计算器"],
            "tech_stack": "Python + Pandas + Jupyter + API",
            "cost": "低",
            "timeline": "3周",
            "monetization": "开源+付费数据源",
            "reference": "Jungle Scout、Helium 10",
            "innovation": "轻量级脚本版，无需注册即开即用",
        },
    ],
    "电商 & 选品工具": [
        {
            "name": "跨境卖家工具箱",
            "product_type": "网站",
            "summary": "一站式跨境运营工具：选品、定价、利润分析",
            "target_users": "跨境新手卖家、小团队运营",
            "core_features": ["多平台选品对比", "FBA利润模拟器", "关键词反查与优化", "竞品监控"],
            "tech_stack": "React + Python + Amazon API",
            "cost": "中",
            "timeline": "8周",
            "monetization": "月费订阅",
            "reference": "卖家精灵、Jungle Scout",
            "innovation": "针对新手卖家的低门槛设计",
        },
    ],
    "学习 & 技能提升": [
        {
            "name": "技能学习路径规划器",
            "product_type": "小程序",
            "summary": "根据目标职业自动生成个性化学习路径",
            "target_users": "转行学习者、大学生、职场新人",
            "core_features": ["职业目标→学习路径映射", "B站/慕课课程推荐", "学习进度追踪", "技能树可视化"],
            "tech_stack": "微信小程序 + Python + AI推荐引擎",
            "cost": "低",
            "timeline": "4周",
            "monetization": "免费+高级路径解锁",
            "reference": "慕课网、Coursera",
            "innovation": "聚焦国内免费学习资源整合",
        },
    ],
    "生活服务 & 本地生活": [
        {
            "name": "本地生活避坑指南",
            "product_type": "小程序",
            "summary": "聚合真实用户评价，AI总结避坑要点",
            "target_users": "本地生活消费者、旅游出行人群",
            "core_features": ["多平台评价聚合", "AI生成避坑摘要", "价格对比与历史趋势", "附近推荐"],
            "tech_stack": "微信小程序 + Python爬虫 + AI摘要",
            "cost": "低",
            "timeline": "4周",
            "monetization": "商家入驻/广告",
            "reference": "大众点评、小红书",
            "innovation": "AI自动聚合多平台真实评价",
        },
    ],
    "社交 & 社区运营": [
        {
            "name": "社群运营自动化助手",
            "product_type": "微信机器人",
            "summary": "自动管理微信群，定时推送、新人欢迎、自动回复",
            "target_users": "社群运营、私域操盘手",
            "core_features": ["入群欢迎语自动发送", "关键词自动回复", "定时内容推送", "群活跃度统计"],
            "tech_stack": "Python + WeChat机器人框架 + SQLite",
            "cost": "低",
            "timeline": "2周",
            "monetization": "免费版+高级功能付费",
            "reference": "微伴、企业微信SCRM",
            "innovation": "轻量级个人微信版，无需企业微信",
        },
    ],
    "开发者工具 & 脚本": [
        {
            "name": "API调试与文档生成工具",
            "product_type": "网站",
            "summary": "在线调试API并自动生成接口文档",
            "target_users": "前后端开发者、API测试人员",
            "core_features": ["在线API请求调试", "自动生成OpenAPI文档", "团队协作与分享", "Mock服务"],
            "tech_stack": "Vue3 + Go/Python + Swagger",
            "cost": "中",
            "timeline": "6周",
            "monetization": "开源+云托管服务",
            "reference": "Postman、Swagger UI",
            "innovation": "轻量级开源替代方案，支持自部署",
        },
    ],
}


def _fallback_solutions(category: str) -> List[Dict[str, Any]]:
    """Return template solutions when LLM is unavailable, matched by category name."""
    # Try exact match
    if category in _CATEGORY_FALLBACKS:
        return _CATEGORY_FALLBACKS[category]

    # Try partial match
    for cat_key, solutions in _CATEGORY_FALLBACKS.items():
        if any(kw in category for kw in cat_key.split(" & ")):
            return solutions

    # Generic fallback
    return [
        {
            "name": f"「{category}」痛点解决方案",
            "product_type": "网站",
            "summary": f"针对{category}场景的一站式解决方案",
            "target_users": f"有{category}需求的用户",
            "core_features": ["需求收集与分类", "匹配最佳解决方案", "效果追踪与反馈", "持续迭代优化"],
            "tech_stack": "React + Python + PostgreSQL",
            "cost": "中",
            "timeline": "6周",
            "monetization": "免费+高级订阅",
            "reference": "待调研",
            "innovation": "专注细分场景的垂直解决方案",
        }
    ]


def generate_all_solutions(
    aggregation: List[Dict[str, Any]],
    classified_records: List[Dict[str, Any]],
    api_url: str = None,
    api_key: str = None,
    model: str = None,
    max_categories: int = 5,
) -> Dict[str, Any]:
    """Generate solutions for top N pain point categories.

    Args:
        aggregation: [{"category": str, "count": int, "hot_score": float}, ...]
        classified_records: records with categories + extracted_text fields
        api_url/api_key/model: LLM config

    Returns:
        {
            "solutions": [{"category": str, "count": int, "hot_score": float, "solutions": [...]}, ...],
            "generated_count": int
        }
    """
    # Build representative texts per category from extracted_text
    category_samples: Dict[str, List[str]] = {}
    for record in classified_records:
        for cat_detail in record.get("category_details", []):
            cat_name = cat_detail["category"]
            if cat_name not in category_samples:
                category_samples[cat_name] = []
            # Use extracted_text first, fallback to title/desc
            text = record.get("extracted_text", "") or ""
            if not text:
                title = record.get("title", "") or ""
                desc = record.get("desc", "") or ""
                text = (title + " " + desc).strip()
            if text and len(category_samples[cat_name]) < 5:
                category_samples[cat_name].append(text)

    solutions = []
    for rank, item in enumerate(aggregation[:max_categories], 1):
        cat = item["category"]
        count = item["count"]
        hot_score = item.get("hot_score", 0.0)
        samples = category_samples.get(cat, [])

        sols = generate_solutions(
            category=cat,
            count=count,
            rank=rank,
            representative_text=samples,
            hot_score=hot_score,
            api_url=api_url,
            api_key=api_key,
            model=model,
        )
        solutions.append({
            "category": cat,
            "count": count,
            "hot_score": hot_score,
            "rank": rank,
            "solutions": sols,
        })

    return {
        "solutions": solutions,
        "generated_count": len(solutions),
    }
