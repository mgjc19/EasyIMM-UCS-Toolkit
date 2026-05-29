"""
Intersight live-sync engine.

Pulls full resource bodies from Intersight via the SDK, maps them through
``intersight_mapper``, and writes the result into per-domain ``.ezi.yaml``
files so the Easy IMM tree reflects what is actually deployed.

Each connected Intersight domain gets its own folder under
``<EASYIMM_ROOT>/domains/<fqdn>/`` with the standard Easy IMM directory
layout (``organizations/``, ``pools/``, ``policies/``, ``profiles/``,
``templates/``).
"""

import logging
import shutil
import threading
import time
from pathlib import Path
from typing import Any

from intersight_mapper import MAPPERS, map_resource
from yaml_manager import YAMLManager, EASYIMM_ROOT

logger = logging.getLogger(__name__)

DOMAINS_ROOT = EASYIMM_ROOT / "domains"

_sync_lock = threading.Lock()

_sync_state: dict[str, Any] = {
    "status": "idle",
    "last_synced": None,
    "error": None,
    "synced_counts": {},
    "progress": None,
    "domain": None,
}


def _domain_dir(fqdn: str) -> Path:
    """Return the per-domain folder path, creating the skeleton if needed."""
    safe_name = fqdn.replace("https://", "").replace("http://", "").rstrip("/")
    domain_path = DOMAINS_ROOT / safe_name
    return domain_path


def _scaffold_domain(domain_path: Path) -> None:
    """Create the standard Easy IMM directory skeleton inside a domain folder."""
    for subdir in ("organizations", "pools", "policies", "profiles", "templates"):
        (domain_path / subdir).mkdir(parents=True, exist_ok=True)


def get_sync_status() -> dict:
    """Return current sync state (thread-safe copy)."""
    with _sync_lock:
        return dict(_sync_state)


def list_synced_domains() -> list[dict]:
    """Return metadata for every synced domain folder."""
    if not DOMAINS_ROOT.exists():
        return []
    domains = []
    for d in sorted(DOMAINS_ROOT.iterdir()):
        if not d.is_dir():
            continue
        yaml_count = len(list(d.rglob("*.ezi.yaml")))
        domains.append({
            "name": d.name,
            "path": str(d),
            "resource_files": yaml_count,
        })
    return domains


def unsync_domain(fqdn: str) -> dict:
    """Remove a synced domain folder and all its .ezi.yaml files."""
    domain_path = _domain_dir(fqdn)
    if not domain_path.exists():
        return {"ok": False, "error": f"Domain folder not found: {fqdn}"}
    shutil.rmtree(domain_path)
    logger.info("Unsynced domain: %s (removed %s)", fqdn, domain_path)
    return {"ok": True, "removed": str(domain_path)}


def run_sync(
    api_key_id: str,
    secret_key: str,
    endpoint: str = "https://intersight.com",
    org_filter: str | None = None,
) -> dict:
    """Execute a full sync from Intersight into per-domain .ezi.yaml files.

    Creates ``domains/<fqdn>/`` with the standard Easy IMM folder layout
    and writes synced resources there.
    """
    fqdn = endpoint.replace("https://", "").replace("http://", "").rstrip("/")

    with _sync_lock:
        if _sync_state["status"] == "running":
            return {"ok": False, "error": "Sync already in progress"}
        _sync_state["status"] = "running"
        _sync_state["error"] = None
        _sync_state["progress"] = "connecting"
        _sync_state["domain"] = fqdn

    try:
        from intersight_client import IntersightClient, RESOURCE_ENDPOINTS
    except ImportError:
        _set_error("Intersight SDK not installed. Run: pip install intersight")
        return {"ok": False, "error": _sync_state["error"]}

    client = None
    try:
        client = IntersightClient(api_key_id, secret_key, endpoint)

        conn = client.test_connection()
        if not conn.get("ok"):
            _set_error(f"Connection failed: {conn.get('error', 'unknown')}")
            return {"ok": False, "error": _sync_state["error"]}

        domain_path = _domain_dir(fqdn)
        _scaffold_domain(domain_path)

        yaml_mgr = YAMLManager(root=str(domain_path))
        counts: dict[str, int] = {}
        total_mapped = 0

        categories = list(RESOURCE_ENDPOINTS.keys())
        for category in categories:
            types = RESOURCE_ENDPOINTS[category]
            for resource_type in types:
                if (category, resource_type) not in MAPPERS:
                    continue

                with _sync_lock:
                    _sync_state["progress"] = f"{category}/{resource_type}"

                items = client.list_resources(
                    category, resource_type,
                    org_filter=org_filter, full=True,
                )

                for item in items:
                    cfg = item.get("config", {})
                    if not cfg:
                        continue
                    org_name = item.get("organization", "default")

                    mapped = map_resource(category, resource_type, cfg)
                    if mapped is None:
                        continue

                    yaml_mgr.create_organization(org_name)
                    yaml_mgr.save_resource(org_name, category, resource_type, mapped)

                    key = f"{category}/{resource_type}"
                    counts[key] = counts.get(key, 0) + 1
                    total_mapped += 1

        with _sync_lock:
            _sync_state["status"] = "idle"
            _sync_state["last_synced"] = time.time()
            _sync_state["synced_counts"] = counts
            _sync_state["progress"] = None
            _sync_state["error"] = None
            _sync_state["domain"] = fqdn

        logger.info(
            "Intersight sync complete for %s: %d resources mapped into %s",
            fqdn, total_mapped, domain_path,
        )
        return {"ok": True, "total": total_mapped, "counts": counts, "domain": fqdn}

    except Exception as exc:
        logger.exception("Sync failed")
        _set_error(str(exc))
        return {"ok": False, "error": str(exc)}
    finally:
        if client:
            client.close()


def _set_error(msg: str):
    with _sync_lock:
        _sync_state["status"] = "error"
        _sync_state["error"] = msg
        _sync_state["progress"] = None
