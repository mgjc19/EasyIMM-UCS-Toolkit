"""
Direct Redfish API push -- bypasses Terraform and calls the BMC Redfish
endpoints directly using HTTP requests.
"""

import json
import urllib3
from typing import Optional

import requests

from redfish_manager import (
    _load_config,
    REDFISH_SCHEMAS,
    build_bios_attributes,
)

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


def _session(endpoint: str, username: str, password: str, insecure: bool):
    """Create an authenticated requests.Session against the BMC."""
    s = requests.Session()
    s.auth = (username, password)
    s.verify = not insecure
    s.headers.update({
        "Content-Type": "application/json",
        "Accept": "application/json",
    })
    s.base_url = endpoint.rstrip("/")
    return s


def _url(session, path: str) -> str:
    return f"{session.base_url}{path}"


def _get(session, path: str) -> dict:
    r = session.get(_url(session, path), timeout=30)
    r.raise_for_status()
    return r.json()


def _patch(session, path: str, payload: dict) -> dict:
    r = session.patch(_url(session, path), json=payload, timeout=30)
    if r.status_code >= 400:
        detail = ""
        try:
            detail = json.dumps(r.json(), indent=2)
        except Exception:
            detail = r.text[:500]
        return {"ok": False, "status": r.status_code, "detail": detail}
    return {"ok": True, "status": r.status_code}


def _post(session, path: str, payload: dict) -> dict:
    r = session.post(_url(session, path), json=payload, timeout=30)
    if r.status_code >= 400:
        detail = ""
        try:
            detail = json.dumps(r.json(), indent=2)
        except Exception:
            detail = r.text[:500]
        return {"ok": False, "status": r.status_code, "detail": detail}
    return {"ok": True, "status": r.status_code}


def push_all_enabled() -> dict:
    """Push all enabled resource configs directly to the BMC via Redfish API."""
    cfg = _load_config()
    server = cfg.get("server", {})
    endpoint = server.get("endpoint", "")
    username = server.get("username", "")
    password = server.get("password", "")
    insecure = server.get("insecure", True)

    if not endpoint or not username or not password:
        return {
            "ok": False,
            "results": [],
            "error": "BMC connection not configured. Save your server connection first.",
        }

    enabled = cfg.get("enabled", [])
    resources = cfg.get("resources", {})

    if not enabled:
        return {"ok": True, "results": [], "message": "No resources are enabled."}

    session = _session(endpoint, username, password, insecure)
    results = []

    for res_key in enabled:
        data = resources.get(res_key, {})
        schema = REDFISH_SCHEMAS.get(res_key)
        if not schema:
            continue
        try:
            result = _push_resource(session, res_key, data)
            results.append({"resource": res_key, "label": schema["label"], **result})
        except requests.exceptions.ConnectionError:
            results.append({
                "resource": res_key,
                "label": schema["label"],
                "ok": False,
                "detail": f"Connection failed to {endpoint}",
            })
        except Exception as e:
            results.append({
                "resource": res_key,
                "label": schema["label"],
                "ok": False,
                "detail": str(e),
            })

    all_ok = all(r.get("ok") for r in results)
    return {"ok": all_ok, "results": results}


def push_single(resource_key: str) -> dict:
    """Push a single resource config directly to the BMC."""
    cfg = _load_config()
    server = cfg.get("server", {})
    endpoint = server.get("endpoint", "")
    username = server.get("username", "")
    password = server.get("password", "")
    insecure = server.get("insecure", True)

    if not endpoint or not username or not password:
        return {"ok": False, "detail": "BMC connection not configured."}

    data = cfg.get("resources", {}).get(resource_key, {})
    schema = REDFISH_SCHEMAS.get(resource_key)
    if not schema:
        return {"ok": False, "detail": f"Unknown resource: {resource_key}"}

    session = _session(endpoint, username, password, insecure)
    try:
        return _push_resource(session, resource_key, data)
    except requests.exceptions.ConnectionError:
        return {"ok": False, "detail": f"Connection failed to {endpoint}"}
    except Exception as e:
        return {"ok": False, "detail": str(e)}


