# -*- coding: utf-8 -*-
"""CLI entrypoint for one automated demand report run."""

from __future__ import annotations

import argparse
from pathlib import Path

from integrations.demand_report.runner import run_auto_demand_report


def main() -> int:
    parser = argparse.ArgumentParser(description="Run automated demand discovery report")
    parser.add_argument("--platforms", nargs="+", default=["xhs", "tieba", "zhihu"])
    parser.add_argument("--keyword-count", type=int, default=3)
    parser.add_argument("--keyword-offset", type=int, default=0)
    parser.add_argument("--max-notes-count", type=int, default=15)
    parser.add_argument("--output-dir", type=Path, default=None)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    kwargs = {
        "platforms": args.platforms,
        "keyword_count": args.keyword_count,
        "keyword_offset": args.keyword_offset,
        "max_notes_count": args.max_notes_count,
        "dry_run": args.dry_run,
    }
    if args.output_dir is not None:
        kwargs["output_dir"] = args.output_dir
    result = run_auto_demand_report(**kwargs)
    print("keywords:", " / ".join(plan.keyword for plan in result.keyword_plans))
    print("new_items:", result.stats.new_items)
    print("excel_path:", result.excel_path or "")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

