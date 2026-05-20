"""Feature 004: adapter serves BOTH planes, or fails loudly (FR-003/004/005).

aiohttp isn't a test dependency, so we inject a tiny fake `aiohttp.web` into
sys.modules: enough for build_*_app + AppRunner/TCPSite lifecycle. The
regression-prone logic (two runners; signaling-bind-failure tears down mgmt
and raises — the feature-003 defect) is fully exercised here. Real binding is
proven on the host by the extended deploy post-verify (constitution V).
"""

import sys
import types

import pytest

from aivg_core.config import SatelliteAdapterConfig

pytestmark = pytest.mark.asyncio


def _install_fake_aiohttp(fail_port=None):
    cleaned = []

    class _App:
        def add_routes(self, _routes):  # build_*_app calls this
            pass

    class _Runner:
        def __init__(self, app):
            self.app = app
        async def setup(self):
            pass
        async def cleanup(self):
            cleaned.append(self)

    class _Site:
        def __init__(self, runner, host, port):
            self.port = port
        async def start(self):
            if fail_port is not None and self.port == fail_port:
                raise OSError(f"address in use :{self.port}")

    web = types.SimpleNamespace(
        Application=_App,
        AppRunner=_Runner,
        TCPSite=_Site,
        json_response=lambda *a, **k: None,
        Response=lambda *a, **k: None,
        post=lambda *a, **k: None,
        get=lambda *a, **k: None,
        delete=lambda *a, **k: None,
    )
    mod = types.ModuleType("aiohttp")
    mod.web = web
    sys.modules["aiohttp"] = mod
    return cleaned


@pytest.fixture
def adapter_cfg():
    return SatelliteAdapterConfig(enabled=True, management_port=8643, webrtc_port=8644)


def _make_adapter(cfg):
    from fakes import FakeHermesBridge
    from aivg_core.adapter import SatelliteWebRTCAdapter

    async def _tf(sdp, device_id):  # unused during start()
        raise NotImplementedError

    # Feature 015: SatelliteWebRTCAdapter takes a platform (the
    # AgentPlatform Protocol) instead of a Hermes-bridge. FakeHermesBridge
    # dual-implements both surfaces.
    return SatelliteWebRTCAdapter(platform=FakeHermesBridge(), cfg=cfg, transport_factory=_tf)


async def test_build_signaling_app_exposes_webrtc_routes():
    _install_fake_aiohttp()
    import importlib

    from aivg_core.webrtc import signaling as sig
    importlib.reload(sig)
    # Build with a dummy service; the call must succeed and wire 3 routes.
    captured = {}

    class _App:
        def add_routes(self, routes):
            captured["n"] = len(routes)

    sig_web = sys.modules["aiohttp"].web
    sig_web.Application = _App
    app = sig.build_signaling_app(object())
    assert app is not None and captured["n"] == 3  # offer, candidate, status


async def test_start_registers_both_planes_and_stop_cleans_both(adapter_cfg):
    cleaned = _install_fake_aiohttp()
    a = _make_adapter(adapter_cfg)
    await a.start()
    assert len(a._sites) == 2, "both control + signaling sites must be up (FR-003)"
    await a.stop()
    assert len(cleaned) == 2 and a._sites == [], "stop() cleans both (FR-004)"


async def test_signaling_bind_failure_raises_and_tears_down_mgmt(adapter_cfg):
    # Signaling port fails to bind → adapter must NOT be half-up (FR-005/SC-005).
    cleaned = _install_fake_aiohttp(fail_port=adapter_cfg.webrtc_port)
    a = _make_adapter(adapter_cfg)
    with pytest.raises(RuntimeError, match="signaling site failed to bind"):
        await a.start()
    assert a._sites == [], "no half-up: sites list cleared"
    assert len(cleaned) == 1, "the already-started management runner was torn down"


async def test_disabled_adapter_starts_nothing():
    _install_fake_aiohttp()
    a = _make_adapter(SatelliteAdapterConfig(enabled=False))
    await a.start()
    assert a._sites == []
