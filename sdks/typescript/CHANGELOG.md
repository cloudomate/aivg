# Changelog

All notable changes to `@aivg/sat-sdk` are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- **0.1.0 (in progress)** — initial release, feature 014.
  - `Satellite` class with `connect()`, `disconnect()`, `beginSession()`,
    `endSession()`, `getConfig()`, `setConfig()`.
  - Control-plane WebSocket client with exponential-back-off reconnect.
  - Voice-plane WebRTC offerer flow (full-gather → POST `/webrtc/offer`).
  - State machine: `idle | listening | speaking | error`.
  - Adoption flow `pending → adopted`.
  - Typed event surface (`adoption`, `state`, `config_changed`, `command`,
    `log`, `ota_manifest`, `ota_progress`, `transcript`, `tool_call`,
    `skill`, `error`, `transient_error`, `session_started`,
    `session_ended`, `remote_stream`).
  - Async-iterator sugar: `transcripts()`, `logs()`, `states()`.
  - WebRTC + audio-sink dependency injection (DI holes per R-1/R-9).
  - Browser + Electron + Node targets. No native deps.
  - Contract version: `1.0.0` (matches `aivg --contract-version`).

[Unreleased]: https://github.com/cloudomate/aivg/compare/HEAD
