"""``sat_cli`` — platform-neutral satellite management CLI.

Binary: ``sat-cli`` (see ``[project.scripts]`` in ``pyproject.toml``).
Speaks the REST API in
``specs/011-satellite-management/contracts/management-api.yaml`` and the
JSON envelope contract in
``specs/011-satellite-management/contracts/cli-contract.md``. Constitution
v2.0.0 Principle IV: this package MUST NOT import any specific agent
platform plugin.
"""

__all__ = ["__version__"]
__version__ = "0.1.0"
