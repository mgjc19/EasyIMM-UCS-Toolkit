"""
Easy IMM Frontend -- FastAPI backend.
Serves the API for the React frontend and runs Terraform commands.
"""

import asyncio
import json
import logging
import os
import re
from pathlib import Path
from typing import Optional

import yaml as pyyaml
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from fastapi.responses import FileResponse, Response

from schema_engine import SchemaEngine
from yaml_manager import YAMLManager
from terraform_runner import TerraformRunner
from paths import EASYIMM_ROOT

logger = logging.getLogger(__name__)

STATIC_DIR = Path(__file__).resolve().parent / "static"


app = FastAPI(title="Easy IMM Frontend")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

schema_engine = SchemaEngine()
yaml_mgr = YAMLManager()
tf_runner = TerraformRunner()


class ResourcePayload(BaseModel):
    data: dict


class ClonePayload(BaseModel):
    src_org: str
    dst_org: str
    category: str
    resource_type: str
    src_name: str
    dst_name: str


class OrgPayload(BaseModel):
    name: str


class SettingsPayload(BaseModel):
    api_key_id: str
    secret_key: str
    intersight_fqdn: str = "intersight.com"


class ImportPayload(BaseModel):
    org_filter: Optional[str] = None
    categories: Optional[list] = None


class SyncPayload(BaseModel):
    org_filter: Optional[str] = None


class RedfishServerPayload(BaseModel):
    endpoint: str
    username: str
    password: str
    insecure: bool = True


class RedfishResourcePayload(BaseModel):
    resource_key: str
    data: dict


# ── Schema endpoints ──

@app.get("/api/schema/types")
def get_all_types():
    return schema_engine.get_all_types()


@app.get("/api/schema/{category}/{resource_type}")
def get_resource_schema(category: str, resource_type: str):
    result = schema_engine.get_resource_schema(resource_type, category)
    if not result.get("fields"):
        raise HTTPException(404, f"Schema not found for {category}/{resource_type}")
    return result


# ── Tree / org endpoints ──

@app.get("/api/tree")
def get_resource_tree():
    tree = yaml_mgr.get_resource_tree()
    moid_map = _resolve_moid_names()
    if moid_map:
        tree["_moid_names"] = moid_map
    return tree


def _resolve_moid_names() -> dict:
    """Try to resolve MOID org names from Intersight (best-effort, cached)."""
    import re
    if not hasattr(_resolve_moid_names, "_cache"):
        _resolve_moid_names._cache = {}
    if _resolve_moid_names._cache:
        return _resolve_moid_names._cache
    try:
        client = _get_intersight_client()
        orgs = client.list_organizations()
        mapping = {o["moid"]: o["name"] for o in orgs}
        if mapping:
            _resolve_moid_names._cache = mapping
        return mapping
    except Exception:
        return {}


@app.get("/api/orgs")
def get_organizations():
    return yaml_mgr.get_organizations()


@app.post("/api/orgs")
def create_organization(payload: OrgPayload):
    yaml_mgr.create_organization(payload.name)
    return {"ok": True}


@app.delete("/api/orgs/{org}")
def delete_organization(org: str):
    yaml_mgr.delete_organization(org)
    return {"ok": True}


# ── Resource CRUD endpoints ──

@app.get("/api/resources/{org}")
def get_org_resources(org: str):
    """Return the full resource tree for a single organization."""
    tree = yaml_mgr.get_resource_tree()
    if org not in tree:
        raise HTTPException(404, f"Organization '{org}' not found")
    return tree[org]


@app.get("/api/resources/{org}/{category}/{resource_type}")
def get_resources(org: str, category: str, resource_type: str):
    return yaml_mgr.get_resources(org, category, resource_type)


@app.post("/api/resources/{org}/{category}/{resource_type}")
def save_resource(org: str, category: str, resource_type: str, payload: ResourcePayload):
    yaml_mgr.save_resource(org, category, resource_type, payload.data)
    return {"ok": True}


@app.delete("/api/resources/{org}/{category}/{resource_type}/{name}")
def delete_resource(org: str, category: str, resource_type: str, name: str):
    ok = yaml_mgr.delete_resource(org, category, resource_type, name)
    if not ok:
        raise HTTPException(404, "Resource not found")
    return {"ok": True}


