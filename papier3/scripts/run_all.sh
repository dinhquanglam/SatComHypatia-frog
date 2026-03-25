#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT_DIR"

python3 papier3/scripts/run_experiments.py --config papier3/config/experiment_config.json "$@"
