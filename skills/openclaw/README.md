# OpenClaw-platform satellite management skill (STUB)

Placeholder. Constitution v2.0.0 Principle IV: a per-platform skill ships
alongside its agent-platform plugin. The OpenClaw plugin is a stub
(`src/satellite_core/platforms/openclaw/`) and the corresponding skill is
not yet implemented — this directory exists to prove the seam (and to
catch the day a new platform plugs in: the skill folder, the plugin, and
the CLI binary are three different things, and only the first two are
per-platform).

When OpenClaw is implemented:

1. Land a working `satellite_core.platforms.openclaw.PLATFORM`.
2. Write `SKILL.md` here mirroring `skills/hermes-agent/SKILL.md`.
3. The `sat-cli` binary itself does NOT change — it is platform-neutral.