@app.post("/api/resources/clone")
def clone_resource(payload: ClonePayload):
    try:
        yaml_mgr.clone_resource(
            payload.src_org, payload.dst_org, payload.category,
            payload.resource_type, payload.src_name, payload.dst_name,
        )
        return {"ok": True}
    except ValueError as e:
        raise HTTPException(404, str(e))


# ── Settings endpoints ──

@app.get("/api/settings")
def get_settings():
    env_path = EASYIMM_ROOT / "env.sh"
    settings = {"api_key_id": "", "secret_key": "", "intersight_fqdn": "intersight.com"}
    if env_path.exists():
        with open(env_path) as f:
            for line in f:
                line = line.strip()
                if "intersight_api_key_id" in line and "=" in line:
                    settings["api_key_id"] = line.split("=", 1)[1].strip("'\" \n")
                elif "intersight_secret_key" in line and "=" in line:
                    settings["secret_key"] = line.split("=", 1)[1].strip("'\" \n")
    gs_path = EASYIMM_ROOT / "global_settings.ezi.yaml"
    if gs_path.exists():
        with open(gs_path) as f:
            gs = pyyaml.safe_load(f)
        if isinstance(gs, dict):
            fqdn = gs.get("global_settings", {}).get("intersight_fqdn")
            if fqdn:
                settings["intersight_fqdn"] = fqdn
    return settings


@app.put("/api/settings")
def save_settings(payload: SettingsPayload):
    env_path = EASYIMM_ROOT / "env.sh"
    lines = [
        "#!/bin/bash",
        "# Easy IMM credentials -- managed by Frontend-app",
        f'export TF_VAR_intersight_api_key_id="{payload.api_key_id}"',
        f'export TF_VAR_intersight_secret_key="{payload.secret_key}"',
        "",
    ]
    with open(env_path, "w") as f:
        f.write("\n".join(lines))
    return {"ok": True}


@app.post("/api/settings/test")
async def test_connection():
    """Test Intersight API connectivity by running terraform validate."""
    result = await tf_runner.run("validate")
    if result["success"]:
        return {"ok": True, "message": "Connection successful -- Terraform validate passed."}
    output = result.get("output", "")
    if "intersight_api_key_id" in output or "secretkey" in output.lower():
        return {"ok": False, "message": "Authentication failed. Check your API Key ID and Secret Key path."}
    return {"ok": False, "message": f"Validation failed:\n{output[:500]}"}


# ── Terraform endpoints ──

@app.post("/api/terraform/{action}")
async def run_terraform(action: str):
    valid_actions = ("init", "validate", "plan", "apply", "destroy", "state_list")
    if action not in valid_actions:
        raise HTTPException(400, f"Invalid action: {action}")
    result = await tf_runner.run(action)
    return result


@app.websocket("/ws/terraform")
async def ws_terraform(websocket: WebSocket):
    await websocket.accept()
    try:
        while True:
            msg = await websocket.receive_text()
            data = json.loads(msg)
            action = data.get("action")
            valid_actions = ("init", "validate", "plan", "apply", "destroy", "state_list")
            if action not in valid_actions:
                await websocket.send_json({"type": "error", "data": f"Invalid: {action}"})
                continue

            async def send_line(line):
                await websocket.send_json({"type": "output", "data": line})

            await websocket.send_json({"type": "start", "action": action})
            result = await tf_runner.run(action, callback=send_line)
            await websocket.send_json({
                "type": "done",
                "success": result["success"],
                "exit_code": result.get("exit_code"),
            })
    except WebSocketDisconnect:
        await tf_runner.cancel()


# ── Intersight Import endpoints ──

def _get_intersight_client():
    """Create an IntersightClient from the current saved settings."""
    env_path = EASYIMM_ROOT / "env.sh"
    api_key_id = ""
    secret_key = ""
    intersight_fqdn = "intersight.com"

    if env_path.exists():
        with open(env_path) as f:
            for line in f:
                line = line.strip()
                if "intersight_api_key_id" in line and "=" in line:
                    api_key_id = line.split("=", 1)[1].strip("'\" \n")
                elif "intersight_secret_key" in line and "=" in line:
                    secret_key = line.split("=", 1)[1].strip("'\" \n")

    gs_path = EASYIMM_ROOT / "global_settings.ezi.yaml"
    if gs_path.exists():
        with open(gs_path) as f:
            gs = pyyaml.safe_load(f)
        if isinstance(gs, dict):
            fqdn = gs.get("global_settings", {}).get("intersight_fqdn")
            if fqdn:
                intersight_fqdn = fqdn

    if not api_key_id or not secret_key:
        raise HTTPException(400, "API credentials not configured. Go to Settings first.")

    try:
        from intersight_client import IntersightClient
        return IntersightClient(api_key_id, secret_key, f"https://{intersight_fqdn}")
    except ImportError:
        raise HTTPException(
            500,
            "Intersight SDK not installed. Run: pip install intersight",
        )