def _push_resource(session, res_key: str, data: dict) -> dict:
    """Dispatch a single resource push to the correct Redfish endpoint."""
    system_id = data.get("system_id", "system")

    if res_key == "bios":
        attrs = build_bios_attributes(data)
        if not attrs:
            return {"ok": True, "detail": "No BIOS attributes to change", "skipped": True}
        return _patch(session, f"/redfish/v1/Systems/{system_id}/Bios/Settings",
                       {"Attributes": attrs})

    if res_key == "boot_order":
        payload = {}
        uefi_sb = data.get("uefi_secure_boot")
        if uefi_sb:
            payload["Boot"] = {"UefiSecureBoot": uefi_sb == "Enabled"}
        otbd = data.get("one_time_boot_device")
        if otbd:
            payload.setdefault("Boot", {})["BootSourceOverrideTarget"] = otbd
            payload["Boot"]["BootSourceOverrideEnabled"] = "Once"
        devices = data.get("boot_devices", [])
        if devices:
            boot_order = [d.get("id") for d in devices if d.get("id")]
            if boot_order:
                payload.setdefault("Boot", {})["BootOrder"] = boot_order
        if not payload:
            return {"ok": True, "detail": "No boot changes to apply", "skipped": True}
        return _patch(session, f"/redfish/v1/Systems/{system_id}", payload)

    if res_key == "power":
        desired = data.get("desired_power_state", "on")
        action_map = {
            "on": "On", "off": "ForceOff", "ForceOn": "ForceOn", "ForceOff": "ForceOff",
            "GracefulShutdown": "GracefulShutdown", "ForceRestart": "ForceRestart",
            "GracefulRestart": "GracefulRestart", "Nmi": "Nmi",
            "PushPowerButton": "PushPowerButton",
        }
        reset_type = action_map.get(desired, "On")
        return _post(session,
                      f"/redfish/v1/Systems/{system_id}/Actions/ComputerSystem.Reset",
                      {"ResetType": reset_type})

    if res_key == "identify_led":
        active = data.get("identify_led", False)
        state = "Lit" if active else "Off"
        return _patch(session, f"/redfish/v1/Systems/{system_id}",
                       {"IndicatorLED": state})

    if res_key == "secure_boot":
        payload = {"SecureBootEnable": data.get("secure_boot_enabled", False)}
        return _patch(session, f"/redfish/v1/Systems/{system_id}/SecureBoot", payload)

    if res_key == "bios_reset":
        if not data.get("reset_bios_to_default"):
            return {"ok": True, "detail": "Reset not requested", "skipped": True}
        return _post(session,
                      f"/redfish/v1/Systems/{system_id}/Bios/Actions/Bios.ResetBios", {})

    if res_key == "bmc_settings":
        manager_id = data.get("manager_id", "c885a")
        patches = {}
        ntp = data.get("ntp_servers")
        if ntp:
            patches["NTP"] = {"NTPServers": ntp}
        if patches:
            result = _patch(session, f"/redfish/v1/Managers/{manager_id}/NetworkProtocol", patches)
            if not result.get("ok"):
                return result
        if data.get("reset_bmc"):
            return _post(session,
                          f"/redfish/v1/Managers/{manager_id}/Actions/Manager.Reset",
                          {"ResetType": "GracefulRestart"})
        return {"ok": True, "status": 200}

    if res_key == "bmc_network_protocol":
        manager_id = data.get("manager_id", "c885a")
        payload = {}
        for proto, key in [("SSH", "ssh"), ("HTTPS", "https"), ("IPMI", "ipmi"),
                           ("KVMIP", "kvmip"), ("SNMP", "snmp")]:
            enabled_key = f"{key}_enabled"
            port_key = f"{key}_port"
            if enabled_key in data:
                payload[proto] = {
                    "ProtocolEnabled": data[enabled_key],
                    "Port": data.get(port_key, 0),
                }
        if not payload:
            return {"ok": True, "detail": "No protocol changes", "skipped": True}
        return _patch(session, f"/redfish/v1/Managers/{manager_id}/NetworkProtocol", payload)

    if res_key == "virtual_media":
        if not data.get("mount_virtual_media"):
            return {"ok": True, "detail": "Virtual media mount not requested", "skipped": True}
        manager_id = data.get("manager_id", "c885a")
        media_id = data.get("virtual_media_id", "CD0")
        payload = {
            "Image": data.get("virtual_media_image_url", ""),
            "TransferProtocolType": data.get("virtual_media_transfer_protocol", "HTTPS"),
            "WriteProtected": data.get("virtual_media_write_protected", True),
        }
        return _patch(session,
                       f"/redfish/v1/Managers/{manager_id}/VirtualMedia/{media_id}", payload)

    if res_key == "log_service":
        if not data.get("clear_event_log"):
            return {"ok": True, "detail": "Log clear not requested", "skipped": True}
        manager_id = data.get("manager_id", "c885a")
        log_id = data.get("log_service_id", "EventLog")
        return _post(session,
                      f"/redfish/v1/Managers/{manager_id}/LogServices/{log_id}/Actions/LogService.ClearLog",
                      {})

    if res_key == "event_subscription":
        if not data.get("create_event_subscription"):
            return {"ok": True, "detail": "Subscription not requested", "skipped": True}
        payload = {
            "Destination": data.get("event_subscription_destination", ""),
            "Protocol": data.get("event_subscription_protocol", "Redfish"),
            "Context": data.get("event_subscription_context", ""),
            "EventTypes": data.get("event_subscription_types", ["Alert"]),
        }
        return _post(session, "/redfish/v1/EventService/Subscriptions", payload)

    return {"ok": False, "detail": f"Direct push not implemented for: {res_key}"}
