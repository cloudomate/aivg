#!/usr/bin/env bash
# Feature 021 — regenerate the Python gRPC/protobuf bindings for the
# satellite transport from the canonical schemas in proto/.
#
# Output lands in src/aivg_core/transports/grpc/_generated/ and is CHECKED
# INTO GIT, so `pip install aivg` needs no protoc toolchain. Run this only
# after editing a proto/aivg/satellite/v1/*.proto file.
#
# Requires the `dev` extra (grpcio-tools). Usage:
#   scripts/gen_proto.sh            # uses ./.venv/bin/python if present, else python3
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PROTO_DIR="$ROOT/proto/aivg/satellite/v1"
OUT="$ROOT/src/aivg_core/transports/grpc/_generated"
PY="${PYTHON:-}"
if [ -z "$PY" ]; then
  if [ -x "$ROOT/.venv/bin/python" ]; then PY="$ROOT/.venv/bin/python"; else PY="python3"; fi
fi

mkdir -p "$OUT"

# Generate FLAT stubs (-I points at the proto dir, so generated sibling
# imports are `import audio_pb2` rather than the package-qualified
# `aivg.satellite.v1.audio_pb2`). We then rewrite that sibling import to a
# relative one so `_generated` imports cleanly as a normal sub-package
# without needing `proto/` on sys.path.
"$PY" -m grpc_tools.protoc \
  -I "$PROTO_DIR" \
  --python_out="$OUT" \
  --grpc_python_out="$OUT" \
  "$PROTO_DIR/audio.proto" \
  "$PROTO_DIR/management.proto"

# Rewrite `import <name>_pb2 as ...` -> `from . import <name>_pb2 as ...`
# in the generated *_pb2_grpc.py files (portable in-place sed for macOS+Linux).
for f in "$OUT"/*_pb2_grpc.py; do
  [ -e "$f" ] || continue
  "$PY" - "$f" <<'PYEOF'
import re, sys
p = sys.argv[1]
src = open(p).read()
src = re.sub(r'^import (\w+_pb2) as', r'from . import \1 as', src, flags=re.M)
open(p, "w").write(src)
PYEOF
done

echo "Generated stubs under $OUT/:"
ls -1 "$OUT"/*.py | sed "s#$ROOT/##"
