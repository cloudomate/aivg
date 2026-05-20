"""Dev entrypoint: `python -m aivg_core --dev-fake-bridge`.

Local/test harness ONLY. In production the adapter is loaded by the
active agent-platform gateway (v1: Hermes; see ``adapter.register``),
never started this way.
"""

from __future__ import annotations

import argparse
import asyncio
import sys


def _build_dev_adapter():
    from .adapter import SatelliteWebRTCAdapter

    # Import the fake bridge from the test package only in dev mode.
    sys.path.insert(0, "tests")
    from fakes import FakeHermesBridge  # type: ignore

    return SatelliteWebRTCAdapter(bridge=FakeHermesBridge())


async def _amain(args: argparse.Namespace) -> int:
    if not args.dev_fake_bridge:
        print(
            "Refusing to start: the real Hermes bridge is gated behind "
            "VG-1..VG-4. Use --dev-fake-bridge for local runs.",
            file=sys.stderr,
        )
        return 2
    adapter = _build_dev_adapter()
    adapter.cfg.enabled = True
    await adapter.start()
    print(
        f"[dev] satellite_webrtc adapter up — management:"
        f"{adapter.cfg.management_port} webrtc:{adapter.cfg.webrtc_port}"
    )
    try:
        await asyncio.Event().wait()
    finally:
        await adapter.stop()
    return 0


def main() -> int:
    p = argparse.ArgumentParser(prog="aivg_core")
    p.add_argument("--dev-fake-bridge", action="store_true")
    args = p.parse_args()
    return asyncio.run(_amain(args))


if __name__ == "__main__":
    raise SystemExit(main())
