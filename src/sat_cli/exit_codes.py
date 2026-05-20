"""Documented ``sat-cli`` exit codes (R-9, cli-contract.md).

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
}


def map_error_to_exit_code(code: str | None) -> int:
    if code is None:
        return OK
    return _ERROR_CODE_TO_EXIT.get(code, BAD_INPUT)
