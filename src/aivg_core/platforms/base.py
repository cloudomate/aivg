"""``AgentPlatform`` — the constitution v2.0.0 Principle IV plugin seam.

See ``specs/011-satellite-management/contracts/agent-platform.md``.

This module is the **only** plugin-related symbol the satellite core
imports. Concrete plugins live under ``aivg_core/platforms/<name>/``
and expose a module-level ``PLATFORM: AgentPlatform`` singleton. The
loader selects one by name at startup via ``~/.satellite/config.yaml``
``platform:``; no other discovery mechanism in v1 (R-15).

Structural typing via ``typing.Protocol`` (PEP 544) means a plugin does
NOT need to inherit from ``AgentPlatform`` — exposing the named methods
is enough. Practical consequence: the existing
:class:`aivg_core.platforms.hermes.bridge.HermesBridge` is already
structurally close; a thin ``HermesAgentPlatform`` adapter (in
``platforms/hermes/__init__.py``) renames its methods to the canonical
``AgentPlatform`` names so a single core can target both plugins.
"""

from __future__ import annotations

import importlib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, AsyncIterator, Optional, Protocol, runtime_checkable

__all__ = [
    "AgentPlatform",
    "EndpointResult",
    "AllProvidersUnavailable",
    "PluginRegistry",
    "load_platform",
    "_validate_agent_platform",
    # Feature 013 — deploy-layer companion to AgentPlatform.
    "SetupCapability",
    "DetectResult",
    "SetupOptions",
    "SetupPhase",
    "PreflightReport",
    "InstallResult",
    "UninstallResult",
    "ParityCheckResult",
    "RollbackResult",
    "PHASE_NAMES",
    "SetupError",
]


class AllProvidersUnavailable(RuntimeError):
    """Plugin-neutral base exception: every configured provider (and its
    fallbacks) failed for this verb. Plugins raise it; the voice loop
    catches it and emits a perceptible failure (FR-015) rather than a
    hung session. Lifted from the Hermes plugin to ``platforms/base``
    in feature 015 so the satellite core can import it without
    tripping the SC-006 "no .hermes. imports outside the plugin" gate;
    the bridge re-exports it for backward compat with existing tests."""


@dataclass(frozen=True)
class EndpointResult:
    """Per-frame endpoint detection signal (feature 015 / R-1).

    Returned by :meth:`AgentPlatform.endpoint`. Carries both
    ``end_of_utterance`` (the constitutional primary field) and
    ``speech_started`` (consumed by the voice loop's barge-in watcher to
    detect the first non-silent frame within the current turn). Frozen
    so plugins can return literals cheaply.
    """

    end_of_utterance: bool
    speech_started: bool = False


@runtime_checkable
class AgentPlatform(Protocol):
    """Pluggable agent-platform integration (constitution v2.0.0 IV).

    Implementations MUST NOT leak provider/SDK types across this
    boundary — only the Python primitives below cross it.
    """

    name: str
    """Stable lowercase identifier, e.g. ``'hermes'``, ``'openclaw'``."""

    async def startup(self, *, gateway_config: dict) -> None:
        """Called once when the satellite adapter starts.

        Implementations open whatever long-lived resources the platform
        requires (provider warm-up, etc). MUST NOT raise on a recoverable
        error; the next call will retry."""

    async def transcribe(self, audio: bytes, *, sample_rate: int) -> str:
        """ASR: PCM16 mono → text. Sample rates: 16000 or 48000."""

    def agent_step(
        self,
        text: str,
        session_id: str,
        *,
        history: Optional[list[dict]] = None,
    ) -> AsyncIterator[str]:
        """User text → streaming reply text deltas. Implementations
        stream as soon as the platform produces tokens (feature 008
        streaming seam) and yield clean prose suitable for TTS — markdown
        stripping is the platform's responsibility (constitution I)."""

    async def synthesize(self, text: str) -> bytes:
        """TTS: text → Opus or PCM (negotiated at startup)."""

    async def endpoint(self, frame: bytes) -> "EndpointResult":
        """Server-side end-of-utterance + speech-start signal for one
        incoming PCM frame. Returns :class:`EndpointResult` (frozen
        dataclass: ``end_of_utterance``, ``speech_started``).
        Implementations delegate to the platform's existing silence
        algorithm (constitution I rule).

        Feature 015 / R-1: returning a richer dataclass (vs bare bool)
        preserves the ``speech_started`` field the voice loop's
        barge-in watcher consumes."""

    async def shutdown(self) -> None:
        """Idempotent teardown."""


