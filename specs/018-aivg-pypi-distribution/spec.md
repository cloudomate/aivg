# Feature Specification: AIVG PyPI distribution

**Feature Branch**: `018-aivg-pypi-distribution`  
**Created**: 2026-05-21  
**Status**: Draft — feature 019 has landed (post-merge `2d81078` on main); 018 is unblocked. Plan + tasks generated 2026-05-21.  
**Input**: User description: "i want to distributre avig setup and core as a pypi package"

## Clarifications

### Session 2026-05-21

- Q: Should the `satellite_webrtc` → `aivg_satellite` rename (plugin
  registration name, REST paths, config block, env vars) be part of
  this feature? → A: No. The rename ships FIRST as feature 019, and
  THEN feature 018 publishes the post-rename surface to PyPI. This
  feature is parked until 019 lands so the first PyPI release goes
  out under the final, transport-neutral names rather than re-publishing
  to rename one release later. **Resolved 2026-05-21**: feature 019
  landed on main (post-merge `2d81078`); 018 is unblocked.
- Q: Should AIVG ship as multiple PyPI packages (e.g.,
  `aivg-core` + `aivg-cli` + `aivg-satellite-plugin`) or a single
  package containing every piece? → A: Single package. The four
  pieces (`aivg_core` library, `aivg_cli` CLI binary, `aivg-satellite`
  Hermes plugin entry point, future `aivg setup` flow) are
  tightly coupled by version and shipped together. Splitting
  introduces inter-package version-pinning fragility for zero
  user-visible benefit — operators only ever install the bundle.
  The four `HTTP 404 (AVAILABLE)` PyPI probes at plan time were
  candidate NAMES for the single package, not four separate
  packages.
- Q: For the single package, use `aivg-core` (current `pyproject.toml`
  value) or rename to `aivg` (short canonical name)? → A: **`aivg`**.
  The product IS called AIVG (per feature 012 rebrand and the
  constitution); the CLI binary IS `aivg`; the npm SDK uses scope
  `@aivg/`. The `-core` suffix only earns its keep in multi-package
  ecosystems, which the single-package decision above just ruled out.
  Cost is one line in `pyproject.toml` (`name = "aivg-core"` → `name = "aivg"`).
  The PyPI distribution name becomes `aivg`; the Python import name
  `aivg_core` stays unchanged (common Python pattern — `pyyaml` →
  `import yaml`, `beautifulsoup4` → `import bs4`). Install command
  becomes `pip install aivg`. Wheel filename becomes
  `aivg-X.Y.Z-py3-none-any.whl`.
- Q: First PyPI release version? → A: **`0.2.0`**. Treat the first
  PyPI publication as the public baseline — every pre-018 version
  (`0.1.0` → ... → `0.3.1`) was internal, never visible outside the
  repo. The CHANGELOG entries for those internal versions are
  moved under an "Unreleased / pre-publication history" header;
  the first PyPI-tagged entry is `[0.2.0] — YYYY-MM-DD — First
  public release`. (Resolved at `0.2.0` rather than `0.1.0` to
  align with the SDK forward-bump per the next clarification —
  one number across every release surface.)
- Q: Should the wire-contract version (`aivg --contract-version`
  JSON field, currently `1.1.0` post-feature-017) also reset for
  consistency with the package version? → A: **Yes, reset to
  `0.2.0`**. Rationale: nothing is in production today (no
  external dependents on the current `1.1.0` value beyond the
  local electron-test + a handful of dev satellites); aligning
  every release axis at the public-baseline boundary keeps the
  mental model simple. The package version, the wire-contract
  version, and the SDK package version all align at `0.2.0` for
  the first PyPI release. The axes will naturally diverge over
  time (package bumps every release, wire bumps only when the
  wire shape changes) — single number is just the starting
  alignment, not an ongoing constraint. Cascade: requires
  updating the source `CONTRACT_VERSION` constant in
  `aivg_cli/cli.py` (currently `1.1.0`) to `"0.2.0"`.
