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

from tools.utils import logger


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
        logger.warning(f"[SolutionGenerator] No LLM_API_KEY set, using fallback solutions for '{category}'")
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
        logger.warning(f"[SolutionGenerator] LLM call failed for '{category}': {exc}")
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

# ── Domain-aware fallback engine ──
# When LLM is unavailable, this piechart decomposes category names
# into domain signals and generates relevant, specific solutions
# rather than generic "one-size-fits-all" templates.

# Domain signals: keyword → (product_type, action_verb, target_audience, tech_hint)
_DOMAIN_PRODUCT_MAP: Dict[str, Dict[str, Any]] = {
    "餐饮":   {"type": "小程序", "verb": "发现",      "audience": "吃货、探店爱好者",     "tech": "微信小程序 + Python API + 地图SDK"},
    "探店":   {"type": "小程序", "verb": "探店攻略",  "audience": "本地生活消费者",       "tech": "微信小程序 + Python爬虫 + AI摘要"},
    "美食":   {"type": "小程序", "verb": "美食推荐",  "audience": "美食爱好者、游客",     "tech": "微信小程序 + React + 推荐算法"},
    "旅游":   {"type": "小程序", "verb": "行程规划",  "audience": "自由行游客、家庭出游", "tech": "微信小程序 + 地图API + AI攻略生成"},
    "出行":   {"type": "小程序", "verb": "出行助手",  "audience": "通勤族、旅客",         "tech": "微信小程序 + 高德API + 实时数据"},
    "酒店":   {"type": "小程序", "verb": "比价预订",  "audience": "出行旅客",             "tech": "微信小程序 + 爬虫聚合 + 比价引擎"},
    "休闲娱乐": {"type": "小程序", "verb": "活动推荐","audience": "年轻人、家庭用户",     "tech": "微信小程序 + 推荐算法 + 票务API"},
    "食品":   {"type": "小程序", "verb": "成分分析",  "audience": "健康饮食者、家长",     "tech": "微信小程序 + OCR识别 + 营养数据库"},
    "健康":   {"type": "小程序", "verb": "健康管理",  "audience": "注重健康的消费者",     "tech": "微信小程序 + 营养API + AI分析"},
    "安全":   {"type": "小程序", "verb": "安全查询",  "audience": "消费者、家长",         "tech": "微信小程序 + 数据库查询 + 用户反馈"},
    "学习":   {"type": "网站",   "verb": "学习路径",  "audience": "职场新人、转行者",     "tech": "React + Python + 课程聚合API"},
    "技能":   {"type": "网站",   "verb": "技能提升",  "audience": "职场人士、学生",       "tech": "React + Node.js + AI推荐"},
    "自动化": {"type": "脚本",   "verb": "自动执行",  "audience": "运营人员、开发者",     "tech": "Python + n8n/Node-RED + API集成"},
    "效率":   {"type": "脚本",   "verb": "效率提升",  "audience": "知识工作者、程序员",   "tech": "Python/Electron + 系统API + AI"},
    "数据":   {"type": "网站",   "verb": "数据洞察",  "audience": "运营、产品经理",       "tech": "React + ECharts + Python + 爬虫"},
    "可视化": {"type": "网站",   "verb": "数据看板",  "audience": "数据分析师、管理者",   "tech": "Vue3 + ECharts + Python API"},
    "电商":   {"type": "网站",   "verb": "选品分析",  "audience": "卖家、选品经理",       "tech": "React + Python + 电商API聚合"},
    "选品":   {"type": "脚本",   "verb": "智能选品",  "audience": "电商卖家、跨境运营",   "tech": "Python + Pandas + 电商平台API"},
    "社交":   {"type": "微信机器人","verb":"社群运营","audience": "社群运营、私域操盘手",  "tech": "Python + 微信机器人框架 + SQLite"},
    "社区":   {"type": "网站",   "verb": "社区管理",  "audience": "社区运营、版主",       "tech": "React + Python + 内容审核AI"},
    "运营":   {"type": "微信机器人","verb":"运营助手","audience": "新媒体运营、私域运营",  "tech": "Python + 微信API + 自动化脚本"},
    "内容创作": {"type": "网站", "verb": "内容生成",  "audience": "自媒体创作者、博主",   "tech": "React + Python + LLM API"},
    "写作":   {"type": "网站",   "verb": "AI写作",    "audience": "作者、内容创作者",     "tech": "React + Python + 大模型API"},
    "开发者": {"type": "CLI工具", "verb": "开发辅助", "audience": "前后端开发者",         "tech": "Python/Go + CLI + API服务"},
    "工具":   {"type": "网站",   "verb": "工具集合",  "audience": "各类用户",             "tech": "Vue3 + Python + 插件架构"},
    "脚本":   {"type": "脚本",   "verb": "脚本工具",  "audience": "开发者、运维",         "tech": "Python + Shell + 自动化"},
    "生活用品": {"type": "小程序","verb":"好物推荐",  "audience": "租房党、家庭采购",     "tech": "微信小程序 + 爬虫 + 价格对比"},
    "家居":   {"type": "小程序", "verb": "家居灵感",  "audience": "租房党、新房装修",     "tech": "微信小程序 + 图片识别 + 电商导购"},
    "购物":   {"type": "小程序", "verb": "购物决策",  "audience": "消费者",               "tech": "微信小程序 + 比价引擎 + 真实评价聚合"},
    "本地生活": {"type": "小程序","verb":"本地服务",  "audience": "本地居民",             "tech": "微信小程序 + LBS + 服务聚合"},
    "家政":   {"type": "小程序", "verb": "服务预约",  "audience": "家庭用户",             "tech": "微信小程序 + 预约系统 + 评价体系"},
    "汽车":   {"type": "小程序", "verb": "选车助手",  "audience": "购车者、车主",         "tech": "微信小程序 + 车型数据库 + 对比工具"},
    "交通":   {"type": "小程序", "verb": "出行规划",  "audience": "通勤族",               "tech": "微信小程序 + 公交API + 实时路况"},
    "租房":   {"type": "小程序", "verb": "租房避坑",  "audience": "租房人群",             "tech": "微信小程序 + 房源聚合 + 评价分析"},
    "买房":   {"type": "小程序", "verb": "购房决策",  "audience": "购房者",               "tech": "微信小程序 + 房价数据 + AI分析"},
}

