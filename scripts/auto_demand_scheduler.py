# -*- coding: utf-8 -*-
"""Simple local scheduler loop for automated demand reports."""

from __future__ import annotations

import argparse
import time

from scripts.auto_demand_report import main as run_once


INTERVAL_SECONDS = {
    "3h": 3 * 60 * 60,
    "6h": 6 * 60 * 60,
    "12h": 12 * 60 * 60,
    "day": 24 * 60 * 60,
    "week": 7 * 24 * 60 * 60,
}


def main() -> int:
    parser = argparse.ArgumentParser(description="Run automated demand report on an interval")
    parser.add_argument("--interval", choices=sorted(INTERVAL_SECONDS), default="6h")
    args, _unknown = parser.parse_known_args()

    while True:
        run_once()
        time.sleep(INTERVAL_SECONDS[args.interval])


if __name__ == "__main__":
    raise SystemExit(main())

