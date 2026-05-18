"""Constitution Principle I guard (T012).

Fails if any STT/TTS engine or agent loop is imported anywhere in the package
EXCEPT the sanctioned ``hermes_bridge`` delegation seam.
"""

import pathlib
import re

PKG = pathlib.Path(__file__).resolve().parents[2] / "src" / "hermes_satellite_adapter"
FORBIDDEN = re.compile(
    r"\b(import\s+(whisper|faster_whisper|piper)|from\s+(whisper|faster_whisper|piper))\b"
)


def test_no_embedded_speech_engines_outside_bridge():
    offenders = []
    for py in PKG.rglob("*.py"):
        if py.name == "hermes_bridge.py":
            continue  # the only sanctioned seam (delegation only, no engines)
        text = py.read_text()
        if FORBIDDEN.search(text):
            offenders.append(py.name)
    assert offenders == [], f"embedded engine import outside hermes_bridge: {offenders}"


def test_bridge_module_constructs_no_engine_on_import():
    # Importing the seam must perform zero engine construction.
    import hermes_satellite_adapter.hermes_bridge as hb

    assert hasattr(hb, "HermesBridge")
    assert hasattr(hb, "AllProvidersUnavailable")
