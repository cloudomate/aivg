# Quickstart — Cut an `aivg` PyPI release

**Feature**: 018-aivg-pypi-distribution · **Date**: 2026-05-21

The one-page release runbook. Every step is executable; nothing
requires reading external docs. Runs against the canonical PyPI
project `aivg` (already verified available on PyPI at
plan time — HTTP 404 from the JSON API).

Repo root for all commands: `/Users/yashwant.singh/coderepo/aivg`.

---

## 0. One-time setup (per maintainer / per host)

**Done once. Skip on subsequent releases.**

### 0.1 PyPI accounts

1. Create a PyPI account at `https://pypi.org/account/register/`.
2. Enable 2FA at `https://pypi.org/manage/account/two-factor/`
   (REQUIRED since 2024 — PyPI rejects uploads from non-2FA accounts).
3. Repeat steps 1–2 on TestPyPI (`https://test.pypi.org/`).

### 0.2 PyPI Trusted Publisher config (per project, per index)

On `https://pypi.org/manage/project/aivg/settings/publishing/`
(after the first manual upload bootstraps the project):

- Owner: `cloudomate`
- Repository name: `aivg`
- Workflow filename: `release.yml`
- Environment name (optional): `pypi`

Repeat on `https://test.pypi.org/manage/project/aivg/settings/publishing/`
with environment name `testpypi`.

### 0.3 Local toolchain

```bash
uv --version           # expect >= 0.4.x — supports `uv publish` OIDC
git --version          # expect any modern
~/.hermes/hermes-agent/venv/bin/python --version   # 3.11.x
```

---

## 1. Pre-tag preparation

### 1.1 Pick the new version

Semver rules:

- PATCH bump (`0.3.1 → 0.3.2`): docs, internal renames, bug fixes,
  no API/wire change.
