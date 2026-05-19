# Phase 1 Data Model: TTS Text-Strip Seam

No persistence, no schema, no new shared models (constitution II models
unchanged). The only "data" is the in-flight text flow at one seam.

## Text flow (per spoken unit)

```
Raw Reply Text  ──(display/transcript: UNCHANGED, FR-006)──────────────▶ shown/recorded as-is
      │
      └─(speech copy only)─▶ _strip_markdown_for_tts(text)  ─▶ Spoken Text ─▶ text_to_speech_tool ─▶ audio
                                   (Hermes-owned transform)      │
                                                                 └─ empty/whitespace ─▶ skip unit (FR-007)
        import/strip raises ─▶ Spoken Text := Raw (un-stripped)  ────────────────────▶ synth (FR-008)
```

## Entities (transient, in-process)

| Entity | Definition | Rules |
|---|---|---|
| **Raw Reply Text** | The agent's reply text as produced (per unit on the 008 path; the completed reply segmented on the 006 path). | Source of truth for display + transcript; **never mutated** for display/record (FR-006). |
| **Spoken Text** | `tools.tts_tool._strip_markdown_for_tts(Raw)` | Equals that function's output exactly — no added transform (FR-003). Sent to `text_to_speech_tool`. If empty/whitespace → unit skipped, not synthesised (FR-007). |
| **Reused Hermes Helper** | `tools.tts_tool._strip_markdown_for_tts` | External, Hermes-owned. Its behaviour IS the spec; not re-implemented or re-tested locally (constitution IV). Unavailable/raises ⇒ fall back to Raw (FR-008). |
| **Speakable Unit** | Reused from features 006/008 — per-sentence chunk passed to `tts_synthesize`. | Unit boundaries unchanged; strip applied per unit; both speech paths funnel through `tts_synthesize` so coverage is automatic (FR-001/FR-002). |

## State / lifecycle

None. Pure per-call function application at `HermesV013Bridge.`
`tts_synthesize`; no session state, no config, no transitions, no
ordering concerns (one unit in → one audio out, identical to today minus
the markdown characters).