@app.post("/api/import/test")
def import_test_connection():
    """Test Intersight API connectivity via the SDK."""
    client = _get_intersight_client()
    try:
        result = client.test_connection()
        return result
    finally:
        client.close()


@app.get("/api/import/orgs")
def import_list_orgs():
    """List organizations from Intersight."""
    client = _get_intersight_client()
    try:
        return client.list_organizations()
    finally:
        client.close()


@app.post("/api/import/resources")
def import_list_resources(payload: ImportPayload):
    """List all resources from Intersight, optionally filtered by org."""
    client = _get_intersight_client()
    try:
        all_res = client.list_all_resources(org_filter=payload.org_filter)
        if payload.categories:
            all_res = {k: v for k, v in all_res.items() if k in payload.categories}
        total = sum(len(items) for cat in all_res.values() for items in cat.values())
        return {"resources": all_res, "total": total}
    finally:
        client.close()


@app.get("/api/import/resources/{category}/{resource_type}")
def import_list_resources_by_type(category: str, resource_type: str, org: str = None):
    """List resources of a specific type from Intersight."""
    client = _get_intersight_client()
    try:
        items = client.list_resources(category, resource_type, org_filter=org)
        return items
    finally:
        client.close()


# ── Intersight Sync endpoints ──

import intersight_sync
from concurrent.futures import ThreadPoolExecutor

_sync_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="isync")


@app.post("/api/sync")
def trigger_sync(payload: SyncPayload):
    """Start a background sync from Intersight into local .ezi.yaml files."""
    status = intersight_sync.get_sync_status()
    if status["status"] == "running":
        raise HTTPException(409, "Sync already in progress")

    env_path = EASYIMM_ROOT / "env.sh"
    api_key_id = ""
    secret_key = ""
    intersight_fqdn = "intersight.com"

    if env_path.exists():
        with open(env_path) as f:
            for line in f:
                line = line.strip()
                if "intersight_api_key_id" in line and "=" in line:
                    api_key_id = line.split("=", 1)[1].strip("'\" \n")
                elif "intersight_secret_key" in line and "=" in line:
                    secret_key = line.split("=", 1)[1].strip("'\" \n")

    gs_path = EASYIMM_ROOT / "global_settings.ezi.yaml"
    if gs_path.exists():
        with open(gs_path) as f:
            gs = pyyaml.safe_load(f)
        if isinstance(gs, dict):
            fqdn = gs.get("global_settings", {}).get("intersight_fqdn")
            if fqdn:
                intersight_fqdn = fqdn

    if not api_key_id or not secret_key:
        raise HTTPException(400, "API credentials not configured. Go to Settings first.")

    _sync_executor.submit(
        intersight_sync.run_sync,
        api_key_id, secret_key,
        f"https://{intersight_fqdn}",
        payload.org_filter,
    )
    return {"ok": True, "message": "Sync started"}


@app.get("/api/sync/status")
def sync_status():
    """Return current sync state."""
    return intersight_sync.get_sync_status()


@app.get("/api/sync/domains")
def list_synced_domains():
    """List all synced Intersight domain folders."""
    return intersight_sync.list_synced_domains()


@app.delete("/api/sync/domains/{domain_name}")
def unsync_domain(domain_name: str):
    """Remove a synced domain folder (unsync)."""
    result = intersight_sync.unsync_domain(domain_name)
    if not result.get("ok"):
        raise HTTPException(404, result.get("error", "Unsync failed"))
    return result


# ── Redfish configuration endpoints ──

import redfish_manager
import redfish_direct
import docascode_exporter

@app.get("/api/redfish/schemas")
def get_redfish_schemas():
    """Return all Redfish resource type schemas for form generation."""
    return redfish_manager.get_schemas()


@app.get("/api/redfish/server")
def get_redfish_server():
    return redfish_manager.get_server_config()


@app.put("/api/redfish/server")
def save_redfish_server(payload: RedfishServerPayload):
    redfish_manager.save_server_config(
        payload.endpoint, payload.username, payload.password, payload.insecure,
    )
    return {"ok": True}


