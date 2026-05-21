# Phase 0 — Research

**Feature**: 018-aivg-pypi-distribution · **Date**: 2026-05-21

Seven ADRs back the implementation. Each documents the decision,
the rationale, and the alternatives that were considered and
rejected.

The single highest-risk unknown identified in the spec — PyPI name
availability — was resolved at plan time: `aivg-core`, `aivg`,
`aivg-satellite`, and `aivg-gateway` were ALL available (verified
via HTTP 404 from the JSON API). Spec Clarification Q2 then locked
the canonical choice as **`aivg`** — short, matches the CLI binary
and the product name, with no `-core` suffix to imply a multi-package
ecosystem.

---

## R-1: Build + publish tooling — `uv build` / `uv publish`

### Decision

Use **`uv`** (already installed at `~/.local/bin/uv 0.11.12`) for
both the wheel/sdist build and the PyPI upload:

```bash
uv build                                                     # produces dist/*.whl + dist/*.tar.gz
uv publish --publish-url https://test.pypi.org/legacy/      # TestPyPI staging
uv publish                                                   # real PyPI
```

`uv publish` natively supports PyPI Trusted Publishing OIDC — no
shell-out to `twine`, no PyPI API token. The CI workflow uses the
same commands.

### Rationale

- `uv` is already on the maintainer's path AND is the editable-install
  tool used today (we ran `uv pip install --python ~/.hermes/...` in
  feature 013 + the 2026-05-21 deploy). One binary covers install,
  build, and publish.
- `uv build` produces standard PEP 517 sdist + wheel using the
  declared `[build-system]` in `pyproject.toml` (currently
  `setuptools>=68`). No build-backend change needed.
- `uv publish` integrates with GitHub Actions OIDC out of the box
  (since uv 0.4.x): no `pypa/gh-action-pypi-publish` extra
  dependency in the workflow YAML.
- Single binary → one fewer thing to keep current vs. the
  `build` + `twine` + `pkginfo` chain.

### Alternatives rejected

- **`python -m build` + `twine upload`**. The historical default.
  Rejected because `uv` already does both and is already installed;
  adding `build` + `twine` as dev deps would be net work for a
  feature already covered. Also: `twine` predates Trusted Publishing
  and needs careful configuration to use OIDC; `uv publish` handles
  it natively.
- **`hatchling` as the build backend** (replacing `setuptools`).
  Rejected as out of scope — `pyproject.toml`'s
  `[build-system] requires = ["setuptools>=68", "wheel"]` already
  works for an editable install; backend change is a separate decision
  with its own risks (entry-point semantics, sdist file inclusion).
- **`flit`**. Same: out of scope, would require migrating the
  declared build backend.

---

## R-2: PyPI Trusted Publishing setup — GitHub Actions OIDC

### Decision

Use **PyPI Trusted Publishing** with GitHub Actions as the OIDC
issuer. One-time setup on the PyPI side (per project):

1. Maintainer creates the PyPI project `aivg` (initial
   upload bootstraps the project; subsequent uploads via OIDC).
   For Trusted Publishing this is configured under
   PyPI → Project → Publishing → Add → "Trusted publisher".
2. Configure the trusted publisher with:
   - Owner: `cloudomate`
   - Repository: `aivg`
   - Workflow filename: `release.yml`
   - Environment name: `pypi` (optional but recommended)
3. Same setup repeated separately on TestPyPI
   (`test.pypi.org`) for the TestPyPI workflow path.

The GitHub Actions workflow uses `id-token: write` permission
and `uv publish` (which exchanges the OIDC token for a short-lived
PyPI upload token at publish time).

### Rationale

- Trusted Publishing is the canonical 2026 path. PyPI now
  recommends it over long-lived API tokens for any project that
  publishes from CI.
- Zero long-lived credentials anywhere: no secret to rotate, no
  secret to leak from a developer machine, no secret in CI
  encrypted-secrets store.
- Audit trail: every publish is tied to a specific GitHub Actions
  workflow run on a specific commit SHA. Operators can verify the
  published wheel came from the tagged source.