- Q: How should `@aivg/sat-sdk` update to know the new wire
  contract `0.2.0`? → A: **Bump SDK forward to `0.2.0`** (MAJOR
  per 0.x semver convention; also satisfies the "one number
  across release surfaces" intent). Source `CONTRACT_VERSION`
  constant flipped from `"1.1.0"` to `"0.2.0"`. SDK package
  version evolves forward (no npm-monotonicity regression);
  electron-test's dep pin updates from `^0.1.x` to `^0.2.0`.
  The SDK's package version (an independent npm product) and
  the wire-contract version it speaks happen to align at
  `0.2.0` for this release boundary, but the two axes remain
  independent going forward. Cascade: SDK CHANGELOG entry,
  dist rebuild, electron-test package.json + lockfile refresh.

## User Scenarios & Testing *(mandatory)*

### User Story 1 — Operator installs AIVG with a single `pip install` from PyPI (Priority: P1)

An operator on a fresh machine that already has a working Hermes agent
install wants to add AIVG (the voice satellite gateway + the `aivg`
setup CLI) without cloning the AIVG repository. They run a single
`pip install ...` command into the Hermes virtualenv, then continue
with the existing `aivg setup` / `aivg device adopt` flow they would
follow today after an editable install.

**Why this priority**: This IS the feature's MVP. Today the only way
to get AIVG onto a host is to clone the git repository and run
`pip install -e .` against a local checkout. That is appropriate for
contributors but is a non-starter for any operator who just wants to
install and use AIVG. Without PyPI distribution, every install is a
manual chain of "clone, install, pray your branch matches what the
docs assume." Every other story in this spec depends on this one
working.

**Independent Test**: From a clean macOS or Linux host with Python
3.11+ and a Hermes-agent venv at `~/.hermes/hermes-agent/venv/`:

1. Run `pip install --target=... aivg` **without any local AIVG checkout**.
2. Confirm the `aivg` binary appears in the venv's `bin/` directory.
3. Confirm `aivg --version` returns the standard JSON envelope with
   the contract version field.
4. Confirm `hermes plugins list` shows the `aivg-satellite`
   entry-point plugin, with `source=entrypoint`.
5. The operator then runs `aivg setup` (or manually enables the
   plugin per existing docs) and a satellite-side smoke test
   (`aivg device adopt …`, then an end-to-end voice turn via
   the @aivg/sat-sdk electron-test or a real ESPHome device) passes.

If steps 1–5 succeed in one sitting without the operator opening the
AIVG repo or editing any AIVG source file, the story is delivered.

**Acceptance Scenarios**:

1. **Given** a clean Hermes venv with no AIVG package present,
   **When** the operator runs `pip install <aivg-package-name>`,
   **Then** the install completes in under 60 s on a typical
   broadband connection, the `aivg` binary appears in the venv's
   `bin/`, and `aivg --version` returns a JSON envelope whose
   `version` matches the just-installed package's PyPI version.
2. **Given** AIVG has just been pip-installed into the Hermes venv,
   **When** the operator restarts the Hermes gateway,
   **Then** the gateway logs show the `satellite_webrtc` plugin
   loading from the entry point (not from a vendored
   `~/.hermes/hermes-agent/plugins/platforms/satellite_webrtc/`
   directory), and the management plane binds on ports 8643 / 8644.
3. **Given** AIVG was installed via pip rather than editable mode,
   **When** the operator runs the existing electron-test or an
   ESPHome smoke device against the gateway,
   **Then** a voice turn completes end-to-end with byte-equivalent
   behavior to the same test run after an editable install.

---

### User Story 2 — Maintainer pre-flights a release on TestPyPI before promoting to real PyPI (Priority: P2)

A maintainer cutting a new AIVG release wants to validate the
packaging end-to-end on TestPyPI (a separate index) before publishing
to real PyPI. PyPI versions are immutable — once `0.2.0` exists on
real PyPI, that name+version is burned, even if it is then deleted.
The TestPyPI staging step exists to catch packaging mistakes
(missing files, broken entry points, missing `LICENSE`, etc.) where
the mistake is recoverable.

**Why this priority**: Reduces the blast radius of a packaging error
from "we waste a version number on real PyPI forever" to "we waste a
version number on TestPyPI, which nobody else depends on." This is
hygiene, not the headline feature — hence P2 — but it pays for
itself the first time a release would have failed on real PyPI.

**Independent Test**: A maintainer following the documented release
runbook can:

1. Build the distribution artifacts locally (sdist + wheel).
2. Upload the artifacts to TestPyPI.
3. Install from TestPyPI into a throwaway venv on the same machine.
4. Run a documented smoke check (`aivg --version`,
   `aivg --contract-version`, `aivg list` — empty registry is fine).
5. Only on a clean smoke pass do they promote the SAME artifact
   bytes (not a rebuild) to real PyPI.

**Acceptance Scenarios**:

1. **Given** a freshly-built sdist + wheel for AIVG version `X.Y.Z`,
   **When** the maintainer follows the documented TestPyPI upload
   step, **Then** TestPyPI accepts the upload and the artifact is
   installable in a clean venv via
   `pip install -i https://test.pypi.org/simple/ aivg==X.Y.Z`.
2. **Given** the TestPyPI install succeeded and the smoke checks
   passed, **When** the maintainer follows the promotion step,
   **Then** the SAME artifact files (not rebuilt) upload to real
   PyPI and become installable via `pip install aivg==X.Y.Z`
   within 5 minutes of the upload command returning.
3. **Given** a TestPyPI upload that triggers a smoke failure,
   **When** the maintainer reads the documented runbook,
   **Then** the runbook explicitly states "do NOT promote to real
   PyPI; fix and re-tag" and never advises mutating the failed
   release in place.

---

### User Story 3 — Repo CI auto-publishes new tagged releases (Priority: P3)

A maintainer tags a release commit (e.g. `v0.2.1` after the first `v0.2.0` shipped) and pushes the tag.
A CI workflow on the repo's hosting platform (GitHub) builds the
sdist + wheel, uploads them to TestPyPI, runs the documented smoke
install, and (on success) uploads the same bytes to real PyPI —
without any human re-running `twine upload` from a laptop.

**Why this priority**: Removes the maintainer's laptop from the
release path. Today's manual flow has a single human in the loop
who has to remember the runbook every time; CI codifies the runbook
and replaces the human's "I think I followed step 3 correctly" with
a verifiable workflow log. Also enables Trusted Publishing (PyPI's
OIDC-based no-token publishing mechanism), which is materially safer
than long-lived `twine` tokens stored on a developer machine.

**Independent Test**: After the workflow lands:

1. A maintainer creates an annotated git tag `vX.Y.Z` at the head
   of `main` (or a release branch).
2. They push the tag.
3. Without any further human input, the CI run completes within
   10 minutes and `pip install aivg==X.Y.Z` works against
   real PyPI from a clean venv.

If a manual `twine upload` from a laptop is ever required for a
normal release, this story is NOT delivered.

**Acceptance Scenarios**:

1. **Given** the CI release workflow is installed on the repo,
   **When** a maintainer pushes a tag matching `vX.Y.Z`,
   **Then** the workflow builds, smoke-tests on TestPyPI, and
   promotes to real PyPI without requiring the maintainer to
   touch a CI dashboard or laptop terminal beyond `git push --tags`.
2. **Given** a tagged release that fails the TestPyPI smoke step,
   **When** the workflow encounters the failure,
   **Then** the workflow halts BEFORE the real-PyPI promotion step,
   leaves the TestPyPI upload as a recoverable record, and surfaces
   the failure to the maintainer via the standard CI notification
   channel.
3. **Given** the CI release workflow is being run by a brand-new
   maintainer with no prior release history,
   **When** they follow the documented one-time setup steps,
   **Then** the only credential they need to provision is access to
   the repo's CI secrets (Trusted Publishing OIDC config) — they
   never have to generate, paste, or rotate a long-lived PyPI API
   token.

---

### Edge Cases

- **Package name unavailable on PyPI**: the chosen package name
  (`aivg`, locked by clarification Q2) may already be registered by an unrelated
  project. The plan phase MUST verify name availability before the
  first publish; if taken, fall back per the `assumptions` section.
- **Maintainer reuses a version number after a failed publish**:
  PyPI rejects re-uploads of the same `version` (and TestPyPI's
  re-upload behaviour is similarly restrictive). The release workflow
  MUST detect this and surface a clear "bump the version and re-tag"
  message rather than silently rebuilding.
- **Conflict between an editable local install and a PyPI install**:
  a contributor on the AIVG repo may have `pip install -e .` AND
  later run `pip install aivg` in the same venv. The second
  install MUST not break the first, and the contributor SHOULD be
  warned of the conflict (pip's default behaviour is acceptable;
  no AIVG-specific shim required).
- **Transitive dependency breakage between editable and PyPI**:
  a Python wheel resolved from PyPI for a transitive dependency
  (e.g., `aioesphomeapi`, `aiortc`) may differ from the version
  pinned in `pyproject.toml` if pins are too loose. The release
  workflow MUST validate that the smoke install resolves the same
  major.minor as the dev-time install for every direct dependency.
- **Hermes installed in a different venv than the AIVG install**:
  the `aivg-satellite` entry point is only discoverable by the
  Hermes plugin loader if AIVG is installed into the SAME venv that
  Hermes runs from. The PyPI README / docs MUST surface this
  explicitly (it caught us today during deploy).
- **A published release contains a regression**: PyPI allows
  `yank` (which hides the version from new resolves but keeps it
  installable for users who already pinned). The release workflow
  MUST document how to yank, and MUST never instruct a maintainer
  to delete + re-upload the same version.
- **Multi-architecture install**: AIVG is pure Python; native deps
  (`aiortc`, `av`) ship their own per-platform wheels. Any platform
  for which `aiortc`/`av` does NOT publish a wheel will require a
  C/C++ toolchain at install time. The PyPI README MUST list the
  supported platforms (the intersection of what `aiortc` + `av`
  ship wheels for: Linux x86_64, Linux aarch64, macOS x86_64,
  macOS arm64, Windows x86_64).

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The AIVG package MUST be installable into a clean
  Python ≥3.11 virtualenv via a single `pip install <name>` command
  from PyPI, without requiring the operator to clone the AIVG
  repository, configure an extra index, or run `pip install -e`.
- **FR-002**: Installation MUST register the `aivg` CLI binary on
  the install venv's `bin/` so that `<venv>/bin/aivg --version`
  works immediately after install.
- **FR-003**: Installation into a Hermes virtualenv MUST register
  the `aivg-satellite` entry point under the `hermes_agent.plugins`
  group so the Hermes plugin loader discovers it on next gateway
  start (no manual file-system vendoring required).
- **FR-004**: All runtime dependencies declared in
  `pyproject.toml` MUST resolve from PyPI on every supported
  target platform without manual pre-install steps beyond the
  documented platform prerequisites for `aiortc` / `av`
  (e.g., the system `ffmpeg` libraries those upstream projects
  already require).
- **FR-005**: Each published release MUST include BOTH a source
  distribution (`.tar.gz` sdist) and a pure-Python wheel
  (`py3-none-any.whl`) so installation does not require a build
  toolchain on supported platforms.
- **FR-006**: The package version MUST be sourced from a SINGLE
  authoritative location (`pyproject.toml` `[project] version`).
  The string returned by `aivg --version` MUST equal the
  PyPI-displayed version, byte-for-byte.
- **FR-007**: A maintainer following the documented release runbook
  MUST be able to execute an end-to-end release (build → TestPyPI →
  smoke → real PyPI) without manually editing any file in the repo
  beyond the version bump and the changelog entry.
- **FR-008**: The release runbook MUST require a successful
  TestPyPI smoke install before any real PyPI upload of the same
  version.
- **FR-009**: Published distribution metadata MUST include: a
  license declaration (a `LICENSE` file MUST exist in the repo
  root and be referenced from `pyproject.toml`), an author /
  maintainer field, the project repository URL, a short
  description, the long description (from `README.md`), and PyPI
  trove classifiers identifying the supported Python versions,
  operating systems, and development status.
- **FR-010**: The PyPI-installed package MUST be byte-equivalent
  in user-visible behavior to the same version installed via
  editable mode from the matching git tag. "User-visible behavior"
  here covers: the `aivg` CLI surface, the `aivg-satellite` entry
  point, the `aivg_core` Python import surface, the contract
  version string, and the runtime wire formats.
- **FR-011**: Every published release MUST correspond to a tagged
  commit in the AIVG git repository. The release artifacts MUST be
  reproducible from that tag — anyone with the tag's SHA can
  rebuild the wheel and verify it matches the PyPI-hosted bytes
  (modulo metadata fields that are intrinsically build-time, e.g.
  build timestamps inside the sdist).
- **FR-012**: PyPI authentication secrets (API tokens, OIDC
  configuration) MUST NEVER be committed to the AIVG repository
  in any branch or git history. The release runbook MUST document
  where these secrets live (CI secret store, maintainer's
  password manager) and how they are rotated.
- **FR-013**: The `aivg setup` flow shipped in feature 013 MUST
  work end-to-end when invoked after a PyPI install — i.e., the
  combination `pip install aivg && aivg setup` MUST be a
  sufficient installation path on a fresh host with Hermes
  installed, with no other manual steps required.
- **FR-014**: The PyPI listing's README (rendered from
  `README.md`) MUST surface, prominently and near the top:
  the supported Python versions, the supported operating systems,
  the requirement to install into the Hermes venv (not a fresh
  venv) for the entry point to be discovered by Hermes, and a
  link to the AIVG repository.
