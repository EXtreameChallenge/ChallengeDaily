#!/usr/bin/env python3
"""轮10 B24：把企业旧 JSON 迁入 SQLite（可独立运行，幂等）。

用法：
  python scripts/migrate_round10_data.py --data-dir "%APPDATA%\\challenge-daily\\backend-data"
"""
import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-dir", required=True)
    parser.add_argument("--home-dir", default="")
    args = parser.parse_args()
    os.environ["CHALLENGE_DAILY_DATA_DIR"] = args.data_dir
    if args.home_dir:
        os.environ["CHALLENGE_DAILY_HOME_DATA_DIR"] = args.home_dir

    import enterprise_store
    print(json.dumps({
        "data_dir": str(enterprise_store.DATA_DIR),
        "db_path": str(enterprise_store.DB_PATH),
        "home_dir": str(enterprise_store.HOME_DATA_DIR),
        "before": enterprise_store.legacy_counts(),
    }, ensure_ascii=False, indent=2))

    report = enterprise_store.migrate_home_data()
    print(json.dumps(report, ensure_ascii=False, indent=2, default=str))
    print(json.dumps({"after": enterprise_store.legacy_counts()}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
