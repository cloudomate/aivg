# Phase 0 Research: AIVG Rebrand

**Feature**: `012-aivg-branding` · **Plan**: [plan.md](./plan.md) ·
**Spec**: [spec.md](./spec.md) · **Date**: 2026-05-20

Each item below states a decision, its rationale (tied to a binding rule
from the spec / constitution), and the alternatives considered. No
`NEEDS CLARIFICATION` markers remain after this phase.

---

## R-1. Compat-shim shape — re-export package with cached `DeprecationWarning`

**Decision**: `src/satellite_core/__init__.py` and `src/sat_cli/__init__.py`
become thin packages that:

1. Emit **one** `DeprecationWarning` per process on first import (cached
   via a module-level sentinel, not re-raised on subsequent imports).
2. Re-export from the new package: `from aivg_core import *` /
   `from aivg_cli import *`, plus explicit re-imports for any submodule
   the old `__all__` mentioned.

```python
# src/satellite_core/__init__.py — shape only
import warnings as _w
import sys as _sys

if "_aivg_shim_warned" not in _sys.__dict__:
    _w.warn(
        "satellite_core is renamed to aivg_core (feature 012, AIVG "
        "rebrand). Update imports to aivg_core.*. Shim removed in the "
        "next release.",
        DeprecationWarning,
        stacklevel=2,
    )
    _sys.__dict__["_aivg_shim_warned"] = True

from aivg_core import *  # noqa: F401,F403,E402
from aivg_core import models, registry, logsink, ...  # explicit submodules
```

**Rationale**:

- FR-003 / SC-004 want exactly **one** deprecation notice per process —
  not per import. Using a `sys.__dict__` sentinel (not a module-level
  `__init__` variable) survives reloads.
- Stdlib `warnings` filters honor `filterwarnings` so the existing
  pytest filter (`"ignore:satellite_core is renamed:DeprecationWarning"`)
  cleanly silences shim noise during tests.
- The existing two-hop shim from feature 011
  (`hermes_satellite_adapter → satellite_core`) continues to work
  unchanged; this feature adds a second hop
  (`satellite_core → aivg_core`). The two-hop is intentional: each shim
  emits its own deprecation pointing one step further along the path.

**Alternatives considered**:

- **Module-level `__getattr__` PEP-562 forwarder** — works but is
  surprising; importers can't `dir(satellite_core)` reliably.
- **No shim, hard rename** — fails FR-003 (external consumers break).

---

## R-2. CLI binary compat — keep `sat-cli` entry point, dispatch to `aivg`

**Decision**: `pyproject.toml` keeps both entries:

```toml
[project.scripts]
aivg = "aivg_cli.cli:app"
sat-cli = "sat_cli.cli:legacy_app"
```

`sat_cli/cli.py::legacy_app` is a tiny Typer wrapper that:

1. Writes one line to **stderr** the first time it runs:
   `"sat-cli is renamed to aivg (feature 012, AIVG rebrand). The legacy binary still works for this release."`
2. Forwards `sys.argv` to `aivg_cli.cli.app()`.

**Rationale**:

- FR-004: the legacy binary must work for one release.
- SC-004's "stderr never stdout" requirement is binding because JSON
  consumers pipe stdout — leaking the deprecation onto stdout would
  break their parsers.
- Keeping it as a Typer wrapper (not a plain shell stub) ensures
  arg-parsing parity, env-var passthrough, and exit-code parity with
  zero subprocess overhead.

**Alternatives considered**:

- **Console-script alias only** (no wrapper) — no deprecation notice
  appears, fails FR-004.
- **Shell-script stub** — needs a separate file in `bin/`, doesn't
  install on Windows reliably.

---

## R-3. Data-directory migration — first-run, atomic, leave-bak

**Decision**: `aivg_core/persistence.py` gains
`migrate_legacy_data_dir(*, src=Path("~/.satellite"), dst=Path("~/.aivg"))`,
called once from `ManagementService.__init__` (or wherever the registry
is first persisted) **before** any state read/write. Behavior:

1. If `dst/state.json` already exists and is newer than
   `src/state.json` (or `src/state.json` does not exist), no-op.
2. Otherwise: load `src/state.json`, write to `dst/state.json` via the
   existing atomic `tmp+rename` helper, then `os.replace(src/state.json,
   src/state.json.pre-aivg-rebrand.bak)`. The `firmware/` subtree is
   moved with the same atomic-rename pattern.
3. The migration is **idempotent**: a second startup with both files
   present picks the newer and skips.

**Rationale**:

- FR-005 + SC-005: existing `~/.satellite/state.json` must be preserved
  with a `.pre-aivg-rebrand.bak` suffix, never deleted; the new path
  must have identical content.
- "Leave-bak" gives the operator a rollback rope without invading the
  new directory.
- Doing the migration once on first run (rather than on every read)
  avoids the lazy-read complication where two processes race.

**Alternatives considered**:

