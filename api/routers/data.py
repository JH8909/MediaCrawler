# -*- coding: utf-8 -*-
# Copyright (c) 2025 relakkes@gmail.com
#
# This file is part of MediaCrawler project.
# Repository: https://github.com/NanmiCoder/MediaCrawler/blob/main/api/routers/data.py
# GitHub: https://github.com/NanmiCoder
# Licensed under NON-COMMERCIAL LEARNING LICENSE 1.1
#
# 声明：本代码仅供学习和研究目的使用。使用者应遵守以下原则：
# 1. 不得用于任何商业用途。
# 2. 使用时应遵守目标平台的使用条款和robots.txt规则。
# 3. 不得进行大规模爬取或对平台造成运营干扰。
# 4. 应合理控制请求频率，避免给目标平台带来不必要的负担。
# 5. 不得用于任何非法或不当的用途。
#
# 详细许可条款请参阅项目根目录下的LICENSE文件。
# 使用本代码即表示您同意遵守上述原则和LICENSE中的所有条款。

import json
import os
import tempfile
import zipfile
from pathlib import Path
from typing import List, Optional

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel

from tools.utils import logger

router = APIRouter(prefix="/data", tags=["data"])

# Data directory
DATA_DIR = Path(__file__).parent.parent.parent / "data"
SUPPORTED_EXTENSIONS = {".json", ".jsonl", ".csv", ".xlsx", ".xls", ".sqlite", ".db"}


class DataSyncRequest(BaseModel):
    file_path: str


def get_file_info(file_path: Path) -> dict:
    """Get file information"""
    stat = file_path.stat()
    record_count = None

    # Try to get record count
    try:
        if file_path.suffix == ".json":
            with open(file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, list):
                    record_count = len(data)
        elif file_path.suffix == ".jsonl":
            with open(file_path, "r", encoding="utf-8-sig") as f:
                record_count = sum(1 for line in f if line.strip())
        elif file_path.suffix == ".csv":
            with open(file_path, "r", encoding="utf-8") as f:
                record_count = sum(1 for _ in f) - 1  # Subtract header row
    except Exception:
        pass

    return {
        "name": file_path.name,
        "path": str(file_path.relative_to(DATA_DIR)),
        "size": stat.st_size,
        "modified_at": stat.st_mtime,
        "record_count": record_count,
        "type": file_path.suffix[1:] if file_path.suffix else "unknown"
    }


@router.get("/files")
async def list_data_files(
    platform: Optional[str] = None,
    file_type: Optional[str] = None,
    sort_by: str = Query("modified_at", pattern="^(modified_at|name|size|record_count)$"),
    sort_order: str = Query("desc", pattern="^(asc|desc)$"),
    search: Optional[str] = None,
    offset: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
):
    """Get data file list with filtering, sorting, pagination"""
    if not DATA_DIR.exists():
        return {"files": [], "total": 0}

    all_files = []
    for root, dirs, filenames in os.walk(DATA_DIR):
        root_path = Path(root)
        for filename in filenames:
            file_path = root_path / filename
            if file_path.suffix.lower() not in SUPPORTED_EXTENSIONS:
                continue

            # Platform filter
            if platform:
                rel_path = str(file_path.relative_to(DATA_DIR))
                if platform.lower() not in rel_path.lower():
                    continue

            # Type filter
            if file_type and file_path.suffix[1:].lower() != file_type.lower():
                continue

            try:
                info = get_file_info(file_path)
                # Text search in filename
                if search and search.lower() not in info["name"].lower():
                    continue
                all_files.append(info)
            except Exception:
                continue

    # Sort
    reverse = sort_order == "desc"
    all_files.sort(key=lambda x: x.get(sort_by, 0) or 0, reverse=reverse)

    total = len(all_files)
    paginated = all_files[offset:offset + limit]

    return {"files": paginated, "total": total}


