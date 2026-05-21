"""Documented ``aivg`` exit codes (R-9, cli-contract.md + feature 013
setup-cli-contract.md).

Agents and scripts MUST be able to switch on exit code; collapsing all
failures into ``1`` would make ``device_offline`` indistinguishable from
``bad_input``, which fails FR-016.
"""

from __future__ import annotations

OK = 0
BAD_INPUT = 1
DEVICE_OFFLINE = 2
GATEWAY_UNREACHABLE = 3
BLE_FAILURE = 4
OTA_FAILURE = 5

# Feature 013 — same numeric codes; new error.code values join the
# closed set below.
SETUP_PARTIAL_FAILURE = OTA_FAILURE  # 5: terminal failure with operator follow-up
SETUP_LOCK_HELD = BAD_INPUT  # 1: try again later
NO_PLATFORM_DETECTED = BAD_INPUT
MULTIPLE_PLATFORMS_DETECTED = BAD_INPUT
SETUP_NOT_SUPPORTED_FOR_PLATFORM = BAD_INPUT
PERMISSION_DENIED = BAD_INPUT
HOST_STATE_DRIFTED = BAD_INPUT

# Mapping from JSON envelope `error.code` → exit code.
_ERROR_CODE_TO_EXIT = {
    "bad_input": BAD_INPUT,
    "unknown_device": BAD_INPUT,
    "config_conflict": BAD_INPUT,
    "device_limit_reached": BAD_INPUT,
    "already_adopted": BAD_INPUT,
    "browser_not_ota_eligible": BAD_INPUT,
    "device_offline": DEVICE_OFFLINE,
    "gateway_unreachable": GATEWAY_UNREACHABLE,
    "ble_unavailable": BLE_FAILURE,
    "ble_provisioning_failed": BLE_FAILURE,
    "improv_timeout": BLE_FAILURE,
    "wifi_join_failed": BLE_FAILURE,
    "ota_failed": OTA_FAILURE,
    "rolled_back": OTA_FAILURE,
    "ota_in_progress": BAD_INPUT,
    "internal_error": BAD_INPUT,
    # Feature 013 additions (closed set; see contracts/setup-cli-contract.md).
    "no_platform_detected": BAD_INPUT,
    "multiple_platforms_detected": BAD_INPUT,
    "setup_not_supported_for_platform": BAD_INPUT,
    "setup_lock_held": BAD_INPUT,
    "setup_partial_failure": OTA_FAILURE,
    "permission_denied": BAD_INPUT,
    "host_state_drifted": BAD_INPUT,
}


def map_error_to_exit_code(code: str | None) -> int:
    if code is None:
        return OK
    return _ERROR_CODE_TO_EXIT.get(code, BAD_INPUT)
