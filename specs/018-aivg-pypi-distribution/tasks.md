---
description: "Task list for feature 018 — AIVG PyPI distribution"
---

# Tasks: AIVG PyPI distribution

**Input**: Design documents from [/specs/018-aivg-pypi-distribution/](./)
**Prerequisites**: [plan.md](./plan.md), [spec.md](./spec.md), [research.md](./research.md), [data-model.md](./data-model.md), [contracts/pypi-release-contract.md](./contracts/pypi-release-contract.md), [quickstart.md](./quickstart.md)

**Tests**: Two new test files are mandatory (per plan.md "Testing" section + FR-009 + SC-006). They are the local gates that catch packaging mistakes BEFORE the wheel ever leaves the repo.

**Organization**: Tasks are grouped by user story. Stories US1 and US2 are both P1 in the spec — US1 is the in-repo "wheel builds + installs locally" work, US2 is the maintainer-driven first real PyPI publish. US3 is P3: the CI automation layer that takes the laptop out of every subsequent release.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies on incomplete tasks).
- **[Story]**: US1 / US2 / US3 for user-story tasks; absent for Setup / Foundational / Polish.
- **[OPERATOR]** in the description marks tasks that require a human (PyPI account setup, OIDC config, tagging + pushing). All other tasks are LLM-executable file edits or local-shell verifications.
- Every task names its target file or command.

## Path Conventions

Single-project layout:
- Repo-root files: `LICENSE`, `pyproject.toml`, `README.md`, `CHANGELOG.md`
- CI: `.github/workflows/release.yml`
- Tests: `tests/contract/`, `tests/integration/`

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Capture the plan-time verifications so the implementation has a known-good starting state and the polish phase has something to assert against.

- [X] T001 Re-confirm PyPI name availability: `curl -s -o /dev/null -w '%{http_code}\n' https://pypi.org/pypi/aivg/json` MUST return `404`. If it now returns `200`, abort the feature and replan with the fallback name chain (`aivg`, `aivg-satellite`, `aivg-gateway`). Recorded for the record in this task line; no file mutation.
- [X] T002 [P] Confirm dev toolchain present: `uv --version` returns ≥ `0.4.x`, `~/.hermes/hermes-agent/venv/bin/python --version` returns `3.11.x`, `git --version` succeeds. Operator action only if any check fails; do NOT install missing tools without confirming with the user.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Add the on-disk artifacts that every release path (manual and CI) reads. Until these land, neither story can ship.

**⚠️ CRITICAL**: No user-story work begins until T003 + T004 + T005 + T006 land.

