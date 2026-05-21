# Implementation Plan: AIVG PyPI distribution

**Branch**: `018-aivg-pypi-distribution` · **Date**: 2026-05-21 · **Spec**: [spec.md](./spec.md)

## Summary

Publish `aivg` to PyPI so a single `pip install aivg` into a
Hermes virtualenv lands the AIVG satellite gateway + `aivg` CLI +
the `aivg-satellite` entry-point plugin Hermes auto-discovers. Replaces
today's only install path ("clone the repo, run `pip install -e .`")
with the standard Python-packaging workflow. The narrowed-scope rename
in feature 019 means the first published release advertises the
canonical post-019 internal names rather than the pre-019 ones.

**Versioning baseline** (per Clarifications Q1+Q2+Q3): the first PyPI
release is `0.2.0` across all three release axes — the package version
in `pyproject.toml`, the wire-contract version in
`aivg --contract-version`, and the `@aivg/sat-sdk` npm version. Every
pre-018 package version (`0.1.0` → ... → `0.3.1`) is treated as
internal pre-publication history.

Three prioritized stories:

- **P1** — fresh operator runs `pip install aivg` into a Hermes
  venv, the `aivg` binary lands on `bin/`, the entry-point plugin
  registers, a voice turn completes against an unchanged satellite
  client.
- **P2** — maintainer pre-flights every release via TestPyPI before
  promoting the **same artifact bytes** to real PyPI (immutability +
  blast-radius reduction).
- **P3** — CI auto-publishes on `git tag` push via PyPI Trusted
  Publishing (OIDC, no long-lived tokens on a developer laptop).

Open-question check at plan time: the four-name candidate set
(`aivg-core`, `aivg`, `aivg-satellite`, `aivg-gateway`) was ALL
available on PyPI (verified via HTTP 404 from the JSON API).
Clarifications Q2 locked the canonical choice as **`aivg`** —
short, matches the CLI binary and the product name, no `-core`
suffix to imply a multi-package ecosystem. The repo lacks a
top-level `LICENSE` file today (FR-009 in the spec makes adding one
binding); MIT is the choice matching the existing
`sdks/typescript/LICENSE`.

## Technical Context

**Language/Version**: Python 3.11+ (matches the existing `aivg_core`
runtime baseline). Pure-Python package; no native code of our own.

**Primary Dependencies**:

- `uv` (already installed at `~/.local/bin/uv 0.11.12`) — builds and
  publishes the package. `uv build` produces sdist + pure-Python
  wheel; `uv publish` uploads via PyPI Trusted Publishing OIDC.
  No `build` / `twine` / `setuptools_scm` adds needed.
- All `aivg` runtime deps already declared in `pyproject.toml`
  (aiortc, aiohttp, av, typer, rich, PyYAML, aioesphomeapi,
  noiseprotocol, chacha20poly1305-reuseable). PyPI resolves them
  for users; nothing new added by 018.
- GitHub Actions (the cloudomate org's existing CI surface; repo at
  `git@github.com:cloudomate/aivg.git`) — runs the build → TestPyPI →
  smoke → PyPI workflow on tag push. Uses Trusted Publishing OIDC
  configured on PyPI per project.

**Storage**: None new on disk. PyPI itself stores the published
artifacts (immutable per version per index). The repo gains a
`LICENSE` file and a `.github/workflows/release.yml` (the CI
workflow file).

**Testing**: pytest (existing harness). New tests:

- `tests/contract/test_pypi_metadata.py` — assert
  `pyproject.toml` declares every binding PyPI field (license,
  authors, urls, description, classifiers, readme reference).
  Pure-static, runs in the existing CI.
- `tests/integration/test_install_from_built_wheel.py` — locally
  build the wheel, install it into a fresh throwaway venv,
  assert `aivg --version` works and reports the same version
  string as `pyproject.toml`. Smoke test that catches packaging
  drift (missing files, broken entry points) BEFORE the wheel
  ever leaves the repo.

**Target Platform**: PyPI installer hosts on Linux x86_64, Linux
aarch64, macOS arm64, macOS x86_64 — the intersection of platforms
for which our transitive native deps (`aiortc`, `av`) publish
upstream wheels. Windows is NOT a target (matches AIVG's existing
target-platform note in feature 017).

