#!/usr/bin/env bash
# Renders every docs/*.d2 to an SVG next to it. Needs d2 (https://d2lang.com).
set -euo pipefail
cd "$(dirname "$0")"
for src in *.d2; do
  d2 "$src" "${src%.d2}.svg"
done