- **FR-015**: A release that fails any step after the build phase
  (TestPyPI upload, smoke install, or real PyPI promotion) MUST
  leave the AIVG git tag intact (i.e., NOT auto-delete the tag)
  so the maintainer can see in their tag list which versions
  failed to land and why.

### Key Entities

- **Release Artifact**: a paired (sdist, wheel) for a single
  version. The unit that gets uploaded to TestPyPI, smoke-tested,
  and then promoted to real PyPI. Identified by version string
  (matching the git tag).
- **Release Workflow**: the ordered sequence (version bump →
  changelog → tag → build → TestPyPI upload → smoke install →
  real PyPI upload → tag-push). Initially documented in a runbook;
  in story 3, codified as a CI workflow on the repo's hosting
  platform.
- **Package Manifest**: `pyproject.toml`. The single source of
  truth for package name, version, dependencies, entry points,
  and PyPI metadata. Every release-time string the user sees on
  PyPI traces back to this file.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A new user on a fresh Hermes-installed host can run
  `pip install <aivg-package-name>` and complete the install in
  under 60 seconds on a typical broadband connection (≥ 25 Mbps).
- **SC-002**: From `git push --tags` of an annotated release tag
  to "`pip install aivg==X.Y.Z` resolves on real PyPI" is
  under 10 minutes wall-clock, on the documented (or CI-codified)
  release path.