**Project Type**: Library / service component distribution. Adds
packaging metadata + release tooling; touches no runtime code paths.

**Performance Goals**:

- Install of a fresh `pip install aivg` in a clean Python 3.11
  venv completes in under 60 s on a typical broadband connection
  (SC-001).
- Tag-push → real-PyPI release in under 10 minutes wall-clock end-to-end
  via CI (SC-002).
- Maintainer-driven manual release runbook completes in under 15
  minutes wall-clock (SC-007).
- Published wheel size under 5 MB (SC-004).

**Constraints**:

- Wire-surface invariance: 018 publishes the SAME runtime that an
  editable install of the same tag produces. No code changes ride
  along with the packaging change (SC-006 / FR-010 byte-equivalence
  gate).
- PyPI version immutability: every published version is permanent.
  Test on TestPyPI first (FR-008); promote same artifact bytes
  (SC-008); never re-upload over a yanked version.
- Trusted Publishing only: NO long-lived PyPI API tokens checked in,
  pasted into CI secrets, or stored on maintainer laptops
  (FR-012). OIDC via GitHub Actions is the canonical credential
  path.
- Maintainability bar: the release runbook fits on one page and a
  single maintainer can execute it end-to-end without referring to
  external docs (SC-006).

**Scale/Scope**: 4 source-tree additions (LICENSE file,
pyproject.toml metadata additions, README PyPI-rendered top
section, `.github/workflows/release.yml`). Zero changes to any
file under `src/`. ~150 LoC across the four artifacts plus
~80 LoC of tests.

## Constitution Check

Evaluated against AIVG Constitution **v2.0.1**
(`.specify/memory/constitution.md`).

### I. Thin Satellite, Gateway-Owned Intelligence (NON-NEGOTIABLE) — ✅ PASS

018 ships the same `aivg_core` package contents that already exist
in the repo. It introduces no STT, TTS, agent-loop, or endpointing
code anywhere. The change is purely about distribution mechanics:
how the same code reaches an operator's host. Principle I's
"STT/TTS reached only through the active platform's provider
interfaces" rule is unaffected — the post-018 install puts the
exact same code on disk that a pre-018 editable install would.

### II. Generic Four-Plane Contract — ✅ PASS

The four-plane wire contract is preserved trivially. 018 changes
no REST endpoint, no WS frame shape, no config key, no env var, no
contract version field. SC-006 in spec.md binds "post-PyPI install
behaves byte-equivalently to the same git-tag editable install,"
which IS Principle II's rule applied to the distribution layer.

### III. Separate Control and Voice Connections — ✅ PASS

No transport change. 018 doesn't touch the control WS, the
WebRTC signaling site, the ESPHome native API transport (feature
017), or any port assignment. The Principle III deviation already
documented in feature 017 (ESPHome's single-TCP-connection
upstream protocol) carries through unchanged.

### IV. Reuse the Upstream Agent Platform, Don't Rebuild — ✅ PASS

The Hermes plugin entry point (renamed in 019 to `aivg_satellite`)
is what the PyPI-installed package registers via Hermes's
own `ctx.register_platform`. 018 publishes the post-019 canonical
naming on its first release — operators see `✓ aivg_satellite
connected` immediately. ZERO modifications to any file under
`src/aivg_core/platforms/`. The `AgentPlatform`, `MediaTransport`,
and `SetupCapability` Protocol surfaces are untouched.

### V. Research-Backed, Constraint-Driven Decisions — ✅ PASS

Seven ADRs in [research.md](./research.md) carry the binding
research:

- **R-1**: `uv build` vs. `python -m build` (already-installed `uv`
  is the modern, single-binary choice).
- **R-2**: PyPI Trusted Publishing setup steps (OIDC config on
  PyPI per project; CI workflow file shape).
- **R-3**: `pyproject.toml` metadata completion (license, authors,
  urls, classifiers, readme).
- **R-4**: `LICENSE` file content (MIT, matching
  `sdks/typescript/LICENSE`).