- Spec FR-012 binding ("PyPI authentication secrets MUST NEVER be
  committed; release runbook MUST document where they live") is
  satisfied trivially — there are no secrets to document. The
  Trusted Publisher config itself lives on PyPI, not in the repo.

### Alternatives rejected

- **Long-lived PyPI API token in GitHub Secrets**. The legacy path.
  Rejected because (a) FR-012 implies a strong "no long-lived
  credentials in the release path" preference, (b) token rotation
  is a recurring maintenance cost, (c) any maintainer with repo
  admin can extract the token, (d) Trusted Publishing eliminates
  the whole risk class.
- **Manual `uv publish` from a maintainer laptop with a per-machine
  token**. Acceptable for story 2 (TestPyPI pre-flight by a
  maintainer for diagnosis), but story 3 binds CI as the canonical
  release path. The runbook documents the laptop path as
  diagnostic-only.
- **`pypa/gh-action-pypi-publish` GitHub Action**. Functionally
  identical to `uv publish` for OIDC. Rejected to avoid pulling in
  a separate action when `uv` (already in the workflow for build)
  covers it natively — one fewer thing to update.

---

## R-3: `pyproject.toml` metadata completion

### Decision

Add the following keys to the `[project]` table, **in addition to**
the existing `name` / `version` / `description` / `dependencies` /
`requires-python`:

```toml
[project]
license = {text = "MIT"}
readme = "README.md"
authors = [
    {name = "Cloudomate", email = "hello@cloudomate.com"},
]
maintainers = [
    {name = "Cloudomate / AIVG contributors"},
]
keywords = ["voice", "satellite", "webrtc", "hermes", "aivg",
            "ai", "agent", "speech"]
classifiers = [
    "Development Status :: 4 - Beta",
    "Intended Audience :: Developers",
    "Intended Audience :: System Administrators",
    "License :: OSI Approved :: MIT License",
    "Operating System :: POSIX :: Linux",
    "Operating System :: MacOS",
    "Programming Language :: Python :: 3",
    "Programming Language :: Python :: 3.11",
    "Programming Language :: Python :: 3.12",
    "Topic :: Communications :: Telephony",
    "Topic :: Multimedia :: Sound/Audio :: Speech",
    "Topic :: Software Development :: Libraries",
]

[project.urls]
Repository = "https://github.com/cloudomate/aivg"
Issues = "https://github.com/cloudomate/aivg/issues"
Changelog = "https://github.com/cloudomate/aivg/blob/main/CHANGELOG.md"
Documentation = "https://github.com/cloudomate/aivg/blob/main/README.md"
```

### Rationale

- Every field is required or strongly recommended by PEP 621 / PyPI
  for a complete listing. Missing `license` causes a PyPI listing
  warning; missing `readme` means the project page is empty.
- `classifiers` populate PyPI's faceted browse experience and let
  installers filter on Python version / OS support.
- `[project.urls]` populate the PyPI sidebar with the canonical
  links operators look for first.
- `keywords` improves PyPI search ranking for relevant queries
  ("voice satellite", "voice gateway", etc.).

### Alternatives rejected

- **Use `setuptools.packages.find` exclusion patterns to also exclude
  `tests/`, `specs/`, etc. from the wheel**. Already done implicitly
  by the existing `[tool.setuptools.packages.find]` config which
  whitelists only `aivg_core*` and `aivg_cli*`. No further exclusion
  needed.
- **Specify `license = "MIT"` (PEP 639 SPDX-string form)**. The
  newer PEP 639 syntax. Rejected for v1 because PyPI's UI
  rendering of PEP 639 was still inconsistent across uploaders as
  of late 2025; the legacy `{text = "MIT"}` form has universal
  support. Future feature can migrate to PEP 639 once it's
  uniformly handled.
- **Add `optional-dependencies` for development/testing**. Already
  present (`[project.optional-dependencies] dev = [...]`); no
  change required.

---

## R-4: `LICENSE` file content — MIT, matching the TypeScript SDK

### Decision

Add `LICENSE` to the repo root. Content: the **exact** MIT license
text from `sdks/typescript/LICENSE` (already present), copyright
attribution `Cloudomate / AIVG contributors`, year `2026`.

### Rationale

- Matches the existing TypeScript SDK LICENSE — single license
  posture across the project. Operators (and downstream Linux
  distros) see one license, not two.
- MIT is the most permissive widely-recognized license; minimum
  friction for adoption.
- A repo-root `LICENSE` file is the standard location every build
  backend (setuptools, hatchling, flit, poetry) auto-includes in
  the wheel's `.dist-info/` without explicit configuration. Bare
  presence is enough.

### Alternatives rejected

- **Apache 2.0**. Defensible (patent-grant clause adds protection)
  but introduces a license mismatch with the existing TypeScript
  SDK. Project-wide license consistency is more valuable than the
  patent-grant for a v1 hobby/SMB voice-gateway product.
- **BSD-3-Clause**. Equivalent to MIT plus a no-endorsement clause.
  No real-world benefit for AIVG; introduces gratuitous
  attribution-clause divergence from the TypeScript SDK.
- **Dual MIT-or-Apache-2.0**. Common in the Rust ecosystem;
  unnecessary complexity for a Python distribution.

---

## R-5: Wheel inventory verification — what ships, what doesn't

### Decision

After `uv build`, the wheel MUST contain:

- `aivg_core/**/*.py` (all subpackages, including
  `platforms/hermes/plugin_entrypoint/` for the entry-point seam)
- `aivg_cli/**/*.py`
- `aivg-X.Y.Z.dist-info/METADATA` (PEP 621 metadata)
- `aivg-X.Y.Z.dist-info/entry_points.txt` (carries
  `aivg = aivg_cli.cli:app` AND
  `aivg-satellite = aivg_core.platforms.hermes.plugin_entrypoint`)
- `aivg-X.Y.Z.dist-info/LICENSE`
- `aivg-X.Y.Z.dist-info/RECORD`

The wheel MUST NOT contain:

- `tests/**`
- `specs/**`
- `clients/**`
- `sdks/**`
- `deploy/**`
- `scripts/**`
- `docs/**`
- `.github/**`
- `CHANGELOG.md` (consumed via the PyPI listing's Changelog
  link, not embedded)

This is verified locally by `unzip -l dist/aivg-*.whl` AND
by an automated test in
`tests/integration/test_install_from_built_wheel.py` that asserts
post-install `aivg --version` works AND the wheel size is under
the 5 MB cap (SC-004).

### Rationale

- The existing `[tool.setuptools.packages.find] include =
  ["aivg_core*", "aivg_cli*"]` already excludes the non-package
  trees; this ADR makes the inclusion/exclusion explicit so future
  changes don't accidentally bundle test fixtures or the entire
  `specs/` directory.
- The 5 MB cap (SC-004) is a sanity guard against accidental
  bundling — at the time of writing, `aivg_core` source is a few
  hundred KB; a 5 MB wheel would indicate something is wrong.
- Both entry points (the `aivg` CLI binary AND the `aivg-satellite`
  Hermes plugin discovery hook) MUST land in the wheel's
  `entry_points.txt` for operators to get the post-install
  experience the spec promises.

### Alternatives rejected

- **Use `MANIFEST.in` to control sdist contents**. Rejected because
  `MANIFEST.in` only controls sdist, not wheel. The
  `[tool.setuptools.packages.find]` pattern already controls wheel
  contents correctly; sdist follows from the same configuration.
- **Add `tests/` to the wheel for runtime introspection**. Rejected
  because (a) doubles the wheel size, (b) shipping tests blurs the
  "what's the install vs. what's the test" line, (c) anyone who
  needs the tests can clone the repo.

---

## R-6: TestPyPI staging — what it is, how it differs

### Decision

Treat **TestPyPI (https://test.pypi.org/)** as the mandatory
pre-flight index for every release. Every published version of
`aivg` MUST first be uploaded to TestPyPI, smoke-installed
in a clean throwaway venv, and only then promoted to real PyPI.

The promotion step uploads the SAME artifact bytes (the same
`dist/aivg-X.Y.Z-py3-none-any.whl` and `dist/aivg-X.Y.Z.tar.gz`
files) to real PyPI — no rebuild between staging and prod.

### Rationale

- PyPI versions are immutable. A bad upload to real PyPI burns
  the version number forever (yank hides it from new installs but
  doesn't free the number). TestPyPI is the recovery mechanism:
  upload, validate, only then promote.
- TestPyPI is operated by the PyPA, free, and infinitely
  reproducible. Catches every packaging mistake (missing files,
  broken entry points, missing LICENSE, classifier typo) where
  the mistake is recoverable (TestPyPI nobody-depends-on-it land).
- Same-bytes promotion is the binding anti-drift gate (SC-008).
  The wheel that 100 operators install on day 1 of a release IS
  the wheel that the maintainer manually installed from TestPyPI
  on day 0.

### Alternatives rejected

- **Skip TestPyPI; upload straight to real PyPI**. Acceptable for
  experienced maintainers comfortable with version-burning, but
  the spec's SC-003 binds zero failed promotions for the first
  5 releases. TestPyPI is the de-risking mechanism.
- **Set up a private pypi-compatible artifact server
  (Artifactory / Nexus / S3+pypi-server)**. Rejected because it
  duplicates what TestPyPI gives free and adds infra to maintain.
  TestPyPI is operated by PyPA at production reliability.
- **Use a separate "release candidate" version pattern
  (`0.3.1rc1`)**. Acceptable per PEP 440 and complementary to
  TestPyPI (NOT exclusive). Out of scope for v1; the v1 path is
  "TestPyPI for everyone, real PyPI for final". Future features
  may layer in pre-release versions.

---

## R-7: Release-runbook automation level — manual + CI both ship in v1

### Decision

Ship **both** a documented manual release runbook (in
[quickstart.md](./quickstart.md)) AND a GitHub Actions CI workflow
(`.github/workflows/release.yml`) in the v1 release. They serve
different stories:

- **Story 2 (P2) — manual runbook**: the maintainer-driven pre-
  flight path. Useful when validating a release for the first
  time, debugging a failed CI run, or shipping a hotfix from
  a laptop when CI is down.
- **Story 3 (P3) — CI workflow**: the canonical release path
  for every normal release. Tag push triggers it; no laptop in
  the loop.

The runbook and the CI workflow MUST execute the **same logical
sequence** (build → TestPyPI → smoke → real PyPI). The CI
workflow is the runbook's automation, not a different path.

### Rationale

- Spec story 2 explicitly binds the manual runbook ("A maintainer
  cutting a new AIVG release wants to validate the packaging
  end-to-end on TestPyPI"). Without it, story 2 is undelivered.
- Spec story 3 explicitly binds CI ("removes the maintainer's
  laptop from the release path"). Without it, story 3 is
  undelivered.
- Shipping both is cheap: the runbook is one page of markdown;
  the CI workflow is ~50 lines of YAML reading the same commands.
- Operators benefit from the existence of both paths even when
  only one is normally used — if CI is broken, the manual path
  is the fallback; if a maintainer leaves the org, the CI path
  continues working without their laptop.

### Alternatives rejected

- **CI-only**. Rejected because story 2 implies a maintainer-driven
  validation path. Also: when CI is broken, there's no escape
  hatch.
- **Manual-only**. Rejected because story 3 specifically binds
  "no laptop in the release path." This is the explicit ask.
- **CI fires on every push to `main` (no tag required)**.
  Rejected because every merge would publish a new version,
  which is too aggressive for a hobby/SMB project and would burn
  version numbers fast. Tag-push is the standard trigger for
  maintainer-driven release cadence.
- **Release branches (e.g. `release/0.4.x`)**. Out of scope for
  v1. The v1 model is "tag from `main` (or any branch); CI builds
  it." Future features may add release-branch policy if needed.

---

## Cross-cutting non-issues (recorded for completeness)

- **PyPI name availability**: resolved at plan time.
  `aivg` is AVAILABLE on PyPI (HTTP 404 from the JSON API).
  No fallback needed. (Locked by Spec Clarification Q2.)
- **Repo remote**: `git@github.com:cloudomate/aivg.git` — matches
  the spec's "Repository hosting" assumption. Trusted Publishing
  config uses `cloudomate/aivg` as the GitHub repo identifier.
- **Python version support**: `pyproject.toml` declares
  `requires-python = ">=3.11"`; classifiers add 3.11 and 3.12.
  Python 3.13's removal of `audioop` (used by
  `aivg_core/transports/esphome/media_adapter.py`) is a separate
  follow-up feature — out of scope for 018.
- **CLI version drift**: the CLI's hardcoded `__version__ = "0.2.0"`
  inside `aivg_cli/cli.py` is NOT touched by 018. It pre-dates
  the package versioning and is a separate hygiene cleanup
  (out of scope; documented for a future feature).
- **PyPI 2FA on the maintainer account**: PyPI requires 2FA for
  all uploads since 2024. The maintainer publishing the first
  release MUST have 2FA enabled on their PyPI account. This is
  one-time external setup; documented in the runbook
  ([quickstart.md § 0](./quickstart.md) prerequisites).
