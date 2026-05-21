"""Transports layer — sibling of ``aivg_core.platforms`` and
``aivg_core.webrtc``. Hosts non-WebRTC wire transports that route
inbound audio through the canonical :class:`AgentPlatform` Protocol
via the existing :class:`aivg_core.webrtc.session.Session`.

Feature 017 adds the first such sibling: ``transports.esphome`` (the
ESPHome native API server). Future transports (MQTT, gRPC, plain
WebSocket, …) plug in here without touching ``platforms/`` or
``webrtc/session.py``.

The module is intentionally empty at package level; consumers import
the concrete transport class explicitly, e.g.::

    from aivg_core.transports.esphome import EsphomeTransport
"""