- **SC-003**: Across the first 5 published releases, zero versions
  reach real PyPI without first passing a TestPyPI smoke install.
  (Measured by counting real-PyPI releases whose version number
  does NOT appear in the TestPyPI release log before the
  real-PyPI upload timestamp.)
- **SC-004**: The published wheel is under 5 MB. (Today's
  source tree is small Python with no native code of its own;
  this is a guard against accidentally bundling test fixtures
  or vendored binaries.)
- **SC-005**: On Linux x86_64, Linux aarch64, macOS arm64, and
  macOS x86_64, `pip install <aivg-package-name>` in a clean
  Python 3.11 virtualenv with NO system C/C++ toolchain installed
  succeeds. (This proves the pure-Python wheel + the upstream
  per-platform wheels of `aiortc` / `av` cover the install path
  without invoking a compiler.)
- **SC-006**: After a PyPI install, `aivg --contract-version`
  returns a JSON envelope byte-identical to the same command run
  against the matching git-tag editable install of the same
  version.
- **SC-007**: A maintainer following the documented release
  runbook can complete a full release end-to-end (build,
  TestPyPI, smoke, real PyPI) in under 15 minutes wall-clock
  time, end-to-end.
- **SC-008**: For 100% of published releases, the artifact bytes
  uploaded to real PyPI are byte-identical to the artifact bytes
  uploaded to TestPyPI for the same version. (No "rebuild between
  staging and production" — promotion is a re-upload of the same
  files.)