# Feature hints per domain — derived from category keywords.
# Only the *best* (longest) matching domain's features are used, not all.
_DOMAIN_FEATURE_TEMPLATES: Dict[str, List[str]] = {
    "餐饮探店": ["周边餐厅地图与评分聚合", "真实探店笔记与评价AI摘要", "排队等位时间预估", "招牌菜推荐与口味标签", "价格/环境/服务三维评分"],
    "美食体验": ["多平台口碑聚合排行", "AI提取高频好评与差评点", "性价比排名与同类对比", "用户实拍图集与探店Vlog"],
    "旅游出行": ["目的地攻略自动生成", "真实游记关键信息提取", "预算估算与行程优化", "避坑提示汇总与安全提醒"],
    "休闲娱乐": ["热门活动与演出推荐", "票务比价与抢票提醒", "场地评价与设施对比", "周末亲子/聚会方案生成"],
    "食品安全": ["配料表拍照识别与解析", "添加剂风险等级评级", "同类产品成分横向对比", "个性化饮食安全建议"],
    "成分健康": ["营养成分自动计算", "过敏原检测与预警", "健康食谱推荐与规划", "饮食记录与趋势分析"],
    "生活用品": ["真实开箱评测聚合", "同款全网比价", "替代品/平替智能推荐", "使用技巧与常见踩坑"],
    "家居购物": ["空间利用方案推荐", "风格搭配AI建议", "本地门店库存与价格查询", "安装/组装指南"],
    "本地生活": ["附近服务比价与预约", "真实用户评价聚合", "优惠与团购信息一站聚合", "服务响应时间预估"],
    "家政服务": ["服务项目与报价透明对比", "阿姨/师傅真实评价与评分", "在线预约与进度追踪", "服务质保与投诉通道"],
    "汽车交通": ["公交/地铁/驾车方案对比", "实时路况与延误预测", "常坐线路收藏与到站提醒", "出行成本与碳足迹计算"],
    "学习": ["职业目标→技能树映射", "免费课程资源聚合推荐", "学习进度可视化追踪", "同伴互助学习匹配"],
    "技能提升": ["技能缺口自动诊断", "项目实战练习生成", "导师/同行作品评价", "证书与面试路径规划"],
    "自动化": ["拖拽式工作流编辑器", "定时任务调度面板", "执行日志与错误告警", "常用API一键集成（微信/飞书/邮箱）"],
    "效率工具": ["重复操作一键自动化", "文件批处理（重命名/格式转换）", "智能分类与标签管理", "跨平台搜索聚合"],
    "数据分析": ["多平台数据聚合看板", "趋势预警与异常检测", "自动生成分析报告", "竞品对比仪表盘"],
    "可视化": ["拖拽式图表生成器", "实时数据大屏", "自然语言→图表查询", "报告一键导出PPT/PDF"],
    "电商": ["竞品价格变动监控", "销量趋势预测", "关键词搜索量排行分析", "利润模拟计算器"],
    "选品工具": ["跨平台选品数据聚合", "蓝海品类自动发现", "供应商匹配与评估", "利润与风险综合评分"],
    "社交": ["入群欢迎语自动发送", "关键词触发智能自动回复", "群活跃度统计看板", "定时内容推送排期"],
    "社区运营": ["内容质量自动审核", "水军/广告智能检测", "用户影响力排行", "话题趋势与情感分析"],
    "内容创作": ["多平台风格适配生成", "标题A/B测试建议", "热点话题实时推荐", "内容原创度检测"],
    "AI写作": ["大纲/章节自动生成", "违规词/敏感词提前预警", "文风一致性自动检查", "读者反馈情绪分析"],
    "开发者工具": ["API在线调试与测试", "自动生成接口文档", "代码片段搜索与管理", "依赖安全漏洞扫描"],
    "脚本": ["常用功能收藏与快捷键", "历史记录与撤销", "批量导入/导出处理", "插件市场与扩展生态"],
}

