# Phase 1 — Data Model

**Feature**: 018-aivg-pypi-distribution · **Date**: 2026-05-21

Feature 018 introduces no persistent runtime records, no wire
fields, no new public Python types. The "data" being modeled is
the **release artifact pair** that gets published, the
**package manifest** that drives its build, and the **release
workflow** that produces and ships it.

---

## 1. Release Artifact (sdist + wheel pair)

### What it is

A single immutable unit of distribution, identified by version
string. One Release Artifact = one `.tar.gz` sdist + one
`.whl` wheel built from the same tagged commit.

### Fields (per artifact)

| Field | Source | Example |
|---|---|---|
| Version | `pyproject.toml` `[project] version` | `0.2.0` (first PyPI release per Clarifications) |
| Sdist filename | Build tool convention | `aivg-0.2.0.tar.gz` |
| Wheel filename | Build tool convention | `aivg-0.2.0-py3-none-any.whl` |
| Built-from SHA | Git tag pointing at the build commit | `f1b24ce…` |
| Built-by | CI workflow run (or maintainer + machine) | `cloudomate/aivg-release.yml#42` |
| Upload destination | TestPyPI URL or PyPI URL | `https://test.pypi.org/legacy/` |
| Upload timestamp | PyPI's record | `2026-MM-DDTHH:MM:SSZ` |

Sdist + wheel together are the artifact pair — they ship as a
unit, are smoke-tested as a unit, and are promoted as a unit.

### Invariants

- **One version per artifact**. A given version string maps to
  exactly one (sdist, wheel) pair, ever. Re-running the build with
  the same `pyproject.toml` version on a different commit MUST
  fail to upload (PyPI rejects re-uploads).
- **Byte-equivalence across staging and prod**. The wheel + sdist
  bytes uploaded to TestPyPI MUST be byte-identical to the bytes
  uploaded to real PyPI for the same version. No rebuild between
  stages (SC-008 binding).
- **Reproducibility from the tag**. Anyone with the git tag SHA
  can run `uv build` at that tag and produce the same (sdist,
  wheel) names + the same wheel contents (modulo build-time
  timestamps inside the sdist, which are inherent to the
  archive format).
- **Wheel is pure-Python** (`py3-none-any`). AIVG itself has no
  native code; transitive native deps (`aiortc`, `av`) come from
  their own per-platform wheels resolved at install time.
- **Wheel size ≤ 5 MB**. Sanity guard against accidental bundling
  of `tests/`, `specs/`, vendor binaries, etc. (SC-004).

### State transitions

```text
DRAFT (just built)
    └─ uv build → dist/aivg-X.Y.Z.{tar.gz,whl}

STAGED (uploaded to TestPyPI; same bytes)
    └─ uv publish --publish-url https://test.pypi.org/legacy/

VERIFIED (smoke install in clean venv passed)
    └─ pip install -i https://test.pypi.org/simple/ aivg==X.Y.Z
       && aivg --version       (matches X.Y.Z)
       && aivg --contract-version  (returns 0.2.0 for the first PyPI release)

PUBLISHED (uploaded to real PyPI; same bytes again)
    └─ uv publish  (no --publish-url; targets pypi.org by default)

LIVE (resolvable by `pip install aivg==X.Y.Z` worldwide)

[Terminal state. Cannot revert. Yank hides from new installs but
 does not delete or free the version number.]
```

The state transitions are strictly forward; nothing in 018 ever
needs the artifact to go back a step. A failure at any step
between DRAFT and PUBLISHED leaves the artifact at its last
successful state — the maintainer fixes the issue, bumps the
version, and starts over with a fresh DRAFT.

---

## 2. Package Manifest (`pyproject.toml`)

### What it is

The single authoritative file that drives every release. Every
PyPI-rendered field, every Python dependency, every entry-point,
the build backend, the package version — all traced to this file.

### Fields (post-018)

These fields land via the FR-009 implementation. Asterisk indicates
fields already present pre-018.

| Field | Pre-018 | Post-018 |
|---|---|---|
| `[project] name` | `"aivg-core"` (placeholder) | **`"aivg"`** (Clarification Q2) |
| `[project] version` | `"0.3.1"` (internal pre-PyPI) | **`"0.2.0"`** at first PyPI release (Clarification Q1) |
| `[project] description` | ✓ present | unchanged |
| `[project] requires-python` | ✓ `">=3.11"` | unchanged |
| `[project] dependencies` | ✓ present (10 deps) | unchanged |
| `[project] optional-dependencies` | ✓ `dev`, `ble` | unchanged |
| `[project] license` | absent | `{text = "MIT"}` |
| `[project] readme` | absent | `"README.md"` |
| `[project] authors` | absent | `[{name = "Cloudomate", email = "..."}]` |
| `[project] maintainers` | absent | added |
| `[project] keywords` | absent | added |
| `[project] classifiers` | absent | added (~10 classifiers, see R-3) |
| `[project.urls]` | absent | Repository / Issues / Changelog / Documentation |
| `[project.scripts] aivg` | ✓ `"aivg_cli.cli:app"` | unchanged |
| `[project.entry-points."hermes_agent.plugins"]` | ✓ `aivg-satellite = ...` | unchanged |
| `[build-system]` | ✓ setuptools + wheel | unchanged |
| `[tool.setuptools.packages.find]` | ✓ `include = ["aivg_core*", "aivg_cli*"]` | unchanged |

