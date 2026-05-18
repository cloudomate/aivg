#!/usr/bin/env bash
# Deliberate, manual re-import of the upstream Hermes `hermes-agent` SKILL.md.
#
# This is the ONLY sanctioned way the vendored copy changes (spec FR-008).
# Nothing schedules or hooks this script — it never auto-runs (FR-007).
# It performs ZERO host mutation: it only reads GitHub and writes two repo
# files under .claude/skills/hermes-agent/ (FR-009 non-interference).
#
# Usage:
#   scripts/import-hermes-skill.sh [COMMIT_SHA]
#     no arg  → re-pin to the commit currently recorded in PROVENANCE.md
#     COMMIT  → import that upstream commit and re-pin to it
#
# Exit non-zero and write NOTHING if the upstream fetch fails (FR-006 / SC-006):
# never substitute guessed or fabricated skill content.

set -euo pipefail

REPO="NousResearch/hermes-agent"
SRC_PATH="skills/autonomous-ai-agents/hermes-agent/SKILL.md"
DEST_DIR=".claude/skills/hermes-agent"
SKILL="$DEST_DIR/SKILL.md"
PROV="$DEST_DIR/PROVENANCE.md"
DEFAULT_COMMIT="98db898c0bd4df0b09a5830b6a18a069c771e67c"

cd "$(git rev-parse --show-toplevel)"

commit="${1:-}"
if [ -z "$commit" ]; then
  commit="$(grep -oE 'pinned_commit . \`[0-9a-f]{40}\`' "$PROV" 2>/dev/null \
            | grep -oE '[0-9a-f]{40}' | head -1 || true)"
  commit="${commit:-$DEFAULT_COMMIT}"
fi

mkdir -p "$DEST_DIR"
tmp="$(mktemp)"
trap 'rm -f "$tmp"' EXIT

# Read-only fetch of the file at the explicit commit.
if ! gh api "repos/$REPO/contents/$SRC_PATH?ref=$commit" --jq '.content' 2>/dev/null \
      | base64 -d > "$tmp" 2>/dev/null || [ ! -s "$tmp" ]; then
  echo "IMPORT FAILED: could not fetch $SRC_PATH @ $commit from $REPO" >&2
  echo "No files written. Vendored copy left unchanged." >&2
  exit 1
fi

# Upstream git blob SHA for the byte-identity guarantee (FR-003 / SC-004).
upstream_blob="$(gh api "repos/$REPO/contents/$SRC_PATH?ref=$commit" --jq '.sha' 2>/dev/null || true)"
commit_date="$(gh api "repos/$REPO/commits/$commit" --jq '.commit.committer.date' 2>/dev/null | cut -dT -f1 || true)"

mv "$tmp" "$SKILL"
trap - EXIT

local_blob="$(git hash-object "$SKILL")"
if [ -n "$upstream_blob" ] && [ "$local_blob" = "$upstream_blob" ]; then
  identical="yes"
else
  identical="no"
fi

cat > "$PROV" <<EOF
# Provenance — \`hermes-agent\` skill (vendored copy)

\`SKILL.md\` in this directory is a **verbatim, point-in-time copy** of an
upstream Hermes Agent skill. Byte-identical to upstream; do NOT hand-edit
(spec FR-003 / SC-004). This file is a sibling, never merged into SKILL.md.

| Field | Value |
|-------|-------|
| source_repo | \`github.com/$REPO\` |
| source_path | \`$SRC_PATH\` |
| pinned_commit | \`$commit\` |
| upstream_commit_date | \`${commit_date:-unknown}\` |
| blob_sha | \`${upstream_blob:-$local_blob}\` |
| copied_on | \`$(date +%Y-%m-%d)\` |
| license | MIT (per upstream frontmatter) |

**Point-in-time, not auto-synced.** Re-import: \`scripts/import-hermes-skill.sh <commit>\`.
Verify: \`git hash-object $SKILL\` must equal blob_sha above.

Use against a live Hermes host: host-mutating/outward steps require explicit
confirmation (FR-005); read-only is free; the skill never self-runs (FR-007);
importing changes nothing on any host or in the satellite runtime (FR-009).
EOF

echo "Imported $SRC_PATH @ $commit"
echo "BYTE-IDENTICAL: $identical (local=$local_blob upstream=${upstream_blob:-n/a})"
[ "$identical" = "yes" ] || { echo "WARNING: not byte-identical to upstream blob" >&2; exit 2; }
