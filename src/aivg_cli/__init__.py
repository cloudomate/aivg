"""``aivg_cli`` — AIVG (AI Voice Gateway) management CLI.

Binary: ``aivg`` (see ``[project.scripts]`` in ``pyproject.toml``).
The legacy binary name ``sat-cli`` is kept as a one-release compat
alias that dispatches here with a stderr deprecation notice.

Speaks the REST API in
``specs/011-satellite-management/contracts/management-api.yaml`` and
the JSON envelope contract in
``specs/011-satellite-management/contracts/cli-contract.md``.

Constitution v2.0.1 Principle IV: this package MUST NOT import any
specific agent-platform plugin (Hermes, OpenClaw, future).
"""

__all__ = ["__version__"]
__version__ = "0.3.0"
