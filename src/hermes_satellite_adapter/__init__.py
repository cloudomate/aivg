"""Hermes gateway platform adapter for realtime voice (STT/agent/TTS).

Thin transport + registry layer. STT, the agent loop, TTS, and end-of-utterance
detection are reached ONLY through ``hermes_bridge`` (constitution Principle I).
"""

__all__ = ["__version__"]
__version__ = "0.1.0"