- MINOR bump (`0.3.x → 0.4.0`): additive new features, additive
  wire changes. (e.g. feature 017's pre-PyPI contract bump 1.0.0 → 1.1.0 — pre-PyPI; the first PyPI release resets the wire contract to 0.2.0 per Spec Clarification Q2.)
- MAJOR bump (`0.x.y → 1.0.0`): NOT yet defined for AIVG. v1.0.0
  triggers a separate stability commitment + this contract review.

### 1.2 Bump `pyproject.toml`

```bash
# Edit by hand or use uv version --bump (uv 0.5+)
$EDITOR pyproject.toml
# Update: version = "X.Y.Z"
```

### 1.3 Update CHANGELOG

Add a new top-level section to `CHANGELOG.md`:

```markdown
## [X.Y.Z] — YYYY-MM-DD — <one-line summary>

<2–4 paragraph release note describing user-visible changes>

### Added / Changed / Fixed / Removed (whichever applies)

* ...
```

### 1.4 Run the test suite

```bash
PYTHONPATH=src:tests ~/.hermes/hermes-agent/venv/bin/python \
  -m pytest tests/unit/ tests/contract/ -q --tb=line
```

Expected: all pass. If anything fails, fix before tagging — a
release MUST NOT be cut on a failing test suite.

### 1.5 Run the metadata + install smoke tests

```bash
PYTHONPATH=src:tests ~/.hermes/hermes-agent/venv/bin/python \
  -m pytest tests/contract/test_pypi_metadata.py \
            tests/integration/test_install_from_built_wheel.py -v
```

Expected: both pass. These are 018's new tests; they catch
packaging mistakes BEFORE the wheel ever leaves the repo.

### 1.6 Commit

```bash
git add pyproject.toml CHANGELOG.md
git commit -m "release: prepare aivg X.Y.Z"
```

---

## 2. Tag the release

```bash
git tag -a vX.Y.Z -m "aivg X.Y.Z"
git log -1 --format="%H" vX.Y.Z   # record the SHA the artifact will tie back to
```

The tag is the immutable git reference the published artifact
ties back to. Once created, push happens AFTER successful PyPI
upload (step 6).

---

## 3. Build

```bash
rm -rf dist/                   # start clean
uv build
ls dist/
# expect:
#   aivg-X.Y.Z-py3-none-any.whl
#   aivg-X.Y.Z.tar.gz
```

### 3.1 Wheel inspection (the "what's in the box" check)

```bash
unzip -l dist/aivg-X.Y.Z-py3-none-any.whl | head -40

# Check there's no tests/, specs/, etc. in the wheel:
unzip -l dist/aivg-X.Y.Z-py3-none-any.whl \
  | grep -E "tests/|specs/|clients/|sdks/|deploy/|docs/|\.github/" \
  && { echo "FAIL: wheel contains files that shouldn't ship"; exit 1; } \
  || echo "OK: wheel inventory is clean"

# Check size is under 5 MB:
test "$(stat -f %z dist/aivg-X.Y.Z-py3-none-any.whl)" -lt 5242880 \
  && echo "OK: wheel under 5 MB" \
  || { echo "FAIL: wheel exceeds 5 MB cap"; exit 1; }
```

### 3.2 Entry-point verification

```bash
unzip -p dist/aivg-X.Y.Z-py3-none-any.whl \
  aivg-X.Y.Z.dist-info/entry_points.txt
# expect:
#   [console_scripts]
#   aivg = aivg_cli.cli:app
#
#   [hermes_agent.plugins]
#   aivg-satellite = aivg_core.platforms.hermes.plugin_entrypoint
```

---

## 4. TestPyPI upload + smoke install

### 4.1 Upload to TestPyPI

```bash
# Trusted Publishing assumes you're in CI; for local manual upload
# you need an API token from https://test.pypi.org/manage/account/token/
# stored in ~/.pypirc or passed via $UV_PUBLISH_TOKEN.
uv publish --publish-url https://test.pypi.org/legacy/

# Verify:
#   https://test.pypi.org/project/aivg/X.Y.Z/  → 200
```

### 4.2 Smoke install from TestPyPI

```bash
# Throwaway venv that doesn't pollute the maintainer's environment.
SMOKE=/tmp/aivg-smoke-X.Y.Z
rm -rf "$SMOKE"
uv venv "$SMOKE"

# TestPyPI's --extra-index-url lets pip resolve our package from
# TestPyPI while still pulling deps from real PyPI (TestPyPI doesn't
# mirror the full Python ecosystem).
uv pip install --python "$SMOKE/bin/python" \
  -i https://test.pypi.org/simple/ \
  --extra-index-url https://pypi.org/simple/ \
  aivg==X.Y.Z

# Verify install:
"$SMOKE/bin/aivg" --version
# expect: {"ok":true,"data":{"version":"X.Y.Z",...}}

"$SMOKE/bin/aivg" --contract-version
# expect: {"ok":true,"data":{"contract_version":"0.2.0","transports":[...]}}
```

If any of the above fails: do NOT proceed to step 5. Fix the
issue, bump `pyproject.toml` to the next version (TestPyPI also
treats versions as immutable), and start over from step 1.4.

---

## 5. Real-PyPI upload

```bash
# Same `dist/*` files; no rebuild.
uv publish

# Verify:
#   https://pypi.org/project/aivg/X.Y.Z/  → 200
```

The bytes uploaded here MUST be the same bytes that step 4.1
uploaded to TestPyPI. Verify with `sha256sum`:

```bash
sha256sum dist/aivg-X.Y.Z*
# compare to the SHA shown on the PyPI page sidebar for each file
```

---

## 6. Push the tag

```bash
git push origin main          # if the commit isn't pushed yet
git push origin vX.Y.Z
```

The tag is the public record of which commit produced this
release. Operators inspecting `aivg==X.Y.Z` can run
`git log vX.Y.Z` to see exactly what's in it.

---

## 7. Post-release verification (clean host smoke)

On a different machine (or fresh venv on the same machine):

```bash
SMOKE=/tmp/aivg-post-release-X.Y.Z
rm -rf "$SMOKE"
uv venv "$SMOKE"
uv pip install --python "$SMOKE/bin/python" aivg==X.Y.Z

"$SMOKE/bin/aivg" --version
"$SMOKE/bin/aivg" --contract-version
```

Both commands MUST succeed and return the X.Y.Z version + contract
0.2.0 envelope. This is the binding "worldwide resolvability"
gate.

---

## 8. CI-automated path (story 3)

The CI workflow at `.github/workflows/release.yml` automates
steps 3–6 above. To use it:

1. Land steps 1.1–1.6 on `main` (version bump + CHANGELOG +
   tests pass + commit).
2. Tag and push:
   ```bash
   git tag -a vX.Y.Z -m "aivg X.Y.Z"
   git push origin main vX.Y.Z
   ```
3. Watch the workflow run at
   `https://github.com/cloudomate/aivg/actions`. It runs:
   - Checkout at the tag
   - `uv build`
   - Wheel inspection (same checks as step 3.1)
   - `uv publish --publish-url https://test.pypi.org/legacy/`
     (Trusted Publishing OIDC)
   - Smoke install + `aivg --version` check
   - `uv publish` (real PyPI; same OIDC)
   - Post-release verification job
4. End-to-end: under 10 minutes wall-clock (SC-002).

If the workflow fails at any step BEFORE real PyPI upload, the
tag stays on the repo (FR-015). Maintainer fixes, bumps version,
and retags.

---

## 9. Failure recovery

### "Smoke install failed on TestPyPI"

Do NOT promote to real PyPI. Diagnose:

```bash
unzip -l dist/aivg-X.Y.Z*.whl | head -30   # inspect wheel
"$SMOKE/bin/pip" show aivg                  # confirm install metadata
"$SMOKE/bin/python" -c "import aivg_core; print(aivg_core.__file__)"
```

Common causes:
- Missing `LICENSE` file → setuptools complaint, no upload
- Stale `dist/` from a previous version still on disk → `rm -rf dist/`
  and rebuild
- New dep added but not declared in `pyproject.toml`
  `[project] dependencies` → import error post-install

Fix → bump `pyproject.toml` to the next version → start over at step 1.

### "Yank a bad release from real PyPI"

If a release reaches real PyPI and is regretted:

```bash
# Via the PyPI web UI:
#   https://pypi.org/manage/project/aivg/release/X.Y.Z/
#   → "Options" → "Yank release"
# The version remains downloadable for anyone with a pinned dep but
# is hidden from new resolves. The version number is permanently
# burned — the next release MUST bump to X.Y.(Z+1) or beyond.
```

### "Force-push the tag" — DO NOT

Once a tag is pushed and a PyPI release uses it, the tag MUST NOT
be force-moved. Anyone with the tag's old SHA in their dev environment
sees a divergence. If a release is wrong, yank + roll a new one.

---

## 10. Verification checklist (the "done" gate)

A release is "done" when all of these are true:

- [ ] `pip install aivg==X.Y.Z` resolves on real PyPI from a
      clean Python 3.11+ venv on Linux x86_64 (or Linux aarch64,
      macOS arm64, macOS x86_64).
- [ ] `aivg --version` in that venv returns `{"version":"X.Y.Z",...}`.
- [ ] `aivg --contract-version` returns
      `{"contract_version":"0.2.0","transports":[...]}`.
- [ ] The PyPI project page at
      `https://pypi.org/project/aivg/X.Y.Z/` lists the wheel +
      sdist, the license badge, the author, the repo + issues +
      changelog links, the Python-version requirement, and the OS
      classifiers.
- [ ] The git tag `vX.Y.Z` exists on `origin` and points at the
      commit the artifact was built from.
- [ ] `CHANGELOG.md` has the X.Y.Z entry.
- [ ] `sha256sum dist/aivg-X.Y.Z*` matches the SHA shown on
      both TestPyPI and real PyPI for the same version.

When all boxes are checked, the release is done. Move on.
