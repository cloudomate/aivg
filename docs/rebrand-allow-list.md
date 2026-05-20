# Rebrand allow-list — paths where "Hermes Voice" may persist

Feature 012 (AIVG rebrand) introduces a CI-runnable lint
(`tests/unit/test_no_legacy_branding.py`) that scans the working tree
for the obsolete product-name regex
`\bHermes Voice\b|\bhermes voice\b` and fails on any non-allow-listed
match.

This file is the **allow-list**. The lint reads it line-by-line:

- Whole-line `#` starts a comment.
- Each non-comment, non-blank line is a **gitignore-style fnmatch
  pattern** relative to the repo root. Trailing `/**` matches the dir
  recursively.

Add a path here when "Hermes Voice" legitimately persists there —
typically: the rebrand spec/plan/docs themselves, the compat shims
(which reference both names by design), the lint scanner + its
companion test, and any archived feature artifact that must stay
historically accurate.

If you find yourself wanting to add a path for a fresh non-historical
document, you probably mean to rewrite the prose instead — that's the
whole point of the rebrand.

```
# === Rebrand documentation itself ===
specs/012-aivg-branding/**
docs/rebrand-allow-list.md

# === Lint scanner + its companion tests ===
tests/unit/test_no_legacy_branding.py
# Tests that PROVE the rebrand happened need the legacy string as a
# search needle in `assert "Hermes Voice" not in …`-style assertions.
tests/unit/test_cli_tagline.py
tests/unit/test_constitution_principles_byte_equiv.py
tests/contract/test_rebrand_invariants.py
tests/fixtures/constitution_principles_normalized.md
# (test_compat_shim.py was deleted in Phase 9 along with the shims.)

# (Compat shims removed in feature 012 Phase 9 / T045–T047 — the
# allow-list entries for src/satellite_core/, src/sat_cli/, and
# src/hermes_satellite_adapter/ are no longer needed.)

# === Historical reference (single-mention "formerly Hermes Voice") ===
# These living docs each mention the old name exactly once for new
# readers to recognize the lineage; the lint allow-lists them rather
# than asking authors to obscure the rename history.
README.md
CLAUDE.md
CHANGELOG.md                       # records the rebrand entry
.specify/memory/constitution.md    # Sync Impact Report records the rebrand
specs/011-satellite-management/contracts/management-api.yaml
specs/011-satellite-management/plan.md
```