### Invariants

- **Single source of truth**. The version string returned by
  `aivg --version` MUST trace back to `[project] version`.
  Today's CLI hardcodes `version = "0.2.0"` inside
  `aivg_cli/cli.py` — that's a pre-existing drift (out of scope
  for 018) but the package version (which is what PyPI sees) is
  always `pyproject.toml`'s value.
- **One license declaration**. The repo's top-level `LICENSE` file
  (added by 018) AND `pyproject.toml`'s `[project] license`
  string MUST agree.
- **Entry-point name stability**. `aivg-satellite` (the Hermes
  entry-point manifest name) is the operator-typed identifier;
  changing it would break every existing `plugins.enabled:`
  config. 018 MUST NOT rename it.
- **Classifier consistency**. The Python-version classifiers
  (`Programming Language :: Python :: 3.11/3.12`) MUST be a
  subset of what `requires-python` accepts.

---

## 3. Release Workflow

### What it is

The ordered sequence that takes a tagged commit and produces a
PyPI-resolvable version of `aivg`. Shipped in two forms
(R-7): the manual runbook in [quickstart.md](./quickstart.md)
and the CI workflow at `.github/workflows/release.yml`.

### Steps (canonical)

```text
1. Version bump        — edit pyproject.toml [project] version
2. CHANGELOG entry     — add [X.Y.Z] section to CHANGELOG.md
3. Local validation    — pytest tests/unit/ tests/contract/
                          (must pass before tag)
4. Commit + tag        — git commit; git tag -a vX.Y.Z -m "..."
5. Build               — uv build
                          (produces dist/aivg-X.Y.Z.{tar.gz,whl})
6. Wheel inspection    — unzip -l dist/aivg-*.whl
                          (verify no tests/, specs/, etc.; size < 5 MB)
7. TestPyPI upload     — uv publish --publish-url https://test.pypi.org/legacy/
8. TestPyPI smoke      — uv venv /tmp/smoke; uv pip install --python /tmp/smoke
                            -i https://test.pypi.org/simple/ aivg==X.Y.Z
                          /tmp/smoke/bin/aivg --version
                          (must succeed; version must match X.Y.Z)
9. Real PyPI upload    — uv publish  (SAME artifact bytes; no rebuild)
10. Tag push           — git push origin vX.Y.Z
                          (the tag itself is the public record of
                           which commit produced this release)
11. Post-release       — `pip install aivg==X.Y.Z` from a clean
                          venv on a clean host (verification of
                          worldwide resolvability)
```

### Invariants

- **Steps 5–9 use the SAME artifact bytes**. No `uv build` between
  TestPyPI and PyPI. The CI workflow MUST cache the `dist/`
  directory between the build job and the two publish jobs.
- **Step 4 (tag) MUST precede step 5 (build)**. The git tag is
  the immutable reference the artifact ties back to. If the
  build fails after the tag exists, the tag stays — the
  maintainer bumps the version + retags rather than retroactively
  changing what the existing tag points at.
- **Steps 1–3 (version, CHANGELOG, local tests) are the
  pre-tag gates**. If any of them fails, no tag gets created;
  no release is possible.
- **Step 8 (smoke) is the binding pre-promotion gate**. If smoke
  fails, step 9 (real PyPI upload) MUST NOT run. CI surfaces the
  failure; maintainer diagnoses + bumps + retags.

### State transitions

```text
PLAN          (idea of a release)
    ↓ steps 1–3
PREPARED      (version bumped, CHANGELOG entry written, tests pass)
    ↓ step 4
TAGGED        (immutable git reference exists for this release)
    ↓ steps 5–6
BUILT         (dist/aivg-X.Y.Z.* exists on local disk or in CI workspace)
    ↓ step 7
STAGED        (TestPyPI has the artifact; same bytes)
    ↓ step 8
VERIFIED      (smoke install in clean venv passed)
    ↓ step 9
PUBLISHED     (real PyPI has the artifact; same bytes again)
    ↓ steps 10–11
SHIPPED       (tag pushed; `pip install aivg==X.Y.Z` works worldwide)
```

A failure at any post-TAGGED state leaves the tag intact (per
FR-015 in spec.md). The maintainer can investigate, fix, bump
version, and re-PLAN — but they cannot reuse the failed version
number for a different commit.

---

## Out of scope (positive enumeration)

To make the "no runtime change" promise auditable, 018 explicitly
does NOT introduce, modify, or remove:

- Any file under `src/aivg_core/`
- Any file under `src/aivg_cli/`
- Any wire surface (REST paths, WS frames, config keys, env vars)
- The contract version `aivg --contract-version` reports
- The `aivg-satellite` PyPI entry-point manifest name (which IS the
  operator-visible identifier in `plugins.enabled:`)
- The `@aivg/sat-sdk` TypeScript SDK (separate distribution channel,
  separate release cadence; npm-side packaging is out of scope)
- The C++ SDK (feature 016, not yet started — its distribution
  story is its own feature)
- Any test under `tests/` other than the two new tests this feature
  adds (`test_pypi_metadata.py`, `test_install_from_built_wheel.py`)
- The companion `cloudomate/aivg-devices` repo (ESPHome YAML
  examples; lives outside `aivg`'s distribution scope)

This enumeration is the literal data model of "what didn't
change," and the quickstart's smoke install verifies it.