class PluginRegistry:
    """Tiny dynamic loader. Explicit-config, no entry-point magic in v1."""

    @staticmethod
    def load(name: str) -> AgentPlatform:
        """Import ``aivg_core.platforms.<name>`` and return its
        module-level ``PLATFORM`` attribute. Raises a clear ``RuntimeError``
        on missing/misconfigured plugins."""
        if not name or not name.isidentifier():
            raise RuntimeError(
                f"Invalid agent platform name {name!r} — expected a Python "
                f"identifier (e.g. 'hermes', 'openclaw')."
            )
        try:
            module = importlib.import_module(f"aivg_core.platforms.{name}")
        except ImportError as exc:
            raise RuntimeError(
                f"Unknown agent platform {name!r}: "
                f"aivg_core.platforms.{name} could not be imported "
                f"({exc}). Available plugins: hermes, openclaw."
            ) from exc
        plat = getattr(module, "PLATFORM", None)
        if plat is None:
            raise RuntimeError(
                f"Platform plugin {name!r} does not expose a module-level "
                f"`PLATFORM` symbol. See "
                f"specs/011-satellite-management/contracts/agent-platform.md."
            )
        if getattr(plat, "name", None) != name:
            raise RuntimeError(
                f"Platform plugin {name!r}: `PLATFORM.name` is "
                f"{getattr(plat, 'name', None)!r}, expected {name!r}."
            )
        return plat


def load_platform(name: str) -> AgentPlatform:
    """Convenience shim, identical to :meth:`PluginRegistry.load`."""
    return PluginRegistry.load(name)


_REQUIRED_VERBS = ("transcribe", "agent_step", "synthesize", "endpoint")


def _validate_agent_platform(plat: AgentPlatform) -> None:
    """Fail-fast check (feature 015 / R-4 / FR-007): the loaded plugin
    exposes every required canonical verb as a callable, plus a
    non-empty lowercase ``name``. Called from
    :class:`SatelliteWebRTCAdapter` at startup so a misconfigured
    plugin can never accept a single inbound frame.

    Raises:
        RuntimeError: with the list of missing verbs and a pointer to
            ``specs/015-agentplatform-runtime-closure/contracts/agent-platform.md``.
    """
    missing = [v for v in _REQUIRED_VERBS if not callable(getattr(plat, v, None))]
    name = getattr(plat, "name", None)
    if not isinstance(name, str) or not name or name != name.lower():
        missing.append("name (non-empty lowercase str)")
    if missing:
        raise RuntimeError(
            f"AgentPlatform {name!r} is missing required verb(s) / attribute(s): "
            f"{', '.join(missing)}. See "
            f"specs/015-agentplatform-runtime-closure/contracts/agent-platform.md."
        )


# =============================================================================
# Feature 013 — SetupCapability (deploy-layer companion to AgentPlatform)
# =============================================================================
#
# AgentPlatform is the RUNTIME seam (voice loop talks through it).
# SetupCapability is the DEPLOY-TIME seam (`aivg setup` installs the
# satellite plugin INTO an agent platform). A plugin can implement
# either, neither, or both — runtime and deploy are independent
# capabilities (constitution v2.0.0 Principle IV applied to the
# install path).
#
# See `specs/013-aivg-setup-cli/contracts/platform-setup.md`.

# Closed set of phase names every `aivg setup` invocation can emit
# (data-model.md §2 "Phase set"). Clients (the agent skill, tests)
# key off this set; adding a name is a minor contract bump.
PHASE_NAMES: frozenset[str] = frozenset({
    # Install / uninstall / rollback share these.
    "detecting",
    "preflight",
    "confirming",
    "backup",
    # Install-only.
    "vendoring",           # legacy (pre-013 / shell-script-era plugins)
    "pip_installing",      # feature 013 — Hermes-native pip + entry-point
    "config_writing",
    "enabling_plugin",     # feature 013 — register in Hermes plugins.enabled
    "installing_deps",
    "restarting_gateway",
    "post_verifying",
    # Uninstall-only.
    "uninstall_vendor",    # legacy mirror of `vendoring`
    "pip_uninstalling",    # feature 013 — mirror of `pip_installing`
    "disabling_plugin",    # feature 013 — remove from Hermes plugins.enabled
    "uninstall_config",
    "uninstall_restart",
    # Rollback-only.
    "restoring",
    # Parity-check.
    "parity_check",
    # Terminal.
    "done",
    "failed",
})


@dataclass
class DetectResult:
    """Read-only result of :meth:`SetupCapability.detect`.

    ``is_installed`` answers "is this agent platform on the host?" —
    not "is AIVG already installed into it?". The latter is checked by
    :meth:`SetupCapability.preflight` via the install marker file.
    """

    is_installed: bool
    paths: dict[str, str] = field(default_factory=dict)
    version: Optional[str] = None
    reasons: list[str] = field(default_factory=list)


