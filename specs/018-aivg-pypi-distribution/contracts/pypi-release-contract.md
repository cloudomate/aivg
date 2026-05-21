# Contract — PyPI Release Artifact

**Feature**: 018-aivg-pypi-distribution · **Date**: 2026-05-21
**Status**: Binding — defines what every released `aivg` artifact
on PyPI MUST contain and how operators MUST be able to consume it.

This contract documents the **publicly-visible release surface** of
`aivg`. It is the operator-facing contract; the in-package
behavior (REST paths, WS frames, etc.) is documented in the
respective feature specs and stays unchanged by 018.

---

## 1. Distribution channel

| Property | Value |
|---|---|
| Index URL | `https://pypi.org/simple/` (canonical PyPI) |
| Project URL | `https://pypi.org/project/aivg/` |
| TestPyPI staging URL | `https://test.pypi.org/simple/` |
| TestPyPI project URL | `https://test.pypi.org/project/aivg/` |
| Package name | `aivg` |
| Install command | `pip install aivg` |
| Install command (TestPyPI) | `pip install -i https://test.pypi.org/simple/ aivg` |
| Trusted Publisher | `cloudomate/aivg` repo, workflow `release.yml` |

Both PyPI and TestPyPI hold artifacts indefinitely; every version
is permanent. Yanking hides from new resolves but does NOT free
the version number (per PyPI policy).

---

## 2. Artifact pair

Every release version produces exactly **two files**, uploaded
together as a pair:

### 2.1 Source distribution (sdist)

| Field | Value |
|---|---|
| Filename | `aivg-X.Y.Z.tar.gz` |
| Format | gzipped tarball |
| Top-level directory inside | `aivg-X.Y.Z/` |
| Must include | `pyproject.toml`, `README.md`, `LICENSE`, `CHANGELOG.md`, `src/aivg_core/**/*.py`, `src/aivg_cli/**/*.py`, `PKG-INFO` |
| Must NOT include | `tests/`, `specs/`, `clients/`, `sdks/`, `deploy/`, `docs/`, `scripts/`, `.github/`, `.git/`, `.venv/`, `dist/`, `__pycache__/`, `*.pyc` |

### 2.2 Pure-Python wheel

| Field | Value |
|---|---|
| Filename | `aivg-X.Y.Z-py3-none-any.whl` |
| Format | PEP 427 wheel (zip) |
| ABI tag | `none` (pure Python) |
| Platform tag | `any` (cross-platform) |
| Python tag | `py3` (Python 3 generic; install gated by `requires-python`) |
| Must include | `aivg_core/` package tree, `aivg_cli/` package tree, `aivg-X.Y.Z.dist-info/{METADATA, entry_points.txt, LICENSE, RECORD, WHEEL}` |
| Must NOT include | `tests/`, `specs/`, source tree top-level non-package files |
| Size cap | ≤ 5 MB (binding — SC-004) |

### 2.3 Byte-equivalence guarantee (SC-008 / FR-010)

For every version `X.Y.Z`:

- The bytes of `aivg-X.Y.Z.tar.gz` uploaded to TestPyPI MUST
  be byte-identical to the bytes uploaded to real PyPI.
- The bytes of `aivg-X.Y.Z-py3-none-any.whl` uploaded to
  TestPyPI MUST be byte-identical to the bytes uploaded to real
  PyPI.
- Both files MUST be produced by a SINGLE `uv build` invocation;
  the publish steps re-upload the same files, never re-build.

Verifiable post-release by `sha256sum dist/aivg-X.Y.Z*.{tar.gz,whl}`
locally and comparing to the SHA values shown on the PyPI project
page (which PyPI displays per uploaded file).

---

## 3. Wheel entry points

The wheel's `entry_points.txt` MUST declare exactly these
entry points:

```ini
[console_scripts]
aivg = aivg_cli.cli:app

[hermes_agent.plugins]
aivg-satellite = aivg_core.platforms.hermes.plugin_entrypoint
```

Effect on install (`pip install aivg`):

- A binary named `aivg` lands on the install venv's `bin/`.
  Running `aivg --version` returns a JSON envelope with the
  installed version + contract version.
- Hermes's plugin loader (when installed into a Hermes venv)
  auto-discovers `aivg-satellite` under the `hermes_agent.plugins`
  group on next gateway start.

Operators do NOT need to manually edit `plugins.enabled:` if it
already lists `aivg-satellite` — the entry-point manifest name is
the operator-typed identifier and is stable across releases.

---

## 4. PyPI metadata (rendered listing)

The PyPI project page MUST display the following non-empty
fields (sourced from `pyproject.toml` `[project]`):

| Page section | Source |
|---|---|
| Project description (short) | `[project] description` |
| Long description | `[project] readme` → renders `README.md` as HTML |
| License | `[project] license` → "MIT" badge |
| Author | `[project] authors[0].name` |
| Maintainer | `[project] maintainers[0].name` |
| Repository link (sidebar) | `[project.urls] Repository` |
| Issues link (sidebar) | `[project.urls] Issues` |
| Changelog link (sidebar) | `[project.urls] Changelog` |
| Documentation link (sidebar) | `[project.urls] Documentation` |
| Classifiers (sidebar facets) | `[project] classifiers` |
| Requires-Python | `[project] requires-python` → "Requires: Python ≥3.11" |
| Keywords | `[project] keywords` |
| Released-version dropdown | every previously-uploaded version |