# Parse a category name to find the most specific domain match
def _detect_domain(category: str) -> Optional[Dict[str, Any]]:
    """Scan category name for known domain keywords, preferring longer matches."""
    best = None
    best_len = 0
    for keyword, info in _DOMAIN_PRODUCT_MAP.items():
        if keyword in category and len(keyword) > best_len:
            best = info
            best_len = len(keyword)
    return best

def _detect_features(category: str) -> List[str]:
    """Find feature templates matching this category.

    Tries composite keys first (e.g. "餐饮探店"), then falls back to single-token keys.
    Only returns features from the best (longest) matching key to avoid cross-domain mixing.
    """
    # Try composite keys (split by &) first — prefer longest match
    parts = [p.strip() for p in category.replace("「", "").replace("」", "").split("&")]
    best_features: List[str] = []
    best_len = 0

    for part in parts:
        for keyword, tmpl in _DOMAIN_FEATURE_TEMPLATES.items():
            if keyword in part and len(keyword) > best_len:
                best_features = list(tmpl)
                best_len = len(keyword)

    if best_features:
        return best_features[:4]

    # Fallback: single-token match in full category name
    for keyword, tmpl in _DOMAIN_FEATURE_TEMPLATES.items():
        if keyword in category:
            return list(tmpl)[:4]

    return ["核心场景数据采集与结构化", "AI驱动的关键洞察提炼", "用户自助查询与导出"]

def _clean_category_name(category: str) -> str:
    """Extract a short, display-friendly name from the full category string."""
    # Remove smart-relabel markers
    name = category.replace("「", "").replace("」", "").replace("相关需求", "").replace("相关", "").strip()
    # Take the first part before & as the primary domain
    if "&" in name:
        parts = [p.strip() for p in name.split("&")]
        # Return the shorter, more specific part
        return min(parts, key=len) if parts else name
    return name