@dataclass
class SetupOptions:
    """Cross-cutting flags parsed once by the CLI; passed through to
    every per-platform setup method so plugins don't re-parse argv."""

    yes: bool = False
    force: bool = False
    legacy_hermes: bool = False
    no_tune: bool = False
    json_mode: bool = False
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass
class SetupPhase:
    """One progress event emitted by a plugin during install/uninstall/
    rollback. The CLI wraps these in the v1 JSON envelope (one per
    ``started`` transition + one per terminal ``ok|skipped|failed``)."""

    name: str
    status: str  # "started" | "ok" | "skipped" | "failed"
    detail: Optional[dict[str, Any]] = None

    def __post_init__(self) -> None:
        if self.name not in PHASE_NAMES:
            raise ValueError(
                f"unknown phase name {self.name!r}; allowed: "
                f"{sorted(PHASE_NAMES)}"
            )
        if self.status not in ("started", "ok", "skipped", "failed"):
            raise ValueError(f"invalid phase status {self.status!r}")


@dataclass
class PreflightReport:
    """Read-only summary of what an install/uninstall *would* do.
    ``intended_changes`` is the operator-facing bullet list; the agent
    skill renders it for in-chat confirmation (US3)."""

    ok: bool
    intended_changes: list[str] = field(default_factory=list)
    blockers: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


@dataclass
class InstallResult:
    ok: bool
    phases: list[SetupPhase] = field(default_factory=list)
    backup_dir: Optional[Path] = None
    rollback_command: Optional[str] = None
    failure_phase: Optional[str] = None
    failure_reason: Optional[str] = None


@dataclass
class UninstallResult:
    ok: bool
    phases: list[SetupPhase] = field(default_factory=list)
    removed: list[str] = field(default_factory=list)
    config_changes: list[str] = field(default_factory=list)
    failure_reason: Optional[str] = None


@dataclass
class ParityCheckResult:
    ok: bool
    expected: str = ""
    observed: str = ""
    notes: list[str] = field(default_factory=list)


@dataclass
class RollbackResult:
    ok: bool
    restored_files: list[str] = field(default_factory=list)
    new_backup_dir: Optional[Path] = None


class SetupError(Exception):
    """Typed plugin-side failure with a stable ``error.code``.

    Maps onto the v1 JSON envelope's ``error`` block. Allowed codes
    are the closed set from
    ``specs/013-aivg-setup-cli/contracts/setup-cli-contract.md``.
    """

    def __init__(self, code: str, message: str, phase: Optional[str] = None) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.phase = phase


@runtime_checkable
class SetupCapability(Protocol):
    """Per-platform install/uninstall interface.

    Constitution v2.0.0 Principle IV at the deploy layer: every
    platform-specific detail (plugin-dir layout, config-block format,
    gateway-restart command, dependency installer) lives in one
    implementation of this Protocol — never in the satellite core or
    in `aivg setup` itself.
    """

    name: str            # stable identifier; matches `aivg_core.platforms.<name>/`
    label: str           # human display, e.g. "Hermes Agent"

    def detect(self) -> DetectResult: ...

    def preflight(self, opts: SetupOptions) -> PreflightReport: ...

    def install(self, opts: SetupOptions) -> InstallResult: ...

    def uninstall(self, opts: SetupOptions) -> UninstallResult: ...

    # Optional (Hermes plugin implements these; OpenClaw stub omits them).
    # def parity_check(self, opts: SetupOptions, *, phrase: str) -> ParityCheckResult: ...
    # def rollback(self, opts: SetupOptions, *, backup_dir: Path) -> RollbackResult: ...


# Extend PluginRegistry with a sibling loader for SetupCapability.

def _load_setup_capability(name: str) -> SetupCapability:
    """Import ``aivg_core.platforms.<name>`` and return its
    module-level ``SETUP`` attribute. Raises
    ``RuntimeError("setup_not_supported_for_platform")`` if the
    plugin exists but exposes no ``SETUP`` symbol.
    """
    if not name or not name.isidentifier():
        raise RuntimeError(
            f"Invalid agent platform name {name!r} — expected a Python "
            f"identifier (e.g. 'hermes', 'openclaw')."
        )
    try:
        module = importlib.import_module(f"aivg_core.platforms.{name}")
    except ImportError as exc:
        raise RuntimeError(
            f"Unknown agent platform {name!r}: "
            f"aivg_core.platforms.{name} could not be imported "
            f"({exc}). Available plugins: hermes, openclaw."
        ) from exc
    setup = getattr(module, "SETUP", None)
    if setup is None:
        raise RuntimeError(
            f"setup_not_supported_for_platform: plugin {name!r} has no "
            f"module-level `SETUP` symbol. See "
            f"specs/013-aivg-setup-cli/contracts/platform-setup.md."
        )
    if not isinstance(setup, SetupCapability):
        raise RuntimeError(
            f"setup_not_supported_for_platform: plugin {name!r} `SETUP` "
            f"does not satisfy the SetupCapability protocol (missing "
            f"required methods)."
        )
    if getattr(setup, "name", None) != name:
        raise RuntimeError(
            f"Plugin {name!r}: `SETUP.name` is {getattr(setup, 'name', None)!r}, "
            f"expected {name!r}."
        )
    return setup


PluginRegistry.load_setup_capability = staticmethod(_load_setup_capability)  # type: ignore[attr-defined]