- **R-5**: wheel inventory verification (must include source +
  pyproject metadata; must NOT include tests, fixtures, deploy/,
  specs/).
- **R-6**: TestPyPI workflow shape (separate index, separate
  Trusted Publishing config, smoke install in a throwaway venv).
- **R-7**: release runbook automation level for v1 (manual runbook
  + CI workflow that automates it; story 3 binding gate).

Principle V's "load-test before declared shipped" rule applies via
the locally-built-wheel install test in
`tests/integration/test_install_from_built_wheel.py` (T011 in
tasks). The runbook's TestPyPI smoke step exercises a real
clean-venv install before any real PyPI upload.

### Overall Gate Result

**PASS** on all five principles, no exceptions, no complexity
tracking entry needed. 018 is a pure packaging/distribution change
that ships the post-019 codebase as-is to PyPI; the four-plane
contract, the AgentPlatform seam, and every wire surface ride
through invariant.

### Post-Design Re-Check (after Phase 1)

After producing [research.md](./research.md),
[data-model.md](./data-model.md),
[contracts/pypi-release-contract.md](./contracts/pypi-release-contract.md),
and [quickstart.md](./quickstart.md), the gates are re-evaluated:

- **I. Thin Satellite** — unchanged. Phase 1 added no
  STT/TTS/agent/endpointing code.
- **II. Generic Four-Plane Contract** — strengthened. The
  contract document binds the post-install behavior byte-equivalent
  to the editable install at the same tag — a literal Principle II
  rule application at the distribution layer.
- **III. Separate Control/Voice Connections** — unchanged.
- **IV. Reuse Upstream Agent Platform** — unchanged.
- **V. Research-Backed Decisions** — R-1..R-7 all have explicit
  rationale + rejected alternatives.

**PASS — no new violations introduced by Phase 1 design.**

## Project Structure

### Documentation (this feature)

```text
specs/018-aivg-pypi-distribution/
├── plan.md                    # This file (/speckit-plan output)
├── research.md                # Phase 0 — 7 ADRs (R-1..R-7)
├── data-model.md              # Phase 1 — Release Artifact + Manifest + Workflow
├── quickstart.md              # Phase 1 — one-page release runbook
├── contracts/
│   └── pypi-release-contract.md  # Phase 1 — binding wheel/sdist shape + metadata
└── tasks.md                   # Phase 2 — generated by /speckit-tasks
```

### Source Code (repository root)

```text
LICENSE                                    # NEW — MIT, matches sdks/typescript/LICENSE.
                                            # FR-009 binding requirement.

pyproject.toml                              # MODIFIED — add:
                                            #   - [project] license = {text = "MIT"}
                                            #   - [project] authors = [...]
                                            #   - [project] maintainers = [...]
                                            #   - [project] readme = "README.md"
                                            #   - [project.urls] Repository, Issues, Changelog
                                            #   - [project] classifiers = [
                                            #       "Programming Language :: Python :: 3.11",
                                            #       "Programming Language :: Python :: 3.12",
                                            #       "License :: OSI Approved :: MIT License",
                                            #       "Operating System :: POSIX :: Linux",
                                            #       "Operating System :: MacOS",
                                            #       "Development Status :: 4 - Beta",
                                            #       ...
                                            #     ]

README.md                                   # MODIFIED — add a top-of-file PyPI-rendered
                                            # section per FR-014 surfacing:
                                            #   - supported Python versions
                                            #   - supported OS targets
                                            #   - "install into the Hermes venv, not a
                                            #      fresh one" call-out
                                            #   - repo link
                                            # (Body content unchanged; just an intro block.)

.github/workflows/release.yml               # NEW — CI release workflow (US3 binding):
                                            #   - on: push tags `v*.*.*`
                                            #   - uv build → sdist + wheel
                                            #   - uv publish --publish-url
                                            #       https://test.pypi.org/legacy/
                                            #     (Trusted Publishing OIDC)
                                            #   - smoke step: install from TestPyPI in
                                            #     a clean venv, run `aivg --version`
                                            #     and `aivg --contract-version`
                                            #   - uv publish (real PyPI) — same OIDC
                                            #   - tag remains intact on failure (FR-015)

tests/
├── contract/
│   └── test_pypi_metadata.py               # NEW (FR-009 binding) — pyproject.toml
│                                           #   has every required PyPI field;
│                                           #   pure-static lint
└── integration/
    └── test_install_from_built_wheel.py   # NEW (FR-010 / SC-006) — uv build,
                                            #   install into throwaway venv,
                                            #   assert `aivg --version` works,
                                            #   assert version string matches
                                            #   pyproject.toml

scripts/                                   # POSSIBLY MODIFIED — if a release helper
                                            # script lands (e.g. `scripts/release.sh`)
                                            # it goes here. Optional; the runbook in
                                            # quickstart.md is the authoritative
                                            # surface either way.

# (Every file under src/aivg_core/, src/aivg_cli/, sdks/, clients/: UNCHANGED.)
```

