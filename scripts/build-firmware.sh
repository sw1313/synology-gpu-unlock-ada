#!/bin/bash
# SPDX-License-Identifier: GPL-2.0-only
# Linux host dependencies: make, gcc, Python 3, tar, xz, zstd; network access.
set -euo pipefail
ROOT=$(cd "$(dirname "$0")/.." && pwd)
cd "$ROOT/work/upstream"
make assets INPUTS="$ROOT/work/inputs" ASSETS="$ROOT/work/assets"
make test-full INPUTS="$ROOT/work/inputs" ASSETS="$ROOT/work/assets"
mkdir -p "$ROOT/work/stage/firmware"
cp "$ROOT/work/assets/"*.bin "$ROOT/work/stage/firmware/"
cp "$ROOT/work/assets/NVIDIA-LICENSE" "$ROOT/work/stage/firmware/"
