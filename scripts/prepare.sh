#!/bin/bash
# SPDX-License-Identifier: GPL-2.0-only
set -euo pipefail
ROOT=$(cd "$(dirname "$0")/.." && pwd)
WORK="$ROOT/work"
PIN=d28c485418c3d9d034cd4bac19200bc33dd3453b
mkdir -p "$WORK"
# Refuse to patch an existing tree twice or silently reuse modified sources.
test ! -e "$WORK/upstream" || { echo 'work/upstream already exists; use a fresh checkout.' >&2; exit 1; }
git init "$WORK/upstream"
git -C "$WORK/upstream" remote add origin https://github.com/JustAResearcher/gpu-unlock-ada.git
git -C "$WORK/upstream" fetch --depth=1 origin "$PIN"
git -C "$WORK/upstream" checkout --detach FETCH_HEAD
test "$(git -C "$WORK/upstream" rev-parse HEAD)" = "$PIN"
git -C "$WORK/upstream" apply --check "$ROOT/patches/dsm-5.10-compat.patch"
git -C "$WORK/upstream" apply "$ROOT/patches/dsm-5.10-compat.patch"
URL='https://global.synologydownload.com/download/ToolChain/Synology%20NAS%20GPL%20Source/7.3-86009/epyc7002/linux-5.10.x.txz'
curl -fL --retry 3 "$URL" -o "$WORK/linux-5.10.x.txz"
cd "$WORK"
echo '0c5f70ba9a4c8372f862a5f2778b7fe8903b667f2a94671012a480a74295aaf1  linux-5.10.x.txz' | sha256sum -c -
mkdir -p kernel-source
tar -xf linux-5.10.x.txz -C kernel-source \
  linux-5.10.x/drivers/video/fbdev/core \
  linux-5.10.x/drivers/video/fbdev/edid.h \
  linux-5.10.x/arch/x86/video