Empty / missing fields in the rendered listing indicate a
metadata gap in `pyproject.toml`. The
`tests/contract/test_pypi_metadata.py` (FR-009 binding) asserts
every required field is present, catching gaps BEFORE upload.

---

## 5. Install behaviour (FR-002 / FR-003 / FR-004 binding)

After `pip install aivg` into a Python 3.11+ venv:

| Surface | Expected |
|---|---|
| `<venv>/bin/aivg --version` | exits 0; stdout is `{"ok":true,"data":{"version":"X.Y.Z",...}}` |
| `<venv>/bin/aivg --contract-version` | exits 0; stdout is `{"ok":true,"data":{"contract_version":"0.2.0","transports":[...]}}` (reset at first PyPI release per Spec Clarification Q2) |
| `<venv>/lib/python3.11/site-packages/aivg_core/` | populated with the source tree |
| `<venv>/lib/python3.11/site-packages/aivg_cli/` | populated with the source tree |
| `<venv>/lib/python3.11/site-packages/aivg-X.Y.Z.dist-info/entry_points.txt` | contains both `aivg` console-script and `aivg-satellite` hermes plugin |
| Hermes plugin discovery | `hermes plugins list` (inside the Hermes venv) shows `aivg-satellite` with `source=entrypoint` |
| Voice-turn behaviour | a satellite client (e.g. @aivg/sat-sdk 0.1.4) completes register → adopt → voice turn against the Hermes gateway with the post-019 `aivg_satellite` plugin loaded |

Behavior is byte-equivalent to an editable install at the same
git tag (FR-010 / SC-006).

---

## 6. Forward-compatibility rules

For future releases (post-018) that touch this contract:

- **Adding a new entry point**: append to `[project.entry-points.<group>]`
  with a clear group/name. Operators who don't use it see no change.
- **Adding a new dependency**: append to `[project] dependencies`.
  Existing installs aren't affected; new installs pick it up.
- **Bumping `requires-python`**: MAJOR-bump-equivalent for users
  on the dropped Python version. Document loudly in CHANGELOG.
- **Renaming the package** (e.g. `aivg` → some-other-name): out of
  scope for any near-term release. If ever attempted, the
  release MUST ship BOTH names for at least one release with a
  meta-package that depends on the new name.
- **Bumping the major version** (`1.0.0`): triggers a contract
  review for THIS document. Any change to entry-point names,
  install command, install behavior, or the (sdist, wheel)
  pair shape MUST first land here.

---

## 7. Operator-visible failure modes

| Symptom | Cause | Remedy |
|---|---|---|
| `pip install aivg` returns "No matching distribution found" | Wrong Python version (<3.11) or wrong platform | Use Python 3.11+ on Linux x86_64/aarch64 or macOS arm64/x86_64. Windows is unsupported. |
| `pip install aivg` requires compiling | A transitive dep (`aiortc`, `av`) doesn't publish a wheel for this platform | One of the upstream projects is the source of truth. Operator's options: install a system C/C++ toolchain, or use a supported platform. |
| `aivg --version` is missing after install | The `aivg` entry-point script wasn't picked up | Confirm `<venv>/bin/aivg` exists; re-activate the venv. Often a `pip install` into the wrong venv. |
| Hermes doesn't show `aivg-satellite` in `hermes plugins list` | Install went into a venv other than the one Hermes runs from | Reinstall into the Hermes venv: `uv pip install --python ~/.hermes/hermes-agent/venv/bin/python aivg`. |
| `aivg-satellite` shows in `hermes plugins list` but `enabled=False` | Plugin entry-points are opt-in via `plugins.enabled:` in `~/.hermes/config.yaml` (per the feature-013 flow) | Add `aivg-satellite` under `plugins.enabled:` in the Hermes config. |
| Gateway log shows `Failed to load plugin 'aivg-satellite'` with `refuses to register` | A pre-rebrand vendored `satellite_webrtc/` bundled plugin is also installed (the feature 019 conflict detector firing) | Follow the cleanup verb in the error message: `mv ~/.hermes/hermes-agent/plugins/platforms/satellite_webrtc/ ~/.hermes/backups/` and restart. |

---

## 8. Non-surface promises

The PyPI release ships the post-019 `aivg` codebase. The
following operator-visible properties are **invariant** versus
the editable install at the same git tag (FR-010 / SC-006):

- The same REST paths under `/satellite/*` are served on the
  configured `management_port` (default 8643).
- The same WS path `/satellite/ws` is served.
- The same `satellite:` config block in `~/.hermes/config.yaml`
  is read.
- The same `SATELLITE_*` env vars are read.
- The same `aivg --contract-version` output bytes
  (`{"contract_version":"0.2.0","transports":[...]}`).
- The same plugin registration name `aivg_satellite` in Hermes
  gateway logs.

A diff of `aivg` install via `pip install aivg==X.Y.Z`
vs. `pip install -e .` against the tagged commit MUST produce
zero behaviorally-visible differences. Modulo filesystem-layout
differences inside `site-packages/` (editable installs use a `.pth`
file or `__editable__.<name>.pth` to map back to the source tree;
non-editable installs copy the source into `site-packages/`).
