#!/bin/bash
# SPDX-License-Identifier: GPL-2.0-only
set -euo pipefail
ROOT=$(cd "$(dirname "$0")/.." && pwd)
IMAGE='dante90/syno-compiler@sha256:73f27f7f33c96549eb03ee6450c0eee8c54e16182d0ec62dcda65c7ec2f7d2fb'
test -d "$ROOT/work/upstream"
# Override /opt/do.sh; arbitrary commands are not accepted by that entrypoint.
# Do not use --cpus: the tested DSM kernel lacks the required CFS quota support.
docker run --rm --user 0:0 --memory 4g --entrypoint /bin/bash \
  -v "$ROOT:/repo:ro" -v "$ROOT/work:/work" \
  "$IMAGE" /repo/scripts/build-kernel.sh