@app.get("/api/redfish/config")
def get_all_redfish_configs():
    """Return all resource configurations with their current values."""
    return redfish_manager.get_all_resource_configs()


@app.get("/api/redfish/config/{resource_key}")
def get_redfish_config(resource_key: str):
    cfg = redfish_manager.get_resource_config(resource_key)
    if not cfg:
        raise HTTPException(404, f"Unknown resource: {resource_key}")
    return cfg


@app.put("/api/redfish/config/{resource_key}")
def save_redfish_config(resource_key: str, payload: RedfishResourcePayload):
    redfish_manager.save_resource_config(resource_key, payload.data)
    return {"ok": True}


@app.get("/api/redfish/live")
def read_redfish_live():
    """Read the current live state from the BMC for all resource types."""
    return redfish_direct.read_live_state()


@app.post("/api/redfish/direct-push")
def direct_push_all():
    """Push all enabled resource configs directly to the BMC via Redfish API."""
    return redfish_direct.push_all_enabled()


@app.post("/api/redfish/direct-push/{resource_key}")
def direct_push_single(resource_key: str):
    """Push a single resource config directly to the BMC via Redfish API."""
    return redfish_direct.push_single(resource_key)


@app.post("/api/redfish/generate")
def generate_redfish_tf():
    """Generate Terraform files from current Redfish configuration."""
    return redfish_manager.generate_terraform_files()


@app.post("/api/redfish/terraform/{action}")
async def run_redfish_terraform(action: str):
    valid_actions = ("init", "validate", "plan", "apply", "destroy", "state_list")
    if action not in valid_actions:
        raise HTTPException(400, f"Invalid action: {action}")
    result = await redfish_manager.run_terraform(action)
    return result


@app.websocket("/ws/redfish/terraform")
async def ws_redfish_terraform(websocket: WebSocket):
    await websocket.accept()
    try:
        while True:
            msg = await websocket.receive_text()
            data = json.loads(msg)
            action = data.get("action")
            valid_actions = ("init", "validate", "plan", "apply", "destroy", "state_list")
            if action not in valid_actions:
                await websocket.send_json({"type": "error", "data": f"Invalid: {action}"})
                continue

            async def send_line(line):
                await websocket.send_json({"type": "output", "data": line})

            await websocket.send_json({"type": "start", "action": action})
            result = await redfish_manager.run_terraform(action, callback=send_line)
            await websocket.send_json({
                "type": "done",
                "success": result["success"],
                "exit_code": result.get("exit_code"),
            })
    except WebSocketDisconnect:
        pass


# ── Document-as-Code export endpoints ──


@app.get("/api/export/tech-shared")
def export_tech_shared():
    """Export data.tech-shared.yaml for CiscoIQ."""
    data = docascode_exporter.export_tech_shared()
    content = docascode_exporter.export_to_yaml(data)
    return Response(
        content=f"---\n{content}",
        media_type="application/x-yaml",
        headers={"Content-Disposition": "attachment; filename=data.tech-shared.yaml"},
    )


@app.get("/api/export/tech-ucs")
def export_tech_ucs():
    """Export data.tech-ucs.yaml for CiscoIQ."""
    data = docascode_exporter.export_tech_ucs()
    content = docascode_exporter.export_to_yaml(data)
    return Response(
        content=f"---\n{content}",
        media_type="application/x-yaml",
        headers={"Content-Disposition": "attachment; filename=data.tech-ucs.yaml"},
    )


@app.get("/api/export/preview/tech-shared")
def preview_tech_shared():
    """Preview data.tech-shared.yaml content as JSON."""
    return docascode_exporter.export_tech_shared()


@app.get("/api/export/preview/tech-ucs")
def preview_tech_ucs():
    """Preview data.tech-ucs.yaml content as JSON."""
    return docascode_exporter.export_tech_ucs()


# ── Serve built frontend (SPA) ──

if STATIC_DIR.exists():
    app.mount("/assets", StaticFiles(directory=str(STATIC_DIR / "assets")), name="assets")

    @app.get("/{full_path:path}")
    async def spa_fallback(full_path: str):
        """Serve index.html for any non-API path (SPA routing)."""
        file_path = STATIC_DIR / full_path
        if full_path and file_path.exists() and file_path.is_file():
            return FileResponse(str(file_path))
        return FileResponse(str(STATIC_DIR / "index.html"))