- **Symlink `~/.satellite` → `~/.aivg`** — pollutes the home dir with
  a forwarding symlink that's never cleaned up; lint scanner can't
  tell whether a config file under `~/.satellite/` is "live" or a
  forwarding link.
- **Move-on-every-read** — adds a `Path.exists` check to every read;
  rare-event work in a hot path; complicates idempotency.

---

## R-4. Lint mechanics — pytest scanner with documented allow-list

**Decision**: `tests/unit/test_no_legacy_branding.py` walks the repo
from its parent root, opens every file under a fixed set of suffixes
(`.md`, `.py`, `.toml`, `.yaml`, `.yml`, `.cfg`), and fails when an
obsolete product-name regex matches a non-allow-listed file. The
allow-list lives in `docs/rebrand-allow-list.md` as a literal list of
`path` patterns (gitignore-style globs); the test reads it.

```python
# Pseudocode shape
ALLOW = read_allow_list(REPO_ROOT / "docs" / "rebrand-allow-list.md")
PATTERN = re.compile(r"\bHermes Voice\b|\bhermes voice\b")
offenders = []
for f in iter_repo_files(REPO_ROOT):
    if any(fnmatch.fnmatch(str(f.relative_to(REPO_ROOT)), pat) for pat in ALLOW):
        continue
    text = f.read_text(errors="ignore")
    for ln, line in enumerate(text.splitlines(), 1):
        if PATTERN.search(line) and not line.lstrip().startswith("#"):
            # comment-prefixed lines exempt to allow file-top historical notes
            offenders.append(f"{f.relative_to(REPO_ROOT)}:{ln}: {line.strip()}")
assert not offenders
```

**Rationale**:

- FR-012 + SC-008: lint runs as part of the standard `pytest`
  invocation; no extra CI plumbing.
- Reading the allow-list from a markdown file (rather than hard-coding
  paths in the test) means contributors edit one place to add a
  legitimate historical reference.
- Comment-prefixed lines exempt to keep the door open for a
  one-line "(formerly Hermes Voice)" note in a file's top docstring
  without re-listing every such file in the allow-list. The lint
  catches the body-text case (the one that matters for fresh readers).

**Allow-list seed** (`docs/rebrand-allow-list.md`):

```text
# Rebrand allow-list — paths where "Hermes Voice" may persist.
# One pattern per line; gitignore-style fnmatch.
docs/rebrand-allow-list.md
specs/012-aivg-branding/spec.md
specs/012-aivg-branding/plan.md
specs/012-aivg-branding/research.md
specs/012-aivg-branding/data-model.md
specs/012-aivg-branding/quickstart.md
specs/012-aivg-branding/contracts/rebrand-invariants.md
src/satellite_core/__init__.py          # compat shim — references both names
src/sat_cli/__init__.py
src/sat_cli/cli.py
src/hermes_satellite_adapter/__init__.py  # carried-over shim from feature 011
tests/unit/test_no_legacy_branding.py
tests/unit/test_compat_shim.py
```

**Alternatives considered**:

- **Pre-commit hook only** — misses out-of-tree edits; CI-friendly
  pytest is the simpler enforcement.
- **Hard-coded paths in the test** — adds friction every time a new
  legitimate reference appears.

---

## R-5. Constitution PATCH amendment — what changes

**Decision**: Bump constitution v2.0.0 → v2.0.1. Changes:

- Title: "Hermes Voice Satellite Constitution" → "AIVG Constitution"
  (or "AIVG (Hermes Voice) Satellite Constitution" if we keep the
  legacy name as a parenthetical for one release — spec lets us
  choose; we pick the cleaner "AIVG Constitution").
- Project-codename preface: replace "*Project codename: 'Hermes Voice'
  (historical)*" with "*Project codename: AIVG (AI Voice Gateway).
  Formerly 'Hermes Voice' through feature 011.*"
- Every "Hermes Voice" reference in body prose → "AIVG".
- Hermes-as-plugin references stay verbatim where they appear (rare
  in body; mostly in Principle IV).
- Sync Impact Report gains a bullet:
  - Version change: 2.0.0 → 2.0.1
  - Bump rationale: PATCH. Branding rebrand only (Hermes Voice →
    AIVG). No principle text gains or loses normative meaning.

**Rationale**:

- Spec FR-010 + SC-006: PATCH bump; no principle drift.
- A scripted byte-diff of every Principle section (removing
  whitespace, replacing "Hermes Voice" with a stable token before the
  diff) MUST produce zero differences. The plan ships this diff as a
  CI step in tasks.

**Alternatives considered**:

- **MINOR bump** — would imply added/expanded principle content; not
  the case here.
- **Skip the amendment** — leaves governance source-of-truth
  disagreeing with the codebase; fails FR-010.

---

## R-6. Specs touch-up policy — visible product name only

