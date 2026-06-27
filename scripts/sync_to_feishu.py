# -*- coding: utf-8 -*-

from __future__ import annotations

import argparse
import csv
import json
import sqlite3
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Dict, Iterable, List, Set

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def _configure_utf8_output() -> None:
    for stream_name in ("stdout", "stderr"):
        stream = getattr(sys, stream_name)
        if not stream or not getattr(stream, "encoding", None):
            continue
        if stream.encoding.lower() == "utf-8":
            continue
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")


_configure_utf8_output()

from integrations.feishu_client import FeishuBitableClient
from integrations.field_mapper import map_record_to_feishu_fields


DEFAULT_STATE_PATH = Path(".sync_state") / "feishu_synced_hashes.json"


@dataclass(frozen=True)
class SyncStats:
    success: int = 0
    skipped: int = 0
    failed: int = 0
    pending: int = 0


def read_input_records(input_path: Path, input_format: str) -> Iterable[Dict]:
    input_format = input_format.lower()
    if input_format == "jsonl":
        yield from _read_jsonl(input_path)
    elif input_format == "csv":
        yield from _read_csv(input_path)
    elif input_format == "sqlite":
        yield from _read_sqlite(input_path)
    else:
        raise ValueError(f"Unsupported input format: {input_format}")


def load_synced_hashes(state_path: Path = DEFAULT_STATE_PATH) -> Set[str]:
    if not state_path.exists():
        return set()
    data = json.loads(state_path.read_text(encoding="utf-8"))
    if isinstance(data, list):
        return {str(item) for item in data}
    if isinstance(data, dict):
        return {str(item) for item in data.get("hashes", [])}
    raise ValueError(f"Invalid sync state format: {state_path}")


def save_synced_hashes(
    hashes: Set[str],
    state_path: Path = DEFAULT_STATE_PATH,
) -> None:
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text(
        json.dumps(sorted(hashes), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def run_sync(
    input_path: Path,
    input_format: str,
    dry_run: bool,
    batch_size: int,
    state_path: Path = DEFAULT_STATE_PATH,
    client_factory: Callable[[], FeishuBitableClient] = FeishuBitableClient.from_env,
) -> SyncStats:
    if batch_size < 1 or batch_size > 500:
        raise ValueError("--batch-size must be between 1 and 500")

    synced_hashes = load_synced_hashes(state_path)
    pending_records: List[Dict] = []
    pending_hashes: Set[str] = set()
    skipped = 0

    for raw_record in read_input_records(input_path, input_format):
        fields = map_record_to_feishu_fields(raw_record)
        if fields is None:
            skipped += 1
            continue

        content_hash = fields["内容哈希"]
        if content_hash in synced_hashes or content_hash in pending_hashes:
            skipped += 1
            continue

        pending_records.append(fields)
        pending_hashes.add(content_hash)

    if dry_run:
        sample_payload = FeishuBitableClient.build_batch_payload(pending_records[:3])
        print(f"dry-run: 将同步 {len(pending_records)} 条，跳过 {skipped} 条")
        print(json.dumps(sample_payload, ensure_ascii=False, indent=2))
        return SyncStats(success=0, skipped=skipped, failed=0, pending=len(pending_records))

    client = client_factory()
    success = 0
    failed = 0
    for batch in _chunked(pending_records, batch_size):
        try:
            client.batch_create_records(batch)
        except Exception as exc:
            failed += len(batch)
            print(f"同步飞书失败: {exc}")
            continue

        success += len(batch)
        synced_hashes.update(item["内容哈希"] for item in batch)
        save_synced_hashes(synced_hashes, state_path)

    print(f"同步完成: 成功 {success} 条，跳过 {skipped} 条，失败 {failed} 条")
    return SyncStats(success=success, skipped=skipped, failed=failed, pending=0)


def _read_jsonl(input_path: Path) -> Iterable[Dict]:
    with input_path.open("r", encoding="utf-8-sig") as file:
        for line_no, line in enumerate(file, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                item = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"Invalid JSONL at line {line_no}: {exc}") from exc
            if isinstance(item, dict):
                yield item


def _read_csv(input_path: Path) -> Iterable[Dict]:
    with input_path.open("r", encoding="utf-8-sig", newline="") as file:
        yield from csv.DictReader(file)


def _read_sqlite(input_path: Path) -> Iterable[Dict]:
    with sqlite3.connect(input_path) as connection:
        connection.row_factory = sqlite3.Row
        table_rows = connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
        )
        for table in [row["name"] for row in table_rows]:
            rows = connection.execute(f'SELECT * FROM "{table}"')
            for row in rows:
                yield dict(row)


def _chunked(items: List[Dict], size: int) -> Iterable[List[Dict]]:
    for index in range(0, len(items), size):
        yield items[index : index + size]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Sync MediaCrawler exports to Feishu Bitable")
    parser.add_argument("--input", required=True, type=Path, help="Input export path")
    parser.add_argument(
        "--format",
        required=True,
        choices=["jsonl", "csv", "sqlite"],
        help="Input export format",
    )
    parser.add_argument("--dry-run", action="store_true", help="Print payload without calling Feishu")
    parser.add_argument("--batch-size", type=int, default=100, help="Records per batch, max 500")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    run_sync(
        input_path=args.input,
        input_format=args.format,
        dry_run=args.dry_run,
        batch_size=args.batch_size,
    )


if __name__ == "__main__":
    main()
