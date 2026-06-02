# Contracts: gRPC Satellite Transport (feature 021)

Canonical, language-neutral wire schemas. These are the **single source of
truth** (FR-001): both the Python gateway (`aivg_core.transports.grpc`) and the
C++ native client (in the `aivg-devices` repo) generate bindings from the same
files, so the contract cannot drift.

| File | Plane | Phase | Status |
|---|---|---|---|
| `audio.proto` | Voice / audio plane (`Audio.Stream`) | 1 (MVP) | normative |
| `management.proto` | Control / management plane (`Management`) | 2 | design-ahead |

## Canonical location (on implementation)

Ships verbatim to repo root:

```
proto/aivg/satellite/v1/audio.proto
proto/aivg/satellite/v1/management.proto
```

`aivg-devices` vendors `proto/` (copy or git-subtree) for its C++ codegen.

## Codegen (Python, gateway side)

`scripts/gen_proto.sh` runs:

```sh
python -m grpc_tools.protoc \
  -I proto \
  --python_out=src/aivg_core/transports/grpc/_generated \
  --grpc_python_out=src/aivg_core/transports/grpc/_generated \
  proto/aivg/satellite/v1/audio.proto \
  proto/aivg/satellite/v1/management.proto
```

Generated stubs are **checked into git** so `pip install aivg` needs no
`protoc`. `tests/contract/test_grpc_contract.py` regenerates and diffs to prove
the checked-in stubs match the `.proto` (no drift).

## Versioning rules (FR-004)

- **Additive only.** New fields / new `enum` kinds get **new tag numbers**.
- Never renumber, reuse, or change the type of an existing tag.
- `reserved` removed tags/names.
- The package is `aivg.satellite.v1`; a breaking change would be a new
  `v2` package, not an edit in place.

## Relationship to the AIVG contract-version envelope

Shipping + advertising `grpc` bumps the `aivg --contract-version` envelope
**0.2.0 → 0.3.0** (additive minor; same shape as feature 017's ESPHome
`1.0.0→1.1.0`). The proto `package` version (`v1`) and the product
contract-version envelope are independent axes.

## Proto3 note

The proposal sketched event enums starting at `0` for a real value
(`WAKE_FIRED = 0`). proto3 requires the zero value to be the default/unset
sentinel, so each enum here leads with `KIND_UNSPECIFIED = 0` and real kinds
start at `1`. This is the only intentional deviation from the proposal's
sketch.
