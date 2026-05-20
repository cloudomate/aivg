"""Feature 012 T028 — zero substantive contract drift (US3, SC-003).

Verifies that the AIVG rebrand is a labels-only change at the REST
contract surface:

* every operationId from the documented closed set is present
* every documented schema name is present
* every status code per operation is present
* every documented `error` enum value is present

Failing this test means the rebrand silently dropped or renamed a
contract field — that is a substantive change, not branding, and is
forbidden by FR-007 / SC-003.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml


REPO_ROOT = Path(__file__).resolve().parents[2]
API_YAML = REPO_ROOT / "specs" / "011-satellite-management" / "contracts" / "management-api.yaml"

# The closed set from feature 011's design — these MUST all still be in
# the contract after the rebrand. Adding new ones in a future feature is
# fine; removing/renaming requires a coordinated major bump.
REQUIRED_OPERATION_IDS = {
    "registerDevice",
    "listDevices",
    "getDeviceState",
    "adoptDevice",
    "deleteDevice",
    "getDeviceConfig",
    "postDeviceConfig",
    "getDeviceConfigSchema",
    "postDeviceCommand",
    "getDeviceLogs",
    "getFleetLogs",
    "otaCheck",
    "otaApply",
    "otaStatusReport",
    "getOtaManifest",
}

REQUIRED_SCHEMAS = {
    "DeviceType",
    "AdoptionState",
    "RegisterRequest",
    "RegisterResponse",
    "DeviceSummary",
    "DeviceState",
    "SessionInfo",
    "DeviceConfig",
    "DeviceConfigPatch",
    "AdoptRequest",
    "CommandVerb",
    "CommandRequest",
    "CommandResponse",
    "LogEntry",
    "OtaCheckResult",
    "OtaJob",
    "OtaStatusReport",
    "OtaManifest",
    "ConflictError",
}

REQUIRED_CONFLICT_ERROR_CODES = {
    "device_limit_reached",
    "already_adopted",
    "browser_not_ota_eligible",
    "ota_in_progress",
    "device_offline",
}


@pytest.fixture(scope="module")
def api() -> dict:
    return yaml.safe_load(API_YAML.read_text())


def test_operation_ids_all_present(api):
    found = set()
    for path, methods in api["paths"].items():
        for method, op in methods.items():
            if method.startswith("x-"):
                continue
            if isinstance(op, dict) and "operationId" in op:
                found.add(op["operationId"])
    missing = REQUIRED_OPERATION_IDS - found
    assert not missing, f"contract drifted — missing operationIds: {missing}"


def test_schemas_all_present(api):
    schemas = set((api.get("components") or {}).get("schemas", {}).keys())
    missing = REQUIRED_SCHEMAS - schemas
    assert not missing, f"contract drifted — missing schemas: {missing}"


def test_conflict_error_enum_unchanged(api):
    err_schema = api["components"]["schemas"]["ConflictError"]
    err_values = set(err_schema["properties"]["error"]["enum"])
    missing = REQUIRED_CONFLICT_ERROR_CODES - err_values
    assert not missing, (
        f"contract drifted — ConflictError dropped: {missing}"
    )


def test_info_version_unchanged(api):
    # The rebrand is NOT a contract bump (FR-007 / SC-003).
    assert api["info"]["version"] == "1.0.0", (
        "info.version changed — rebrand is labels-only, this is a "
        "substantive bump masquerading as branding"
    )


def test_info_title_is_aivg_branded(api):
    title = api["info"]["title"]
    assert "AIVG" in title
    assert "Hermes Voice" not in title


def test_openapi_version_unchanged(api):
    assert api["openapi"] == "3.1.0"