## Assumptions

- **Package name**: `aivg` (locked by Clarification Q2 — see
  rationale there; renames the pre-018 `aivg-core` placeholder in
  `pyproject.toml` to the canonical short name). Verified
  available on PyPI at plan time (HTTP 404 from
  `https://pypi.org/pypi/aivg/json`). The Python import name
  `aivg_core` is unchanged — common Python pattern where the
  distribution name and module name differ.
- **Single-wheel distribution**: AIVG ships as ONE package
  containing both `aivg_core` and `aivg_cli`. No separate
  `aivg-cli` or `aivg-satellite-plugin` wheels in v1. (Rationale:
  fewer wheels to maintain; users only ever install the bundle.)
- **License**: MIT, matching `sdks/typescript/LICENSE`
  ("Cloudomate / AIVG contributors"). A `LICENSE` file MUST be
  added to the repo root as part of this feature's
  implementation (the repo lacks one today).
- **Repository hosting**: the AIVG repository lives on GitHub
  under the `cloudomate` organization (matches the
  `cloudomate/aivg-devices` companion repo named in feature 017
  docs). The CI Trusted Publishing setup assumes GitHub Actions.
- **Maintainer identity**: PyPI publishing requires a registered
  PyPI account with 2FA enabled and ownership of the chosen
  package name. The maintainer who first publishes will need to
  go through PyPI's standard account verification flow; this is
  out of scope for this feature (it's PyPI's process, not AIVG's).
- **Platform coverage**: Linux x86_64, Linux aarch64, macOS
  arm64, macOS x86_64. Windows is NOT a target for v1 (matches
  AIVG's existing target-platform note in feature 017 plan:
  "Linux + macOS userspace").
- **Hermes is installed separately**: AIVG is installed INTO an
  existing Hermes venv; AIVG does not pull Hermes as a
  dependency. The PyPI README MUST be unambiguous on this point.
- **Release cadence**: this feature aims for a maintainer-driven
  release cadence (no auto-release on every merge to main).
  Automated nightly / pre-release builds are deferred to a later
  feature.
- **No pre-release artifact storage**: TestPyPI is used as the
  pre-release staging area; this feature does NOT introduce a
  separate artifact repository (Artifactory, custom S3, etc.).
- **Constitution alignment**: this feature is a packaging /
  distribution change. It does NOT alter the four-plane contract,
  the `AgentPlatform` Protocol, the `MediaTransport` interface,
  the wire format, or any plugin-internal file. All five
  constitutional principles are untouched.