- [X] T003 Create `LICENSE` at repo root with the MIT license text. Copy structurally from [sdks/typescript/LICENSE](../../sdks/typescript/LICENSE) (same wording: `MIT License / Copyright (c) 2026 Cloudomate / AIVG contributors`). Per [research.md § R-4](./research.md#r-4-license-file-content--mit-matching-the-typescript-sdk) — binding for FR-009.
- [X] T004 [P] Add `[project] license`, `readme`, `authors`, `maintainers`, `keywords`, `classifiers` keys to [pyproject.toml](../../pyproject.toml) per the field table in [research.md § R-3](./research.md#r-3-pyprojecttoml-metadata-completion). Insert immediately after the existing `dependencies` block; preserve every existing key verbatim.
- [X] T005 [P] Add `[project.urls]` section to [pyproject.toml](../../pyproject.toml) with `Repository`, `Issues`, `Changelog`, `Documentation` keys per [research.md § R-3](./research.md#r-3-pyprojecttoml-metadata-completion). Use `https://github.com/cloudomate/aivg` as the base URL.
- [X] T006 [P] Add a PyPI-rendered intro section to the top of [README.md](../../README.md), immediately under the `# AIVG — AI Voice Gateway` title. Surface (per FR-014): a one-line `pip install aivg` quick-install, the supported Python versions (3.11+), the supported OS targets (Linux x86_64/aarch64, macOS arm64/x86_64), and a prominent "install into the Hermes venv, NOT a fresh venv" call-out (the gotcha that caught us on the 2026-05-21 deploy). Keep the existing body content unchanged below the intro.

### Phase 2.5: Version + name cascade (per Spec Clarifications Q1, Q2, Q3)

These tasks land the version/name flips locked by Clarifications. They're foundational because every downstream task (build, install, smoke) assumes the post-cascade state. All four sub-tasks touch different files and can run in parallel.

- [X] T006a [P] Rename PyPI distribution + bump package version in [pyproject.toml](../../pyproject.toml): change `name = "aivg-core"` → `name = "aivg"` (Clarification Q2); change `version = "0.3.1"` → `version = "0.2.0"` (Clarification Q1 — first PyPI release is the public baseline at 0.2.0). The Python module name (`aivg_core`) is UNCHANGED; only the PyPI distribution name flips.
- [X] T006b [P] Update the gateway contract version in [src/aivg_cli/cli.py](../../src/aivg_cli/cli.py): change `CONTRACT_VERSION = "1.1.0"` → `CONTRACT_VERSION = "0.2.0"` (Clarification Q2 — wire-contract version aligns with the package version at the public-baseline boundary). The pre-PyPI `1.1.0` history (feature 017 additive ESPHome bump) is preserved in CHANGELOG.
- [X] T006c [P] Bump `@aivg/sat-sdk` to 0.2.0 per Clarification Q3 — MAJOR per 0.x npm semver convention:
  - Update [sdks/typescript/package.json](../../sdks/typescript/package.json) `version` from `"0.1.4"` → `"0.2.0"`.
  - Update the SDK source's `CONTRACT_VERSION` constant (in [sdks/typescript/src/control-plane.ts](../../sdks/typescript/src/control-plane.ts) or wherever the constant lives — grep `1\.1\.0` under `sdks/typescript/src/`) from `"1.1.0"` to `"0.2.0"`.
  - Rebuild SDK dist: `cd sdks/typescript && npm run build`.
  - Add a `[0.2.0] — YYYY-MM-DD` entry to [sdks/typescript/CHANGELOG.md](../../sdks/typescript/CHANGELOG.md) explaining the wire-contract reset.
- [X] T006d [P] Refresh the electron-test SDK pin per Clarification Q3 cascade: update [clients/electron-test/package.json](../../clients/electron-test/package.json) `@aivg/sat-sdk` dep from `"file:../../sdks/typescript"` (already file-linked — verify it stays file-linked); run `cd clients/electron-test && npm install` to refresh the lockfile against the new SDK 0.2.0 build.

**Checkpoint**: After T006d, run `~/.hermes/hermes-agent/venv/bin/python -c "import tomllib; tomllib.loads(open('pyproject.toml').read())"` — MUST parse without error AND show `name = "aivg"`, `version = "0.2.0"`. Run `cd sdks/typescript && npm test` — all 148 SDK tests still pass. Foundation ready; both user stories can proceed.

---

## Phase 3: User Story 1 — Wheel builds + installs into a clean venv (Priority: P1) 🎯 MVP

**Goal**: After this phase, a maintainer on their laptop can run `uv build` and produce a (sdist, wheel) pair that installs cleanly into a throwaway venv, registers the `aivg` binary on PATH, registers the `aivg-satellite` entry point Hermes auto-discovers, and reports `aivg --version` + `aivg --contract-version` correctly. Nothing's on PyPI yet — that's US2 — but every condition for a successful PyPI install is locally verifiable.

**Independent Test**: per [quickstart.md § 3 + § 4.2](./quickstart.md) (steps 3.1, 3.2, 4.2 against a LOCAL wheel rather than TestPyPI): `uv build` produces the artifact pair; wheel inventory clean (no `tests/`/`specs/`/etc.); wheel under 5 MB; entry-points file declares both `aivg` and `aivg-satellite`; throwaway-venv install works; `aivg --version` returns the bumped version. All in <2 minutes wall-clock from a clean working tree.

### Implementation tasks for US1

- [X] T007 [P] [US1] Create [tests/contract/test_pypi_metadata.py](../../tests/contract/test_pypi_metadata.py). Parse `pyproject.toml` via `tomllib`; assert presence of `[project] license`, `readme`, `authors`, `maintainers`, `keywords`, `classifiers`; assert `[project.urls]` has `Repository`, `Issues`, `Changelog`, `Documentation` keys; assert MIT classifier `"License :: OSI Approved :: MIT License"` and Python-version classifiers cover 3.11+. Pure-static, runs in <0.5s. Catches metadata drift on every CI run.
- [X] T008 [P] [US1] Create [tests/integration/test_install_from_built_wheel.py](../../tests/integration/test_install_from_built_wheel.py). The test:
  (a) shells out to `uv build --out-dir /tmp/aivg-018-build-test/dist/`;
  (b) creates a throwaway venv at `/tmp/aivg-018-build-test/venv/`;
  (c) `uv pip install --python /tmp/aivg-018-build-test/venv/bin/python /tmp/aivg-018-build-test/dist/aivg-*.whl`;
  (d) asserts `/tmp/aivg-018-build-test/venv/bin/aivg --version` exits 0;
  (e) asserts the version-string in the JSON envelope equals the `[project] version` in `pyproject.toml`;
  (f) asserts the wheel size (via `os.path.getsize()`) is < 5 MB (SC-004);
  (g) cleans up `/tmp/aivg-018-build-test/` at the end. Test is marked `@pytest.mark.integration` so it's skippable on environments without `uv`.
- [X] T009 [US1] Locally run `uv build` from repo root; verify `dist/` contains exactly `aivg-X.Y.Z-py3-none-any.whl` and `aivg-X.Y.Z.tar.gz` (no other files). Then run the inventory check from [quickstart.md § 3.1](./quickstart.md): `unzip -l dist/aivg-*.whl | grep -E "tests/|specs/|clients/|sdks/|deploy/|docs/|\.github/"` MUST return empty.
- [X] T010 [US1] Verify entry-points: `unzip -p dist/aivg-*.whl aivg-*.dist-info/entry_points.txt` MUST show BOTH `aivg = aivg_cli.cli:app` (under `[console_scripts]`) AND `aivg-satellite = aivg_core.platforms.hermes.plugin_entrypoint` (under `[hermes_agent.plugins]`).
- [X] T011 [US1] Run the new pytest from T008 and T007: `PYTHONPATH=src:tests ~/.hermes/hermes-agent/venv/bin/python -m pytest tests/contract/test_pypi_metadata.py tests/integration/test_install_from_built_wheel.py -v`. Both MUST pass.

**Checkpoint US1**: After T011, the wheel builds cleanly and installs cleanly into a throwaway venv. The MVP is locally provable. Nothing's been pushed to any index yet.

---

## Phase 4: User Story 2 — Maintainer pre-flights via TestPyPI, then promotes (Priority: P1)

**Goal**: After this phase, `aivg` exists on real PyPI at its first release version, and the canonical pre-flight workflow (TestPyPI → smoke → promote-same-bytes) has been exercised end-to-end at least once. The runbook in [quickstart.md](./quickstart.md) is no longer just documentation — it's been executed at least once and any docs gaps that exposure surfaced have been fixed.

**Independent Test**: per [quickstart.md § 4 + § 5 + § 7](./quickstart.md): TestPyPI page `https://test.pypi.org/project/aivg/X.Y.Z/` shows the upload; clean-venv install from TestPyPI succeeds and `aivg --version` returns X.Y.Z; same-bytes `uv publish` to real PyPI succeeds; `https://pypi.org/project/aivg/X.Y.Z/` resolves; clean-host smoke `pip install aivg==X.Y.Z` works from a different machine.

### Implementation tasks for US2

- [ ] T012 [US2] [OPERATOR] One-time PyPI + TestPyPI account setup per [quickstart.md § 0.1](./quickstart.md): create accounts at `https://pypi.org/account/register/` and `https://test.pypi.org/account/register/`; enable 2FA on both (PyPI requires it for uploads since 2024). Operator-only; no repo changes.
- [ ] T013 [US2] [OPERATOR] Bootstrap the PyPI project by uploading the first release manually (Trusted Publishing config requires the project to exist; first upload uses a per-account API token). Generate temporary tokens at `https://test.pypi.org/manage/account/token/` and `https://pypi.org/manage/account/token/`; export as `UV_PUBLISH_TOKEN` for the duration of the first upload only. Tokens are deleted from PyPI account settings immediately after the first upload — replaced by Trusted Publishing for all subsequent releases.
- [ ] T014 [US2] Execute the pre-tag preparation per [quickstart.md § 1](./quickstart.md): bump `pyproject.toml` `[project] version` to **`0.2.0`** (locked by Spec Clarification Q1 — first PyPI release is the public baseline at 0.2.0 across every release axis). Also bump `pyproject.toml` `[project] name` to **`aivg`** (Spec Clarification Q2). Update the source `CONTRACT_VERSION` constant in `aivg_cli/cli.py` from `"1.1.0"` to `"0.2.0"` (Spec Clarification Q2). Add a CHANGELOG entry: move existing pre-018 sections under a new "Pre-publication history" header and add a fresh `## [0.2.0] — YYYY-MM-DD — First public PyPI release` section. Run the test suite per § 1.4 + § 1.5; MUST pass.
- [ ] T015 [US2] Tag the release per [quickstart.md § 2](./quickstart.md): `git tag -a v0.2.0 -m "aivg 0.2.0 — first public PyPI release"`. The tag stays local until US2 succeeds end-to-end (per FR-015).
- [ ] T016 [US2] Build + inspect per [quickstart.md § 3](./quickstart.md): `rm -rf dist/ && uv build`; run the inventory + size + entry-points checks from § 3.1 + § 3.2.
- [ ] T017 [US2] Upload to TestPyPI per [quickstart.md § 4.1](./quickstart.md): `uv publish --publish-url https://test.pypi.org/legacy/`. Verify the TestPyPI project page renders correctly (license badge, classifiers, URLs sidebar populated per the contract in [contracts/pypi-release-contract.md § 4](./contracts/pypi-release-contract.md#4-pypi-metadata-rendered-listing)).
- [ ] T018 [US2] Smoke install from TestPyPI per [quickstart.md § 4.2](./quickstart.md): create the throwaway venv, install from TestPyPI with `--extra-index-url https://pypi.org/simple/` for dep resolution, run `aivg --version` (MUST match `0.2.0`) and `aivg --contract-version` (MUST return `0.2.0` — per Spec Clarification Q2, wire contract resets at first PyPI release).
- [ ] T019 [US2] Promote same artifact bytes to real PyPI per [quickstart.md § 5](./quickstart.md): `uv publish` (no `--publish-url`, defaults to pypi.org). Verify the project page resolves at `https://pypi.org/project/aivg/X.Y.Z/`. Run `sha256sum dist/aivg-X.Y.Z*` and confirm the digests match what TestPyPI AND real PyPI show on their respective project pages (the SC-008 byte-equivalence gate).
- [ ] T020 [US2] [OPERATOR] Push the tag per [quickstart.md § 6](./quickstart.md): `git push origin main vX.Y.Z`. The tag is now the public immutable record of which commit produced this release.
- [ ] T021 [US2] [OPERATOR] Worldwide-resolve smoke per [quickstart.md § 7](./quickstart.md) — on a DIFFERENT host (or a different venv on the same machine with no AIVG history): `uv venv /tmp/aivg-post-release-X.Y.Z && uv pip install --python /tmp/aivg-post-release-X.Y.Z/bin/python aivg==X.Y.Z`. Run `aivg --version` and `aivg --contract-version`; both MUST succeed. The binding "worldwide-resolvable" gate (SC-001).

**Checkpoint US2**: After T021, `aivg==X.Y.Z` is live on PyPI and the manual runbook has been exercised end-to-end. The release is shippable. Subsequent releases either repeat US2 manually OR (once US3 lands) push a tag and let CI handle it.

---

## Phase 5: User Story 3 — CI auto-publishes on `git push --tags` (Priority: P3)

**Goal**: After this phase, future releases require only the pre-tag preparation (T014's analog — version bump + CHANGELOG + tests pass + tag + push) from the maintainer. The build → TestPyPI → smoke → real PyPI → SAME-BYTES flow runs in CI via PyPI Trusted Publishing OIDC. No long-lived tokens anywhere; audit trail in GitHub Actions logs.

**Independent Test**: Push a fresh tag (e.g. `v0.2.1` after US2 has shipped `v0.2.0`). The CI workflow at `.github/workflows/release.yml` runs end-to-end within 10 minutes; `pip install aivg==0.2.1` resolves on real PyPI; no maintainer touched a terminal between `git push` and the release going live.

### Implementation tasks for US3

- [ ] T022 [US3] [OPERATOR] On `https://test.pypi.org/manage/project/aivg/settings/publishing/` (after T013 bootstrapped the TestPyPI project) AND on `https://pypi.org/manage/project/aivg/settings/publishing/` (after T019 bootstrapped the real PyPI project): add a Trusted Publisher per [research.md § R-2](./research.md#r-2-pypi-trusted-publishing-setup--github-actions-oidc). Settings: Owner=`cloudomate`, Repository=`aivg`, Workflow=`release.yml`, Environment name=`testpypi` (TestPyPI side) / `pypi` (real PyPI side).
- [ ] T023 [US3] [OPERATOR] On `https://github.com/cloudomate/aivg/settings/environments`: create two GitHub Actions environments named `testpypi` and `pypi`. Add deployment protection rules as appropriate (e.g. require a manual approval for `pypi` if the org wants a gate; leave open for `testpypi`).
- [X] T024 [US3] Create [.github/workflows/release.yml](../../.github/workflows/release.yml) with the structure described in [plan.md § Project Structure](./plan.md#source-code-repository-root). The workflow:
  - Triggers on `push` of tags matching `v*.*.*` (semver pattern).
  - Two jobs: `build` (produces dist/ via `uv build` + uploads as artifact) and `publish` (downloads the artifact, publishes to TestPyPI, smoke-installs, publishes to real PyPI).
  - Uses `permissions: id-token: write` for OIDC.
  - Uses `uv publish --publish-url https://test.pypi.org/legacy/` for TestPyPI and `uv publish` for real PyPI — Trusted Publishing means no token argument anywhere.
  - Smoke step between TestPyPI and real PyPI: `uv venv /tmp/smoke && uv pip install --python /tmp/smoke/bin/python -i https://test.pypi.org/simple/ --extra-index-url https://pypi.org/simple/ aivg==${{ github.ref_name#v }} && /tmp/smoke/bin/aivg --version`.
  - Real PyPI upload step gated on smoke success — if smoke fails the job halts BEFORE real PyPI upload (FR-008 / FR-015).
  - Workflow environment names match T023 (`testpypi` and `pypi`) so the per-environment OIDC token is correctly issued.
- [ ] T025 [US3] [OPERATOR] Trigger the workflow with a small follow-up release (e.g. bump pyproject.toml to `0.2.1` with a one-line CHANGELOG entry "ship CI release workflow"; commit; tag; push). Watch the workflow run at `https://github.com/cloudomate/aivg/actions`. End-to-end in under 10 minutes (SC-002).
- [ ] T026 [US3] Verify post-CI release: `uv pip install --python /tmp/aivg-ci-test/bin/python aivg==0.2.1` from a clean throwaway venv on a clean host. `aivg --version` MUST return `0.2.1`; `aivg --contract-version` MUST return `0.2.0` (the wire contract is independent of the package version; a 0.2.0 → 0.2.1 PATCH bump of the package does NOT change the wire contract).

**Checkpoint US3**: After T026, every subsequent release is `git tag vX.Y.Z && git push origin vX.Y.Z` and walk away. The CI workflow is the canonical release path; the manual runbook is preserved as the recovery / hotfix path.

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: Lock in the test-suite regression, the README polish, and the post-018 follow-up tracking.

- [X] T027 Full regression suite per [quickstart.md § 1.4](./quickstart.md): `PYTHONPATH=src:tests ~/.hermes/hermes-agent/venv/bin/python -m pytest tests/unit/ tests/contract/ -q --tb=line`. Expected: `294 + N passing` where `N` is the count of new tests added in T007 (test_pypi_metadata.py: ~3 tests) — target around `297`. Zero new failures introduced by 018.
- [ ] T028 [P] Verify the published PyPI listing matches the contract in [contracts/pypi-release-contract.md § 4](./contracts/pypi-release-contract.md#4-pypi-metadata-rendered-listing). Visit `https://pypi.org/project/aivg/X.Y.Z/`; confirm: license badge visible, all four sidebar links populated, Python-version requirement displayed, OS classifiers listed, keywords appear, long description renders the README correctly.
- [X] T029 [P] Update the [README.md](../../README.md) Quickstart section to lead with the PyPI install command rather than the `pip install -e .` (editable) command. The editable install stays as a "contributor" sub-section since contributors still want it. Operators get the simpler `pip install aivg` as the canonical path.
- [ ] T030 Verify the [CHANGELOG.md](../../CHANGELOG.md) entries from T014 + T025 are present and correctly dated. Confirm both releases (the initial US2 release + the US3 ship-the-CI follow-up) have CHANGELOG sections.
- [X] T031 [P] Update the SPECKIT marker in [CLAUDE.md](../../CLAUDE.md) to mark feature 018 as `[shipped — first PyPI release X.Y.Z + CI auto-publish workflow live]` once both releases are out.

---

## Dependencies & Story Completion Order

```text
Phase 1 Setup (T001, T002)
   │
   ▼
Phase 2 Foundational (T003 LICENSE → T004/T005/T006 [parallel])
   │
   ├──▶ Phase 3 US1: local-build-works (T007–T011)
   │       │
   │       └──▶ Phase 4 US2: manual-PyPI-release (T012–T021)
   │               │
   │               └──▶ Phase 5 US3: CI-auto-publish (T022–T026)
   │
   ▼
Phase 6 Polish (T027–T031) — runs after both US2 and US3 land
```

- **US1 unblocks US2.** Until the wheel builds cleanly locally (US1), the manual runbook (US2) has nothing to upload.
- **US2 unblocks US3.** Trusted Publisher config (T022) requires the PyPI project to exist, which requires the first manual upload (T013 + T017 + T019 in US2).
- **US3 ships the automation FOR FUTURE RELEASES.** It doesn't make the current US2 release "more done"; it makes the next release (and every subsequent release) easier.

---

## Parallel Execution Examples

### Within Phase 2 (Foundational)

After T003 (LICENSE file) lands:

```text
T004 [P] (pyproject.toml [project] keys)
T005 [P] (pyproject.toml [project.urls])
T006 [P] (README.md intro section)
```

All three touch different files; can land concurrently.

### Within Phase 3 (US1)

```text
T007 [P] (test_pypi_metadata.py — new file)
T008 [P] (test_install_from_built_wheel.py — new file)
```

Both new test files; can land concurrently. T009–T011 are local-shell verifications that need T007 + T008 to have landed first.

### Within Phase 6 (Polish)

```text
T028 [P] (visit PyPI listing — read-only)
T029 [P] (README quickstart update — separate file from T030)
T031 [P] (CLAUDE.md SPECKIT marker — separate file)

T027 (full pytest) — sequential, runs against the post-018 working tree
T030 (CHANGELOG verification) — sequential, depends on T014 + T025 having landed
```

---

## Implementation Strategy

### MVP (delivers user-visible value on its own)

**US1 + US2** is the MVP. Land T001–T021 plus T027 (full regression). At that point:

- `pip install aivg` works from any Python 3.11+ venv on Linux/macOS.
- A maintainer following the runbook can cut subsequent releases manually.
- No CI automation yet — but the package exists, is installable, and is shipping the post-019 canonical names.

**US1 alone is NOT shippable.** It only produces a local wheel. Without US2 nothing's on PyPI; operators can't run `pip install aivg` because the name resolves to nothing.

### Incremental — add US3 (CI automation)

Land T022–T026 after US2 has succeeded at least once. At that point:

- Every subsequent release is `git tag` + `git push --tags`.
- No long-lived PyPI tokens anywhere; OIDC Trusted Publishing is the canonical credential path.
- Audit trail of every release in GitHub Actions logs.

### Final — Polish

T027 + T028 + T029 + T030 + T031 round out the verification + docs + CHANGELOG. T028 / T029 / T031 are [P]-marked; the polish phase parallelizes well after the regression in T027.

---

## Test Count Target

- **Pre-018 baseline**: 294 passing unit + contract (post-feature 019).
- **New tests added by 018**:
  - test_pypi_metadata.py: ~3 tests (T007)
  - test_install_from_built_wheel.py: 1 test (T008) — heavyweight integration that does a full build + install
- **Target post-018**: `294 + 4 = 298 passing` in unit + contract, 0 failed, 3-run flake-free per T027.

The new integration test in T008 is `@pytest.mark.integration` so it's skippable on environments without `uv`. CI MUST include it; local dev MAY skip it for fast iteration.

---

## Operator-Action Checklist (the "what's NOT LLM-actionable" summary)

These tasks require a human at a terminal with PyPI / GitHub credentials:

- T012 — PyPI/TestPyPI account creation + 2FA enable
- T013 — First-ever manual upload to PyPI/TestPyPI (bootstraps the project + temporary API token)
- T020 — `git push origin vX.Y.Z` (first release tag)
- T021 — Worldwide-resolve smoke from a different host
- T022 — Trusted Publisher config on PyPI + TestPyPI web UIs
- T023 — GitHub Actions environment config
- T025 — Trigger the CI workflow with a follow-up tag push

Everything else is file edits + local-shell verifications that an LLM can drive end-to-end.

---

## Out-of-Scope Reminders

To make the implementation auditable against the spec's "packaging-only" scope:

- Zero changes under `src/aivg_core/` (the runtime ships as-is)
- Zero changes under `src/aivg_cli/`
- Zero changes to any wire surface (REST paths, WS frames, config keys, env vars)
- Wire contract version: pre-018 = `1.1.0`; post-018 (first PyPI release) = `0.2.0` per Spec Clarification Q2. Both are read-only fields the gateway emits in its JSON envelope; the change rides in the 018 release alongside the package rename. NO other wire-surface changes (REST paths, WS frames, config keys, env vars all byte-identical pre-AND-post 018).
- Zero changes to `@aivg/sat-sdk` (separate distribution channel, npm-side; out of scope)
- The CLI's hardcoded `__version__ = "0.2.0"` inside `aivg_cli/cli.py` is NOT touched by 018 (it pre-dates the package versioning; separate hygiene cleanup tracked for a future feature — see plan.md "Cross-cutting non-issues")

Any task that creeps into this territory is a scope violation against [spec.md § Assumptions](./spec.md#assumptions) and MUST be split into a separate feature.