**Decision**: Specs 001–011 get a **product-name-only sweep**. The
rewrite replaces "Hermes Voice" / "Hermes Voice Satellite" with
"AIVG" in prose. **Implementation details, decisions, dates, and
historical task labels are left intact** — these are historical
artifacts, not living docs.

Where a historical spec references the **old Python identifier**
(e.g. `hermes_satellite_adapter`, `satellite_core`, `sat-cli`), the
identifier stays exactly as it was written (these specs document the
state at the time they were written). Only product-name prose
mentions are rewritten.

**Rationale**:

- FR-002 + SC-001: a fresh reader of any spec should see AIVG.
- Spec Assumption: git history is not rewritten; the same logic
  extends to historical specs' implementation details.
- The lint (R-4) catches product-name reintroductions but does NOT
  fail on documented historical identifier strings.

**Alternatives considered**:

- **Rewrite identifiers in historical specs too** — confuses the
  archaeology (the spec says `sat_cli` but the code says `aivg_cli`?
  Why?). Worse.

---

## R-7. Hermes-plugin identifiers — exact list of preserved names

**Decision**: The following identifiers are **frozen** and not
renamed by this feature. They identify the **Hermes agent-platform
plugin**, not the product (constitution v2.0.0 Principle IV).

```text
src/aivg_core/platforms/hermes/             # folder
src/aivg_core/platforms/hermes/bridge.py    # the bridge module
src/aivg_core/platforms/hermes/textseg.py
src/aivg_core/platforms/hermes/__init__.py  # exports PLATFORM
skills/hermes-agent/                         # folder
skills/hermes-agent/SKILL.md                 # the Hermes skill
~/.hermes/config.yaml                        # Hermes-plugin config (read by plugin)
~/.hermes/.env                               # Hermes-plugin secrets
~/.hermes/logs/gateway.log                   # Hermes-plugin log destination
PLATFORM.name = "hermes"                     # the plugin's stable id
```

Per the rebrand allow-list (R-4) and FR-014, the lint MUST NOT
treat these as offending references. The product-name regex doesn't
match them (they say "hermes", not "Hermes Voice"), so no allow-
list entry is needed for the lint; FR-014 just ensures we don't
accidentally include them in a rename sweep.

**Rationale**:

- FR-014 + SC-007: Hermes-plugin identifiers stay; constitution v2.0.0
  Principle IV makes Hermes the v1 plugin name.

---

## R-8. Order of operations — single coordinated PR

**Decision**: Ship this feature as **one PR** with the steps below in
dependency order. Splitting into multiple PRs creates a transition
window where the lint either doesn't exist or fails.

1. Create `src/aivg_core/` (`git mv src/satellite_core/* src/aivg_core/`).
   Add `aivg_core/__init__.py` with the AIVG-aware preface.
2. Create `src/aivg_cli/` (`git mv src/sat_cli/* src/aivg_cli/`).
3. Add `aivg_core/persistence.py::migrate_legacy_data_dir()` and wire it.
4. Add `pyproject.toml` entries: rename project name to `aivg-core`,
   add `aivg` script, keep `sat-cli` legacy script, add `aivg_core`
   and `aivg_cli` to packages.find.
5. Replace `src/satellite_core/__init__.py` with the cached
   DeprecationWarning shim (R-1).
6. Replace `src/sat_cli/__init__.py` and `src/sat_cli/cli.py` with
   the legacy-app dispatch (R-2).
7. Update tests to import from `aivg_core` / `aivg_cli` (the existing
   imports still work via shim, but the canonical state of tests is
   on the new names).
8. Write `tests/unit/test_compat_shim.py`,
   `tests/unit/test_persistence_migration.py`,
   `tests/unit/test_no_legacy_branding.py` (the lint).
9. Write `docs/rebrand-allow-list.md`.
10. Sweep product-name prose in README, docs/, all specs (FR-001 /
    FR-002), CLI tagline, agent-skill descriptions, REST API
    `info.title`.
11. Amend the constitution PATCH (R-5).
12. Run the lint; allow-list adjustments until green.
13. Final test sweep — full `pytest -q` green (including the new
    lint).

**Rationale**:

- Steps 1–6 are mechanical and isolated; if any step breaks tests,
  the previous step's commit is a clean revert point.
- The lint (step 8) is the gate that proves the sweep in step 10 is
  complete.
- Constitution amendment (step 11) lands after the codebase is
  AIVG-named, so the constitution PATCH cannot drift from the code.

**Alternatives considered**:

- **Multi-PR rollout** — creates a window where the lint either
  silently passes (allow-list too broad) or fails noisily (allow-list
  too narrow). One-shot is cleaner.

---

## Open questions deferred to `/speckit-tasks`

None. The only deferred items are choices `tasks.md` will codify:

- Whether to split tests/* import-path updates into one bulk task or
  per-test-file tasks (style; pick bulk).
- Whether to refresh `clients/electron-test/README.md` in the same
  sweep or call it out separately (style; include in the sweep).