def _fallback_solutions(category: str) -> List[Dict[str, Any]]:
    """Return template solutions when LLM is unavailable.

    Three-tier lookup:
    1. Exact match in curated _CATEGORY_FALLBACKS
    2. Partial keyword match in _CATEGORY_FALLBACKS
    3. Domain-aware rule-engine synthesis (NEW — replaces generic template)
    """
    # Tier 1: exact match
    if category in _CATEGORY_FALLBACKS:
        return _CATEGORY_FALLBACKS[category]

    # Tier 2: partial match in curated fallbacks
    for cat_key, solutions in _CATEGORY_FALLBACKS.items():
        if any(kw in category for kw in cat_key.split(" & ")):
            return solutions

    # Tier 3: domain-aware rule-engine synthesis
    domain = _detect_domain(category)
    features = _detect_features(category)
    short_name = _clean_category_name(category)

    if domain:
        action = domain["verb"]
        ptype = domain["type"]
        audience = domain["audience"]
        tech = domain["tech"]

        return [
            {
                "name": f"「{short_name}」{action}工具",
                "product_type": ptype,
                "summary": f"帮助{audience}快速{action}，用AI从真实评价中提炼关键信息",
                "target_users": audience,
                "core_features": features,
                "tech_stack": tech,
                "cost": "低",
                "timeline": "4周",
                "monetization": "免费+高级功能订阅",
                "reference": "基于真实用户反馈洞察",
                "innovation": f"专注「{short_name}」场景，用AI替代人工信息筛选",
            },
            {
                "name": f"「{short_name}」经验社区",
                "product_type": "小程序" if ptype == "小程序" else "网站",
                "summary": f"围绕{short_name}的真实用户经验分享与避坑社区",
                "target_users": f"关注{short_name}的用户与从业者",
                "core_features": ["真实经验UGC发布与话题标签", "AI自动归类与精华提取", "关注话题与个性化推送", "达人认证与问答互动"],
                "tech_stack": tech.replace("爬虫", "社区引擎").replace("API", "社区API"),
                "cost": "低",
                "timeline": "6周",
                "monetization": "广告 + 会员增值",
                "reference": "小红书、什么值得买",
                "innovation": f"用AI构造{short_name}领域的结构化知识图谱",
            },
        ]

    # Last resort: smart generic — still better than old "一站式解决方案"
    return [
        {
            "name": f"「{short_name}」需求洞察工具",
            "product_type": "网站",
            "summary": f"从社交媒体数据中自动发现与{short_name}相关的高频需求与用户痛点",
            "target_users": f"关注{short_name}的产品经理、创业者",
            "core_features": ["社交媒体需求自动采集", "痛点频率与热度排序", "每条结论绑定原文证据", "竞品方案对比与缺口分析"],
            "tech_stack": "React + Python + 社交媒体API",
            "cost": "低",
            "timeline": "3周",
            "monetization": "免费工具 + 高级报告付费",
            "reference": "MediaCrawler 同类工具",
            "innovation": f"用数据驱动{short_name}领域的产品决策，而非直觉",
        },
        {
            "name": f"「{short_name}」评价聚合器",
            "product_type": "小程序",
            "summary": f"跨平台聚合{short_name}相关的用户真实评价，AI一键提炼关键结论",
            "target_users": f"需要{short_name}决策参考的消费者",
            "core_features": ["多平台评价一站聚合", "AI生成优缺点摘要", "关键词云与情感趋势", "同类对比排行榜"],
            "tech_stack": "微信小程序 + Python爬虫 + AI摘要",
            "cost": "低",
            "timeline": "4周",
            "monetization": "免费使用 + 去广告订阅",
            "reference": "大众点评、小红书",
            "innovation": f"首次为{short_name}场景提供跨平台AI聚合决策参考",
        },
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
