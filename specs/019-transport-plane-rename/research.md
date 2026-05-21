# Phase 0 — Research

**Feature**: 019-transport-plane-rename · **Date**: 2026-05-21

Four ADRs back the implementation. Each documents the decision,
the rationale, and the alternatives that were considered and
rejected.

---

## R-1: How does the conflict detector observe the legacy plugin?

### Decision

The conflict detector calls **Hermes's own plugin manager API**
(`hermes_cli.plugins.get_plugin_manager().list_plugins()`) and
scans for a plugin whose manifest declares the legacy bundled
satellite — keyed by the manifest name `"satellite-webrtc-platform"`
(the value in the pre-rebrand `plugin.yaml`'s `name:` field) AND
`source == "bundled"`.

### Rationale

- The Hermes plugin manager already loaded and parsed
  `~/.hermes/hermes-agent/plugins/platforms/*/plugin.yaml` before
  the entry-point plugin's `register()` is ever invoked.
  Re-walking the filesystem to find the same data would duplicate
  Hermes's work.
- Constitution Principle IV ("Reuse the upstream agent platform,
  don't rebuild its primitives") applies to plugin discovery
  too. Hermes owns plugin discovery; we consume the result.
- Today's `hermes plugins list` output is structurally identical
  to what the conflict detector needs — we verified this during
  the 2026-05-21 diagnosis session:
  ```python
  m = get_plugin_manager()
  for p in m.list_plugins():
      if p['name'] == 'satellite-webrtc-platform' and p['source'] == 'bundled':
          # conflict
  ```
- If Hermes ever changes its plugin scan logic (adds a new
  layout, deprecates `plugin.yaml` for a TOML alternative, etc.),
  the detector inherits the change for free — instead of drifting
  silently.

### Alternatives rejected

- **Filesystem stat on
  `~/.hermes/hermes-agent/plugins/platforms/satellite_webrtc/plugin.yaml`**.
  Rejected because: (a) the directory name may differ from the
  manifest name in pathological renames, (b) it doesn't catch a
  bundled plugin that's been moved to a sibling directory but
  still loaded, (c) couples us to Hermes's filesystem layout
  rather than its public API.
- **Check after `ctx.register_platform()` returns**. Rejected
  because by the time we'd notice, the bundled plugin has
  already bound to ports 8643/8644 — too late to recover
  cleanly.
- **Read `~/.hermes/config.yaml` `plugins.enabled` list directly
  and check for `aivg-satellite`-only**. Rejected because the
  legacy bundled plugin is `kind=platform` and auto-loads even
  when not in `plugins.enabled` (per
  `hermes_cli.plugins:925`: bundled platforms bypass the
  opt-in gate). Reading `plugins.enabled` doesn't see this
  auto-load path.

---

## R-2: What does `register()` do when a conflict is detected?

### Decision

**Raise `RuntimeError` from the plugin entry-point's `register()`**,
with a message that names:

1. The conflicting bundled plugin's manifest name.
2. The expected filesystem location of its directory (best-effort,
   from the plugin manager's `path` field if present).
3. The recommended cleanup verb (`mv ~/.hermes/hermes-agent/plugins/platforms/satellite_webrtc/ ~/.hermes/backups/` or equivalent).
4. The reason the conflict matters (both plugins would bind to
   the same management/signaling ports; silent shadowing was the
   trap we hit in the 2026-05-21 deploy session).

The Hermes plugin loader treats exceptions from `register()` as
a plugin-load failure, logs them to `~/.hermes/logs/gateway.log`,
and continues loading other plugins. The gateway boots without
the satellite platform; the operator immediately sees the error
and can clean up.

### Rationale

- **Loud failure is the explicit anti-fix for today's silent
  shadow.** The whole reason this detector exists is that the
  pre-019 deploy ran for hours with two plugins coexisting,
  Hermes happily serving the wrong one, and no log line that
  told us about it. Raising is the loudest signal available.
- **Hermes already handles plugin-`register()` exceptions
  cleanly.** Verified by reading `hermes_cli/plugins.py` —
  `_load_plugin` wraps the call in try/except and surfaces the
  failure on `plugin_manager.list_plugins()` as
  `enabled=True, error="<exception text>"`. Operators see this
  in `hermes plugins list` and in the gateway log.
- **Error message contains the cleanup verb.** Operator's path
  forward is "read error → run the named command → restart" —
  three steps, no guessing.

### Alternatives rejected

- **Silently skip `ctx.register_platform(...)`, log a warning**.
  Rejected because (a) "log a warning, don't fail" is what got
  us into today's silent shadow in the first place, (b) the
  warning would be one line in a noisy log; operators miss
  warnings, they don't miss boot failures.
- **Call `ctx.register_platform(..., check_fn=lambda: False)`**.
  Rejected because `check_fn` is Hermes's "is the dependency
  available" gate (used today for `aiortc`), not a "should I
  even register" gate. Repurposing it muddies its semantics.
- **Halt the gateway entirely (`sys.exit`)**. Rejected because
  it would prevent the rest of Hermes from starting (e.g., the
  IRC/Telegram/Discord platforms unrelated to AIVG). The
  satellite plugin failing to load should not take down
  unrelated platforms.

---

## R-3: Should the Python class `SatelliteWebRTCAdapter` rename too?

### Decision

**Yes — rename the class to `AivgSatelliteAdapter`**, and add a
one-line back-compat alias at module scope:

```python
SatelliteWebRTCAdapter = AivgSatelliteAdapter
```

The alias stays for one release (or until any documented external
importer is known to have migrated), then is removed in a trivial
PR.

### Rationale

- **Consistency**: the registration name, the class name, the
  gateway log lines, and the dev-mode banner string in
  `__main__.py` all converge on the same canonical identifier
  (`aivg_satellite`). Leaving the class name as `SatelliteWebRTC*`
  introduces a name-mismatch where future readers have to mentally
  translate.
- **Cheap reversibility**: a 1-line alias is enough to keep every
  existing `from aivg_core.adapter import SatelliteWebRTCAdapter`
  import working. The cost of keeping the alias is one line plus
  one `# Removed in v0.X.Y` comment.
- **Test surface**: `tests/unit/test_adapter_sites.py` already
  imports the class directly — the alias prevents that test from
  breaking on day-1 of the rename. The test gains a parallel
  assertion that confirms the new class name works.

### Alternatives rejected

- **Don't rename the class; only rename the `name = "..."` string
  attribute.** Rejected because the class itself becomes a
  cognitive landmine — readers seeing `SatelliteWebRTCAdapter`
  in tracebacks or imports would assume it's a stale name and
  hesitate to touch it. Internal cosmetic consistency is worth
  the back-compat alias's one line.
- **Rename the class without a back-compat alias.** Rejected
  because we can't audit every downstream consumer of
  `aivg_core.adapter` outside this repo. The cost of the alias
  is trivial; the cost of a surprise downstream breakage is
  meaningful.

---

## R-4: What does `get_chat_info()` return for the `platform` field?

### Decision

**Return `"aivg_satellite"`** (matching the new registration name).

### Rationale

- `get_chat_info()` is called by Hermes when routing messages and
  surfacing chat metadata to the agent loop. The string is
  free-form metadata, not a wire-format-stable identifier:
  Hermes consumes it for display and routing, not as a join key
  against any persisted record.
- The chat session itself is keyed by `Platform.LOCAL` (Hermes's
  closed enum), set at
  `src/aivg_core/adapter.py:204` via `super().__init__(config, Platform.LOCAL)`.
  Existing chat history is therefore safe — it's keyed by
  `Platform.LOCAL`, not by the free-form `platform` string in
  `get_chat_info`.
- Keeping the old string `"satellite_webrtc"` here would create a
  third surface (after the registration name and the gateway log
  line) where the rename is incomplete, defeating R-3's
  consistency rationale.
- Verified by reading `aivg_core/adapter.py:275-278` — the
  function returns `{"chat_id": chat_id, "chat_type": "dm",
  "platform": "satellite_webrtc"}`. The `platform` field is a
  cosmetic display string; no persistence keys off it.

### Alternatives rejected

- **Keep `"satellite_webrtc"` for one release as a "stable
  identifier" deprecation alias.** Rejected because (a) there is
  no documented external consumer of this string, (b) the rest
  of 019 explicitly avoids deprecation-alias machinery (per the
  clarification session), (c) every other identifier renames
  immediately — the `platform` field is one of three places that
  should agree.
- **Read the canonical name from a single source-of-truth
  constant (e.g., `CANONICAL_PLUGIN_NAME` in setup.py).**
  Accepted in principle — the implementation MAY refactor the
  three call sites (`adapter.py:31`, `adapter.py:277`,
  `adapter.py:295`, `plugin_entrypoint/adapter.py:53`) to read
  from a shared constant. This is a tasks-phase decision, not a
  research-phase one. The binding research result is "all four
  sites carry the value `aivg_satellite`."

---

## Cross-cutting non-issues (recorded for completeness)

- **`Platform.LOCAL` enum value is unchanged.** Hermes's
  `gateway.config.Platform` is a CLOSED enum and 019 does NOT
  add a `Platform.AIVG_SATELLITE` member. We continue to reuse
  `Platform.LOCAL` (the generic/uncategorised one), which is the
  pattern feature 015 established and verified against
  hermes-agent v0.13.0.
- **`PlatformEntry(plugin_name=...)` field**. At
  `src/aivg_core/adapter.py:300` the `PlatformEntry` carries
  `plugin_name="hermes_satellite_adapter"`. This is the
  legacy hermes-adapter Python package name (long since renamed
  to `aivg_core`). Update to `plugin_name="aivg_core"` is
  cosmetic; Hermes uses this field only for diagnostic display.
- **`build_platform_entry()` location**. Lives at
  `src/aivg_core/adapter.py:171`. Only the `name="..."` argument
  to `PlatformEntry(...)` changes; the function signature, return
  type, and call site (`plugin_entrypoint/adapter.py:51` —
  `entry = build_platform_entry()`) all stay.