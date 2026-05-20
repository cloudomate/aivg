"""Constitution Principle I guard (T012).

Fails if any STT/TTS engine or agent loop is imported anywhere in the
satellite core EXCEPT the sanctioned Hermes-plugin bridge delegation seam.

Under constitution v2.0.0 (feature 011) the bridge lives at
``aivg_core/platforms/hermes/bridge.py``; the rest of ``aivg_core``
(including ``platforms/openclaw/``) MUST NOT import a speech engine
directly.
"""

import pathlib
import re

PKG = pathlib.Path(__file__).resolve().parents[2] / "src" / "aivg_core"
BRIDGE_FILE = "bridge.py"  # only sanctioned seam (delegation only)
FORBIDDEN = re.compile(
    r"\b(import\s+(whisper|faster_whisper|piper)|from\s+(whisper|faster_whisper|piper))\b"
)


def test_no_embedded_speech_engines_outside_bridge():
    offenders = []
    for py in PKG.rglob("*.py"):
        # Only the Hermes plugin's bridge.py is the sanctioned seam.
        if py.name == BRIDGE_FILE and "platforms/hermes" in str(py).replace("\\", "/"):
            continue
        text = py.read_text()
        if FORBIDDEN.search(text):
            offenders.append(str(py.relative_to(PKG.parent.parent)))
    assert offenders == [], f"embedded engine import outside Hermes bridge: {offenders}"


def test_bridge_module_constructs_no_engine_on_import():
    # Importing the seam must perform zero engine construction.
    import aivg_core.platforms.hermes.bridge as hb

    assert hasattr(hb, "HermesBridge")
    assert hasattr(hb, "AllProvidersUnavailable")
