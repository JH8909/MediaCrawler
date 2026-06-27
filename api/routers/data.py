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

import os
import json
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from scripts.sync_to_feishu import run_sync

router = APIRouter(prefix="/data", tags=["data"])

# Data directory
DATA_DIR = Path(__file__).parent.parent.parent / "data"
SUPPORTED_EXTENSIONS = {".json", ".jsonl", ".csv", ".xlsx", ".xls", ".sqlite", ".db"}


class DataSyncRequest(BaseModel):
    file_path: str
    dry_run: bool = True
    batch_size: int = Field(default=100, ge=1, le=500)


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
async def list_data_files(platform: Optional[str] = None, file_type: Optional[str] = None):
    """Get data file list"""
    if not DATA_DIR.exists():
        return {"files": []}

    files = []
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
                files.append(get_file_info(file_path))
            except Exception:
                continue

    # Sort by modification time (newest first)
    files.sort(key=lambda x: x["modified_at"], reverse=True)

    return {"files": files}


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
                    for i, row in enumerate(reader):
                        if i >= limit:
                            break
                        rows.append(row)
                    # Re-read to get total count
                    f.seek(0)
                    total = sum(1 for _ in f) - 1
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
    """Download file"""
    full_path = _resolve_data_file(file_path)

    return FileResponse(
        path=full_path,
        filename=full_path.name,
        media_type="application/octet-stream"
    )


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


@router.post("/sync-to-feishu")
async def sync_data_file_to_feishu(request: DataSyncRequest):
    full_path = _resolve_data_file(request.file_path)
    input_format = _infer_sync_format(full_path)
    error_detail = ""
    try:
        stats = run_sync(
            input_path=full_path,
            input_format=input_format,
            dry_run=request.dry_run,
            batch_size=request.batch_size,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        error_detail = f"{type(exc).__name__}: {exc}"
        raise HTTPException(
            status_code=500,
            detail=error_detail,
        ) from exc

    result = {
        "status": "ok",
        "format": input_format,
        "dry_run": request.dry_run,
        "stats": {
            "success": stats.success,
            "skipped": stats.skipped,
            "failed": stats.failed,
            "pending": stats.pending,
        },
    }
    # If all records failed, try to get the underlying error
    if stats.success == 0 and stats.failed > 0 and hasattr(stats, "errors") and stats.errors:
        result["errors"] = stats.errors[:5]
    return result



@router.post("/analyze-report")
async def analyze_and_report(request: DataSyncRequest):
    """Load data file, run analysis + AI solutions, send webhook report"""
    full_path = _resolve_data_file(request.file_path)
    input_format = _infer_sync_format(full_path)
    
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
            return {"status": "ok", "message": "无数据可分析", "total": 0}
        
        # Step 2: Classify and aggregate
        from api.services.needs_analyzer import analyze_records
        analysis = analyze_records(records)
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
            except Exception:
                pass
        
        # Step 4: Send webhook report
        from integrations.feishu_webhook import send_crawl_summary, send_analysis_report, get_webhook_url
        wu = get_webhook_url()
        webhook_sent = False
        if wu:
            items = []
            for r in records[:5]:
                items.append({
                    "title": r.get("title", ""),
                    "desc": r.get("desc", "")[:80],
                    "nickname": r.get("nickname", ""),
                    "likes": r.get("liked_count", "0"),
                    "url": r.get("note_url", ""),
                })
            send_crawl_summary(platform=full_path.parent.name, crawler_type="analysis", keywords="", stats={"success": len(records), "skipped": 0, "failed": 0}, content_items=items[:5], webhook_url=wu)
            send_analysis_report(
                aggregation=agg,
                solutions_data=solutions_data,
                keyword="", platform=full_path.parent.name,
                total=len(records),
                webhook_url=wu,
            )
            webhook_sent = True
        
        return {
            "status": "ok",
            "total": len(records),
            "categories": len(agg),
            "aggregation": agg,
            "solutions": len(solutions_data),
            "webhook_sent": webhook_sent,
        }
    except Exception as exc:
        from fastapi import HTTPException
        raise HTTPException(status_code=500, detail=f"{type(exc).__name__}: {exc}")

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


def _infer_sync_format(file_path: Path) -> str:
    suffix = file_path.suffix.lower()
    if suffix == ".jsonl":
        return "jsonl"
    if suffix == ".csv":
        return "csv"
    if suffix in {".sqlite", ".db"}:
        return "sqlite"
    raise HTTPException(status_code=400, detail="Only JSONL, CSV and SQLite files can sync to Feishu")
