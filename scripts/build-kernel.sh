#!/bin/bash
# SPDX-License-Identifier: GPL-2.0-only
# Run only inside the pinned compiler container; modifies its SDK overlay.
set -euo pipefail
export PATH=/opt/epyc7002/bin:/usr/bin:/bin
KDIR=/opt/epyc7002/build
SRC=/work/kernel-source/linux-5.10.x
cp -a "$SRC/drivers/video/fbdev/core/." "$KDIR/drivers/video/fbdev/core/"
cp "$SRC/drivers/video/fbdev/edid.h" "$KDIR/drivers/video/fbdev/edid.h"
cp -a "$SRC/arch/x86/video/." "$KDIR/arch/x86/video/"
ARGS=(CC=x86_64-pc-linux-gnu-gcc LD=x86_64-pc-linux-gnu-ld CROSS_COMPILE=x86_64-pc-linux-gnu- ARCH=x86_64 -j2)
make -C "$KDIR" M="$KDIR/arch/x86/video" "${ARGS[@]}" modules
make -C "$KDIR" M="$KDIR/drivers/video/fbdev/core" "${ARGS[@]}" modules
make -C /work/upstream/kernel/gpu_unlock KDIR="$KDIR" "${ARGS[@]}"
mkdir -p /work/stage/modules
cp "$KDIR/arch/x86/video/fbdev.ko" /work/stage/modules/
cp "$KDIR/drivers/video/fbdev/core/fb.ko" /work/stage/modules/
cp /work/upstream/kernel/gpu_unlock/gpu_unlock.ko /work/stage/modules/
