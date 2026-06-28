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
        if llm_key:
            try:
                from api.services.solution_generator import generate_all_solutions
                sol_result = generate_all_solutions(
                    aggregation=agg,
                    classified_records=classified,
                    api_key=llm_key,
                    max_categories=5,
                )
                solutions_data = sol_result.get("solutions", [])
            except Exception as exc:
                logger.warning(f"[DataRouter] LLM solution generation failed: {exc}")
        
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

