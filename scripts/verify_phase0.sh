#!/usr/bin/env bash
set -euo pipefail

project_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
python_bin="${ACOUSTICFEM_PYTHON:-/Users/peterzhoumacmini/.micromamba/envs/acoustics-phase0/bin/python}"
report_dir="$project_dir/.pytest_cache/phase0_gate"

if [[ ! -x "$python_bin" ]]; then
  echo "PHASE0_GATE_FAILED: interpreter is not executable: $python_bin" >&2
  exit 1
fi

cd "$project_dir"
mkdir -p "$report_dir"
shasum -a 256 -c docs/baselines/phase0-production-source.sha256
"$python_bin" -m pytest -m 'not known_defect' -q \
  --junitxml="$report_dir/normal.xml"
"$python_bin" -m pytest tests/known_defects -q \
  --junitxml="$report_dir/known-defects.xml"
"$python_bin" scripts/check_phase0_junit.py \
  "$report_dir/normal.xml" "$report_dir/known-defects.xml"