@router.get("/files/{file_path:path}")
async def get_file_content(file_path: str, preview: bool = True, limit: int = 100):
    """Get file content or preview"""
    full_path = _resolve_data_file(file_path)

    if preview:
        # Return preview data
        try:
            if full_path.suffix == ".json":
                with open(full_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if isinstance(data, list):
                        return {"data": data[:limit], "total": len(data)}
                    return {"data": data, "total": 1}
            elif full_path.suffix == ".csv":
                import csv
                with open(full_path, "r", encoding="utf-8") as f:
                    reader = csv.DictReader(f)
                    rows = []
                    total = 0
                    for i, row in enumerate(reader):
                        total += 1
                        if i < limit:
                            rows.append(row)
                    return {"data": rows, "total": total}
            elif full_path.suffix.lower() in (".xlsx", ".xls"):
                import pandas as pd
                # Read first limit rows
                df = pd.read_excel(full_path, nrows=limit)
                # Get total row count (only read first column to save memory)
                df_count = pd.read_excel(full_path, usecols=[0])
                total = len(df_count)
                # Convert to list of dictionaries, handle NaN values
                rows = df.where(pd.notnull(df), None).to_dict(orient='records')
                return {
                    "data": rows,
                    "total": total,
                    "columns": list(df.columns)
                }
            elif full_path.suffix == ".jsonl":
                rows = []
                total = 0
                with open(full_path, "r", encoding="utf-8-sig") as f:
                    for line in f:
                        line = line.strip()
                        if not line:
                            continue
                        total += 1
                        if len(rows) < limit:
                            rows.append(json.loads(line))
                return {"data": rows, "total": total}
            else:
                raise HTTPException(status_code=400, detail="Unsupported file type for preview")
        except json.JSONDecodeError:
            raise HTTPException(status_code=400, detail="Invalid JSON file")
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))
    else:
        # Return file download
        return FileResponse(
            path=full_path,
            filename=full_path.name,
            media_type="application/octet-stream"
        )


@router.get("/download/{file_path:path}")
async def download_file(file_path: str):
    """Download single file"""
    full_path = _resolve_data_file(file_path)

    return FileResponse(
        path=full_path,
        filename=full_path.name,
        media_type="application/octet-stream"
    )


class ExportRequest(BaseModel):
    file_paths: List[str]
    format: str = "zip"


@router.post("/export")
async def export_files(request: ExportRequest):
    """Bulk export files as ZIP archive"""
    resolved = []
    for fp in request.file_paths:
        try:
            full = _resolve_data_file(fp)
            resolved.append(full)
        except HTTPException:
            continue

    if not resolved:
        raise HTTPException(status_code=404, detail="No valid files to export")

    # Create ZIP in memory
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".zip")
    try:
        with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as zf:
            for fp in resolved:
                arcname = str(fp.relative_to(DATA_DIR))
                zf.write(fp, arcname)

        tmp_path = tmp.name
        tmp.close()
        return FileResponse(
            path=tmp_path,
            filename="mediacrawler_export.zip",
            media_type="application/zip",
            headers={"Content-Disposition": "attachment; filename=mediacrawler_export.zip"},
        )
    finally:
        # Clean up temp file after response
        import threading
        def _cleanup():
            import time
            time.sleep(5)
            try:
                os.unlink(tmp_path)
            except Exception:
                pass
        threading.Thread(target=_cleanup, daemon=True).start()


@router.get("/search")
async def search_data_files(
    q: str = Query(..., min_length=1, description="Search keyword"),
    platform: Optional[str] = None,
    limit: int = Query(50, ge=1, le=500),
):
    """Search within JSONL data files for records matching keyword"""
    if not DATA_DIR.exists():
        return {"results": [], "total": 0}

    results = []
    for root, dirs, filenames in os.walk(DATA_DIR):
        root_path = Path(root)
        for filename in filenames:
            file_path = root_path / filename
            if file_path.suffix.lower() not in {".jsonl", ".json", ".csv"}:
                continue

            if platform and platform.lower() not in str(file_path.relative_to(DATA_DIR)).lower():
                continue

            try:
                with open(file_path, "r", encoding="utf-8-sig", errors="ignore") as f:
                    for line in f:
                        line = line.strip()
                        if not line:
                            continue
                        if q.lower() in line.lower():
                            try:
                                record = json.loads(line)
                            except json.JSONDecodeError:
                                record = {"_raw": line[:200]}
                            results.append({
                                "file": str(file_path.relative_to(DATA_DIR)),
                                "record": record,
                            })
                            if len(results) >= limit:
                                break
                if len(results) >= limit:
                    break
            except Exception:
                continue
        if len(results) >= limit:
            break

    return {"results": results, "total": len(results), "query": q}