**Structure Decision**:

018 is **strictly additive** in source structure. No new modules
in `src/`; no test fixtures moved; no `scripts/` rewrites. Four
top-level additions (LICENSE, README PyPI section, CI workflow
file, two test files) plus the `pyproject.toml` metadata
completion.

1. **`LICENSE` at repo root** is the standard location every
   build backend looks for. Setuptools auto-includes a top-level
   `LICENSE` in the wheel's `.dist-info/` without further config.
2. **`pyproject.toml` metadata completion** is the single PR-worthy
   diff that publishing requires. Every field name is locked by
   PEP 621; no creative typing.
3. **`.github/workflows/release.yml`** uses GitHub's standard
   workflow YAML — no AIVG-specific DSL.
4. **No new top-level packaging directory** (e.g. `packaging/`,
   `build/`, `dist/`). `dist/` is generated by `uv build` and
   `.gitignore`'d.
5. **No scripts/ wrapper**. The runbook in
   [quickstart.md](./quickstart.md) is the authoritative manual
   path; the CI workflow file is the automated counterpart. A
   third shell-wrapper layer would duplicate them.

## Complexity Tracking

No constitutional violations. No complexity-tracking entries
needed. The following choices were made and the rejected
alternatives are documented in [research.md](./research.md):

| Choice | Why | Alternative rejected |
| --- | --- | --- |
| `uv build` + `uv publish` | Single binary already installed; supports OIDC publishing; obviates `build` + `twine` + their transitive deps | `python -m build` + `twine`: rejected because adds two new dev deps for what `uv` already does. |
| PyPI Trusted Publishing via GitHub Actions OIDC | No long-lived tokens; audit trail in CI logs; canonical 2026 best practice | Long-lived API tokens in CI secrets: rejected because token rotation/leakage risk is real for a public PyPI account. |
| Single wheel + sdist, no separate `aivg-cli` package | One install command for users; one wheel to maintain | Split into `aivg` + `aivg-cli` + `aivg-satellite-plugin`: rejected because users only ever install the bundle; three wheels = three release coordinations. (Spec Clarification Q1) |
| MIT license | Matches existing `sdks/typescript/LICENSE`; widely accepted; no permission complexity | Apache 2.0 / BSD: defensible but introduces a license-mismatch between Python and TypeScript surfaces. Single license across the project is cleaner. |
| Manual runbook + CI workflow (both shipped) | Story 2 (TestPyPI pre-flight) needs the runbook for the operator-driven path; story 3 (CI auto-publish) needs the workflow file. Both are first-class. | CI-only: rejected because operators need the manual path for hotfixes / debugging a failed CI run. Manual-only: rejected because story 3 specifically demands "no laptop in the release path." |
| TestPyPI as the staging area (no custom artifact server) | TestPyPI is free, infinitely reproducible, and operates on the same protocol as real PyPI. Catches every packaging mistake. | Artifactory / S3-hosted pypi-compatible server: rejected because requires infra + auth setup for what TestPyPI gives free. |
| Same artifact bytes between TestPyPI and PyPI (no rebuild) | SC-008 binding — staging-vs-prod drift is a real packaging anti-pattern (the bytes you verified are not the bytes you ship) | Separate build for each upload: rejected because timestamps + file ordering in the sdist would produce different bytes, defeating the "promotion is a re-upload" promise. |
