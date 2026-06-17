#!/bin/bash
# core/ 覆蓋率地板檢查（US4 cov-floor，TASK-73c-T6）
#
# 用途：pre-merge / milestone 本地手動跑，守住 core/ 覆蓋率不倒退。
#   omit 設定見 .coveragerc（web/* 排除；core/scrapers/utils.py 刻意保留）。
#   floor = M(86%) - 2 = 84%（2pp 緩衝防 flaky 與小幅測試刪除）。
#   CI 不強制此 fail-under（CI 維持只跑 pytest unit+integration、不擋 PR）。
#
# 用法：source venv/bin/activate && bash scripts/run_cov.sh

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
cd "$PROJECT_ROOT"

pytest tests/ \
    --ignore=tests/smoke --ignore=tests/e2e \
    -m "not smoke and not e2e" \
    --cov=core --cov=web \
    --cov-report=term-missing \
    --cov-fail-under=84