@router.get("/stats")
async def get_data_stats():
    """Get data statistics"""
    if not DATA_DIR.exists():
        return {"total_files": 0, "total_size": 0, "by_platform": {}, "by_type": {}}

    stats = {
        "total_files": 0,
        "total_size": 0,
        "by_platform": {},
        "by_type": {}
    }

    for root, dirs, filenames in os.walk(DATA_DIR):
        root_path = Path(root)
        for filename in filenames:
            file_path = root_path / filename
            if file_path.suffix.lower() not in SUPPORTED_EXTENSIONS:
                continue

            try:
                stat = file_path.stat()
                stats["total_files"] += 1
                stats["total_size"] += stat.st_size

                # Statistics by type
                file_type = file_path.suffix[1:].lower()
                stats["by_type"][file_type] = stats["by_type"].get(file_type, 0) + 1

                # Statistics by platform (inferred from path)
                rel_path = str(file_path.relative_to(DATA_DIR))
                for platform in ["xhs", "dy", "ks", "bili", "wb", "tieba", "zhihu"]:
                    if platform in rel_path.lower():
                        stats["by_platform"][platform] = stats["by_platform"].get(platform, 0) + 1
                        break
            except Exception:
                continue

    return stats


@router.post("/analyze-report")
async def analyze_and_report(request: DataSyncRequest):
    """Load data file, run analysis + AI solutions, send webhook report"""
    full_path = _resolve_data_file(request.file_path)
    try:
        # Step 1: Load records
        import json as _json
        records = []
        with open(full_path, "r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if line:
                    records.append(_json.loads(line))
        
        if not records:
            return {
                "status": "ok",
                "message": "无数据可分析",
                "total": 0,
                "categories": 0,
                "aggregation": [],
                "classified_records": [],
                "solutions": 0,
                "solutions_data": [],
                "webhook_sent": False,
            }
        
        # Step 2: LLM dedup before classification
        from api.services.dedup_filter import llm_dedup_records
        orig_count = len(records)
        deduped_records, removed_count = llm_dedup_records(records)
        if removed_count > 0:
            logger.info(f"[DataRouter] LLM dedup: {orig_count} -> {len(deduped_records)} ({removed_count} removed)")

        if not deduped_records:
            return {
                "status": "ok",
                "message": "去重后无有效数据",
                "total": 0,
                "categories": 0,
                "aggregation": [],
                "classified_records": [],
                "solutions": 0,
                "solutions_data": [],
                "webhook_sent": False,
            }

        # Step 3: Classify and aggregate
        from api.services.needs_analyzer import analyze_records
        analysis = analyze_records(deduped_records)
        agg = analysis.get("aggregation", [])
        classified = analysis.get("classified_records", [])
        
        # Step 3: Generate AI solutions if API key available
        import os as _os
        solutions_data = []
        llm_key = _os.environ.get("LLM_API_KEY", "")
        llm_api_url = _os.environ.get("LLM_API_URL", "https://api.deepseek.com/v1/chat/completions")
        llm_model = _os.environ.get("LLM_MODEL", "deepseek-v4-flash")
        if llm_key:
            try:
                from api.services.solution_generator import generate_all_solutions
                sol_result = generate_all_solutions(
                    aggregation=agg,
                    classified_records=classified,
                    api_key=llm_key,
                    api_url=llm_api_url,
                    model=llm_model,
                    max_categories=5,
                )
                solutions_data = sol_result.get("solutions", [])
            except Exception as exc:
                logger.warning(f"[DataRouter] LLM solution generation failed: {exc}")

        pm_analysis = {}
        if agg:
            try:
                from api.services.opportunity_evaluator import evaluate_opportunities
                pm_analysis = evaluate_opportunities(
                    aggregation=agg,
                    classified_records=classified,
                    solutions_data=solutions_data,
                    api_key=llm_key,
                    api_url=llm_api_url,
                    model=llm_model,
                )
            except Exception as exc:
                logger.warning(f"[DataRouter] PM opportunity evaluation failed: {exc}")
        
        # Step 5: Send webhook report (single consolidated message)
        from integrations.feishu_webhook import send_demand_report, get_webhook_url
        wu = get_webhook_url()
        webhook_sent = False

        # Load category rules for enriched report
        category_rules = {}
        _rules_path = os.path.join(os.path.dirname(__file__), "..", "data", "category_rules.json")
        if os.path.isfile(_rules_path):
            try:
                with open(_rules_path, "r", encoding="utf-8") as _f_rules:
                    category_rules = json.load(_f_rules)
            except Exception:
                pass

        # Extract platform name and keyword from the data file path
        # Path is: data/<platform>/<subdir>/file.jsonl — extract the platform folder
        _parts = full_path.relative_to(DATA_DIR).parts
        platform_name = _parts[0] if _parts else ""
        first_keyword = (deduped_records[0].get("source_keyword", "") or "") if deduped_records else ""

        if wu and agg:
            webhook_sent = send_demand_report(
                aggregation=agg,
                solutions_data=solutions_data,
                keyword=first_keyword,
                platform=platform_name,
                total=len(deduped_records),
                classified_records=classified,
                category_rules=category_rules,
                webhook_url=wu,
            )
        
        # Step 6: Persist report
        if agg:
            try:
                from api.services.report_store import save_report
                _report = save_report(
                    platform=platform_name,
                    keyword=first_keyword,
                    total=len(deduped_records),
                    aggregation=agg,
                    classified_records=classified,
                    solutions_data=solutions_data,
                    webhook_sent=webhook_sent,
                    pm_analysis=pm_analysis,
                )
                logger.info(f"[DataRouter] Report saved: {_report.get('file', '')}")
            except Exception as rpt_exc:
                logger.warning(f"[DataRouter] Report save failed: {rpt_exc}")

        return {
            "status": "ok",
            "total": len(deduped_records),
            "original_total": orig_count,
            "dedup_removed": removed_count,
            "categories": len(agg),
            "aggregation": agg,
            "classified_records": classified,
            "solutions": len(solutions_data),
            "solutions_data": solutions_data,
            "pm_analysis": pm_analysis,
            "webhook_sent": webhook_sent,
        }
    except Exception as exc:
        import traceback as _tb
        logger.error(f"[DataRouter] analyze_and_report failed: {_tb.format_exc()}")
        from fastapi import HTTPException
        raise HTTPException(status_code=500, detail=f"{type(exc).__name__}: {exc}")

@router.get("/analysis-reports")
async def list_analysis_reports(
    platform: Optional[str] = None,
    limit: int = Query(20, ge=1, le=100),
):
    """Get list of previously generated analysis reports (lightweight summaries)."""
    from api.services.report_store import list_reports
    reports = list_reports(limit=limit, platform=platform)
    return {"reports": reports, "total": len(reports)}


@router.get("/analysis-reports/latest")
async def latest_analysis_report(platform: Optional[str] = None):
    """Get the most recent analysis report with full data."""
    from api.services.report_store import get_latest_report
    report = get_latest_report(platform=platform)
    if not report:
        return {
            "status": "ok",
            "total": 0,
            "categories": 0,
            "aggregation": [],
            "solutions": 0,
            "solutions_data": [],
            "message": "暂无报告",
        }
    return report


def _resolve_data_file(file_path: str) -> Path:
    full_path = (DATA_DIR / file_path).resolve()
    try:
        full_path.relative_to(DATA_DIR.resolve())
    except ValueError:
        raise HTTPException(status_code=403, detail="Access denied")

    if not full_path.exists():
        raise HTTPException(status_code=404, detail="File not found")
    if not full_path.is_file():
        raise HTTPException(status_code=400, detail="Not a file")
    return full_path


# ── MVP Plan Generator ──────────────────────────────────────────────

_MVP_PLAN_PROMPT = """你是资深产品经理 + 技术架构师。基于以下真实用户需求数据，为「{category}」生成一份完整可落地的 MVP 方案。

## 数据背景
- 相关证据数：{count} 条
- 机会评分：{score}/100
- PM 决策：{decision}

## 用户真实反馈（摘录）
{evidence_texts}

## 已有方案方向
{existing_solutions}

## 竞品参考
- Meltwater：企业级社交聆听（$8K-50K/年），PR+社交+广播电视全覆盖
- Brand24：中端市场（$149-399/月），AI 情绪检测 + 异常告警
- YouScan：视觉 AI 领导者（$299+/月），Logo/场景识别
- Sprout Social：主流社媒管理（$249-499/座/月），聆听为附加功能
- MediaCrawler：唯一开源 + 自部署替代方案

## 要求
只输出 JSON，不要其他文字。格式：
{{
  "product_name": "产品名称推荐（8字以内，符合中文互联网产品命名习惯，如xx助手/xx发现/xx指南/xx雷达）",
  "mvp_name": "方案名称（15字以内）",
  "elevator_pitch": "一句话价值主张（25字以内）",
  "target_persona": "目标用户（角色+场景+使用频率）",
  "core_workflow": ["步骤1", "步骤2", "步骤3", "步骤4"],
  "feature_roadmap": [
    {{"phase": "V1 · 2周 · 验证核心假设", "features": ["功能1", "功能2", "功能3"], "hypothesis": "验证什么"}},
    {{"phase": "V2 · 4周 · 扩展能力", "features": ["功能1", "功能2"], "hypothesis": "验证什么"}},
    {{"phase": "V3 · 8周 · 建立壁垒", "features": ["功能1"], "hypothesis": "验证什么"}}
  ],
  "tech_architecture": {{
    "frontend": "技术栈",
    "backend": "技术栈",
    "data": "存储方案",
    "ai": "AI 能力",
    "deploy": "部署方式"
  }},
  "success_metrics": {{
    "north_star": "北极星指标",
    "secondary": ["辅助1", "辅助2"]
  }},
  "go_to_market": "获客策略（2-3句）",
  "risks": [
    {{"risk": "风险", "level": "高/中/低", "mitigation": "缓解方案"}}
  ],
  "budget": {{"dev_weeks": 6, "monthly_ops": "月运维成本描述"}}
}}"""


class MVPPlanRequest(BaseModel):
    category: str
    count: int = 0
    score: int = 0
    decision: str = ""
    evidence_texts: list = []
    solution_name: str = ""
    solution_summary: str = ""
    solution_features: list = []


@router.post("/generate-mvp-plan")
async def generate_mvp_plan(request: MVPPlanRequest):
    """Generate a detailed MVP plan for one product opportunity.

    Uses LLM when API key is available; falls back to structured synthesis
    from existing PM analysis data when key is absent.
    """
    import os as _os
    import json as _json

    llm_key = _os.environ.get("LLM_API_KEY", "")
    llm_api_url = _os.environ.get("LLM_API_URL", "https://api.deepseek.com/v1/chat/completions")
    llm_model = _os.environ.get("LLM_MODEL", "deepseek-v4-flash")

    # Build existing solutions string
    existing_solutions = ""
    if request.solution_name:
        existing_solutions += f"方案名称：{request.solution_name}\n"
    if request.solution_summary:
        existing_solutions += f"方案摘要：{request.solution_summary}\n"
    if request.solution_features:
        existing_solutions += "核心功能：\n"
        for f in request.solution_features[:4]:
            existing_solutions += f"  - {f}\n"
    if not existing_solutions.strip():
        existing_solutions = "暂无已有方案"

    evidence_texts = "\n".join(f"- {t[:120]}" for t in (request.evidence_texts or [])[:8])
    if not evidence_texts.strip():
        evidence_texts = "暂无原文摘录"

    # ── LLM path ──
    if llm_key:
        try:
            import httpx
            prompt = _MVP_PLAN_PROMPT.format(
                category=request.category,
                count=request.count,
                score=request.score,
                decision=request.decision or "待评估",
                evidence_texts=evidence_texts,
                existing_solutions=existing_solutions,
            )
            with httpx.Client(timeout=90) as client:
                resp = client.post(
                    llm_api_url,
                    headers={"Authorization": f"Bearer {llm_key}", "Content-Type": "application/json"},
                    json={
                        "model": llm_model,
                        "messages": [
                            {"role": "system", "content": "你是资深产品经理和技术架构师。只输出可解析的 JSON，不要输出其他文字。"},
                            {"role": "user", "content": prompt},
                        ],
                        "temperature": 0.4,
                        "max_tokens": 3000,
                    },
                )
                resp.raise_for_status()
                data = resp.json()
                content = data["choices"][0]["message"]["content"]
            cleaned = content.strip()
            if cleaned.startswith("```"):
                cleaned = cleaned.split("\n", 1)[-1]
                if "```" in cleaned:
                    cleaned = cleaned.rsplit("```", 1)[0]
            if cleaned.startswith("json"):
                cleaned = cleaned[4:].strip()
            plan = _json.loads(cleaned)
            if isinstance(plan, dict):
                plan["source"] = "llm"
                plan["category"] = request.category
                return {"status": "ok", "plan": plan}
        except Exception as exc:
            logger.warning(f"[MVPRouter] LLM MVP plan generation failed: {exc}")

    # ── Fallback: structured synthesis ──
    plan = _synthesize_mvp_plan(
        category=request.category,
        count=request.count,
        score=request.score,
        decision=request.decision or "validate",
        evidence_texts=request.evidence_texts or [],
        solution_name=request.solution_name,
        solution_summary=request.solution_summary,
        solution_features=request.solution_features,
    )
    plan["source"] = "synthesis"
    plan["category"] = request.category
    return {"status": "ok", "plan": plan}


def _synthesize_mvp_plan(
    category: str,
    count: int,
    score: int,
    decision: str,
    evidence_texts: list,
    solution_name: str = "",
    solution_summary: str = "",
    solution_features: list = None,
) -> dict:
    """Build a structured MVP plan from existing data when LLM is unavailable."""

    # Normalize inputs
    solution_features = solution_features or []
    short_cat = category.replace("「", "").replace("」", "").replace("相关需求", "").strip()
    if "&" in short_cat:
        short_cat = min([p.strip() for p in short_cat.split("&")], key=len)

    # Elevator pitch: derive from category + solution data
    pitch = solution_summary[:50] if solution_summary else f"帮助{short_cat}用户从真实评价中快速获取决策依据"
    if len(pitch) > 50:
        pitch = pitch[:47] + "..."

    # Core workflow: generic 4-step + category-specific step
    workflow = [
        f"用户输入{short_cat}相关需求或问题",
        f"系统跨平台采集真实用户评价和讨论",
        f"AI 自动分类、提取关键痛点和好评点",
        f"生成结构化报告，关联原始证据",
    ]

    # Feature roadmap
    features_v1 = solution_features[:3] if solution_features else [f"{short_cat}数据聚合", "AI 要点总结", "原文溯源"]
    features_v2 = solution_features[3:5] if len(solution_features) > 3 else ["个性化推荐", "趋势预警"]
    features_v3 = ["社区/达人生态", "行业 Benchmark"] if score >= 70 else ["用户反馈闭环", "迭代优化引擎"]
    if len(features_v2) < 2:
        features_v2.append("用户收藏与分享")
    if len(features_v1) < 2:
        features_v1.append(f"{short_cat}搜索与过滤")

    feature_roadmap = [
        {"phase": "V1 · 2周 · 验证核心假设", "features": features_v1[:3], "hypothesis": f"{short_cat}用户愿意用工具替代人工搜索和阅读"},
        {"phase": "V2 · 4周 · 扩展能力", "features": features_v2[:2], "hypothesis": f"个性化推荐能提升留存和复用率"},
        {"phase": "V3 · 8周 · 建立壁垒", "features": features_v3[:2], "hypothesis": f"社区+数据飞轮形成竞争壁垒"},
    ]

    # Tech architecture: domain-aware
    domain_tech = {
        "餐饮": {"frontend": "微信小程序", "backend": "Python FastAPI", "data": "SQLite + Redis 缓存", "ai": "jieba 分词 + 情感分析", "deploy": "Docker + 阿里云/腾讯云"},
        "旅游": {"frontend": "微信小程序", "backend": "Python FastAPI", "data": "PostgreSQL + 地图 API", "ai": "攻略生成 AI + 行程优化算法", "deploy": "Docker + 阿里云"},
        "食品": {"frontend": "微信小程序", "backend": "Python FastAPI", "data": "MongoDB + OCR 引擎", "ai": "图像识别 + 成分分析 NLP", "deploy": "Docker + 阿里云"},
        "学习": {"frontend": "React SPA", "backend": "Python FastAPI", "data": "PostgreSQL + 课程聚合 API", "ai": "学习路径推荐引擎", "deploy": "Docker + Vercel/阿里云"},
        "自动化": {"frontend": "Web UI + CLI", "backend": "Python + n8n", "data": "SQLite + 日志文件", "ai": "规则引擎 + LLM 辅助", "deploy": "Docker / 本地安装"},
        "数据": {"frontend": "React + ECharts", "backend": "Python FastAPI", "data": "MongoDB + Redis", "ai": "异常检测 + 趋势预测", "deploy": "Docker + 云服务器"},
        "电商": {"frontend": "React SPA", "backend": "Python FastAPI", "data": "PostgreSQL + 电商 API", "ai": "选品推荐 + 利润预测", "deploy": "Docker + 阿里云"},
        "社交": {"frontend": "管理后台 Web", "backend": "Python + 微信机器人框架", "data": "SQLite + Redis", "ai": "自动回复 NLP + 活跃度分析", "deploy": "Docker / 本地部署"},
        "开发者": {"frontend": "CLI + Web UI", "backend": "Python / Go", "data": "PostgreSQL + 代码仓库 API", "ai": "代码生成 + 安全扫描", "deploy": "Docker + 云 / 本地"},
    }

    tech = {"frontend": "React SPA", "backend": "Python FastAPI", "data": "PostgreSQL", "ai": "NLP + 推荐引擎", "deploy": "Docker + 云服务器"}
    for keyword, t in domain_tech.items():
        if keyword in category:
            tech = t
            break

    # Success metrics
    north_star = f"周活跃用户数" if score >= 65 else f"方案采纳率"
    secondary = [f"单次查询平均耗时", f"用户 7 日留存率"]

    # Go-to-market
    gtm = f"从{short_cat}相关社群（微信群、小红书、豆瓣小组）冷启动，提供免费基础版获取种子用户。通过用户反馈迭代产品，在目标人群中形成口碑传播。"

    # Risks
    risks = [
        {"risk": f"{short_cat}数据源不稳定或被平台封锁", "level": "高", "mitigation": "多平台冗余采集 + 用户手动补充 + 数据缓存策略"},
        {"risk": "用户付费意愿不明确", "level": "中", "mitigation": "先免费积累用户，通过增值功能（数据导出、高级分析）验证付费"},
        {"risk": "竞品快速复制核心功能", "level": "中", "mitigation": "通过开源社区 + 数据飞轮（更多用户→更多数据→更好模型）建立壁垒"},
    ]

    # Budget
    dev_weeks = 4 if score >= 70 else 6
    budget = {"dev_weeks": dev_weeks, "monthly_ops": f"¥300-800/月（云服务器 + API 调用费）"}

    # Product name: domain-aware naming
    _PRODUCT_NAME_MAP = {
        "餐饮": "吃探", "探店": "探探", "美食": "食评雷达", "旅游": "旅探", "出行": "出行智选",
        "食品": "食安助手", "安全": "成分雷达", "健康": "健康指南", "学习": "学途",
        "技能": "技升", "自动化": "自动助手", "效率": "效率工坊", "数据": "数据洞察",
        "可视化": "看板", "电商": "选品雷达", "选品": "选品智囊", "社交": "社群管家",
        "社区": "社区雷达", "运营": "运营助手", "内容创作": "创作工坊", "写作": "文思助手",
        "开发者": "DevKit", "工具": "工具箱", "脚本": "脚本助手", "生活用品": "好物雷达",
        "家居": "家居指南", "购物": "购探", "本地生活": "本地雷达", "家政": "家政助手",
        "汽车": "车评助手", "交通": "出行助手", "租房": "租房指南", "买房": "购房参谋",
    }
    product_name = ""
    for keyword, name in _PRODUCT_NAME_MAP.items():
        if keyword in category:
            product_name = name
            break
    if not product_name:
        product_name = short_cat[:4] + "助手" if len(short_cat) <= 6 else short_cat[:3] + "雷达"

    return {
        "product_name": product_name,
        "mvp_name": solution_name[:20] if solution_name else f"「{short_cat}」智能决策工具",
        "elevator_pitch": pitch,
        "target_persona": f"有{short_cat}需求的活跃用户，每周至少 1-2 次相关消费或决策行为",
        "core_workflow": workflow,
        "feature_roadmap": feature_roadmap,
        "tech_architecture": tech,
        "success_metrics": {"north_star": north_star, "secondary": secondary},
        "go_to_market": gtm,
        "risks": risks,
        "budget": budget,
    }
