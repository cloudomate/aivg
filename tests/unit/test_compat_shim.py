"""Feature 012 T025 — compat-shim behavior.

The rebrand keeps three compat shims alive for one release:

* ``satellite_core`` → ``aivg_core``
* ``sat_cli`` → ``aivg_cli``
* ``hermes_satellite_adapter`` → ``aivg_core`` (two-hop; carried over from
  feature 011)

Each shim MUST emit exactly **one** :class:`DeprecationWarning` per
process and re-export the public surface of the new package. The
``sat-cli`` legacy binary additionally writes a one-line stderr notice
(never stdout, so JSON consumers stay clean).
"""

from __future__ import annotations

import importlib
import json
import os
import subprocess
import sys
import warnings
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]


def _subprocess_python(*args: str) -> subprocess.CompletedProcess:
    env = {**os.environ, "PYTHONPATH": str(REPO_ROOT / "src")}
    return subprocess.run(
        [sys.executable, *args], cwd=REPO_ROOT, env=env, capture_output=True, text=True
    )


def _fresh_subprocess_import(code: str) -> subprocess.CompletedProcess:
    # Run the import in a SUBPROCESS so the per-process sentinel isn't
    # poisoned by another test. -W default re-enables all warnings.
    return _subprocess_python("-W", "default", "-c", code)


def test_satellite_core_shim_warns_once_and_reexports():
    code = (
        "import warnings; w = warnings.catch_warnings(record=True);\n"
        "w.__enter__(); warnings.simplefilter('always');\n"
        "import satellite_core; import satellite_core; import satellite_core;\n"  # 3 imports → 1 warning
        "import satellite_core.models as m;\n"
        "msgs = [str(x.message) for x in w._filters_mutated.__self__] if False else [str(x.message) for x in __import__('warnings').filters];\n"
        "# count from the recorder instead\n"
        "print('OK', any('renamed' in str(x.message) for x in w.__enter__.__self__._filters_mutated.__self__ if False))\n"
    )
    # Simpler approach: small inline harness.
    code = """
import warnings, sys
with warnings.catch_warnings(record=True) as w:
    warnings.simplefilter('always')
    import satellite_core
    import satellite_core   # second import: must NOT re-warn
    from satellite_core import models  # noqa
deprecations = [x for x in w if issubclass(x.category, DeprecationWarning) and 'satellite_core' in str(x.message)]
assert len(deprecations) == 1, f"expected 1 DeprecationWarning, got {len(deprecations)}"
assert 'aivg_core' in str(deprecations[0].message), f"warning must point at aivg_core: {deprecations[0].message}"
print('OK')
"""
    res = _fresh_subprocess_import(code)
    assert res.returncode == 0, res.stderr
    assert res.stdout.strip().endswith("OK")


def test_sat_cli_shim_warns_once_and_reexports():
    code = """
import warnings
with warnings.catch_warnings(record=True) as w:
    warnings.simplefilter('always')
    import sat_cli
    import sat_cli
    from sat_cli import cli  # noqa
deprecations = [x for x in w if issubclass(x.category, DeprecationWarning) and 'sat_cli' in str(x.message)]
assert len(deprecations) == 1
assert 'aivg_cli' in str(deprecations[0].message)
print('OK')
"""
    res = _fresh_subprocess_import(code)
    assert res.returncode == 0, res.stderr
    assert res.stdout.strip().endswith("OK")


def test_hermes_satellite_adapter_shim_warns_once_and_reexports():
    code = """
import warnings
with warnings.catch_warnings(record=True) as w:
    warnings.simplefilter('always')
    import hermes_satellite_adapter
    import hermes_satellite_adapter
    from hermes_satellite_adapter import models  # noqa
deprecations = [x for x in w if issubclass(x.category, DeprecationWarning) and 'hermes_satellite_adapter' in str(x.message)]
assert len(deprecations) == 1
assert 'aivg_core' in str(deprecations[0].message)
print('OK')
"""
    res = _fresh_subprocess_import(code)
    assert res.returncode == 0, res.stderr
    assert res.stdout.strip().endswith("OK")


def test_sat_cli_legacy_binary_stderr_notice_never_stdout():
    """The legacy ``sat-cli`` binary MUST emit its deprecation notice on
    stderr only — stdout (where the JSON envelope goes) stays clean.
    """
    # We call ``sat_cli.cli.legacy_app`` directly so the test does not
    # depend on the pyproject script being installed (pyproject scripts
    # only resolve after ``pip install``).
    code = """
import sys
sys.argv = ['sat-cli', '--json', '--version']
import sat_cli.cli as L
try:
    L.legacy_app()
except SystemExit:
    pass
"""
    res = _fresh_subprocess_import(code)
    # Stdout: exactly one JSON envelope, byte-equivalent to `aivg`'s.
    out = res.stdout.strip()
    env = json.loads(out.splitlines()[-1])
    assert env["ok"] is True
    assert env["data"]["contract_version"] == "1.0.0"
    # Stderr: must mention the rename and the new binary name.
    assert "aivg" in res.stderr, f"expected deprecation notice on stderr: {res.stderr!r}"
    assert "Hermes Voice" not in out, "deprecation prose must not leak into stdout"


def test_sat_cli_legacy_stderr_notice_only_once_per_process():
    code = """
import sys
sys.argv = ['sat-cli', '--json', '--version']
import sat_cli.cli as L
# Invoke twice in the same process; the stderr notice MUST appear only
# once (cached on sys.__dict__).
for _ in range(2):
    try:
        L.legacy_app()
    except SystemExit:
        pass
"""
    res = _fresh_subprocess_import(code)
    # Stderr should contain the rename phrase exactly once.
    n_notices = res.stderr.count("sat-cli is renamed to aivg")
    assert n_notices == 1, f"expected 1 stderr notice, got {n_notices}: {res.stderr!r}"
