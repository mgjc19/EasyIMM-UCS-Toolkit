"""
Intersight Visualiser — FastAPI backend.

Connects to Cisco Intersight (live API) or parses uploaded UCS
techsupport bundles, and serves the hierarchy to the browser visualizer.

Supports three modes:
  1. Intersight API only (live policies/profiles)
  2. Techsupport only (one or more FI/Chassis/Server/Intersight bundles)
  3. Hybrid: techsupport for physical view + Intersight API for policies
"""

from __future__ import annotations

import asyncio
import copy
import datetime
import html as html_mod
import logging
import os
import queue
import tempfile
import threading
import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from typing import List

from dotenv import load_dotenv
from fastapi import FastAPI, File, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from .data_collector import build_hierarchy, fetch_policy_detail
from .intersight_client import IntersightAuthError, IntersightAPIError, IntersightClient
from .techsupport_parser import TechSupportParser
from .best_practices import DEFAULT_RULES, get_default_rules, run_audit

load_dotenv()
logger = logging.getLogger("intersight-visualiser")

FRONTEND_DIR = Path(__file__).resolve().parent / "frontend"
MAX_UPLOAD_SIZE = 2 * 1024 * 1024 * 1024  # 2 GB

_client: IntersightClient | None = None
_cached_hierarchy: dict | None = None
_uploaded_files: list[str] = []
_parser: TechSupportParser | None = None
_audit_rules: list[dict] | None = None  # user-edited built-in rules (None = use defaults)
_custom_rules: list[dict] = []         # user-added custom rules


@asynccontextmanager
async def lifespan(application: FastAPI):
    global _client
    api_key = os.getenv("INTERSIGHT_API_KEY_ID", "")
    key_path = os.getenv("INTERSIGHT_SECRET_KEY_PATH", "")
    base_url = os.getenv("INTERSIGHT_BASE_URL", "https://intersight.com")

    if api_key and key_path:
        try:
            _client = IntersightClient(api_key, key_path, base_url)
            info = await _client.test_connection()
            logger.info("Auto-connected to Intersight account: %s", info["account_name"])
        except Exception as exc:
            logger.warning("Auto-connect failed (configure via UI): %s", exc)
            _client = None

    yield

    if _client:
        await _client.close()


app = FastAPI(title="Intersight Visualiser", version="1.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Models ──────────────────────────────────────────────────────────────

class ConnectRequest(BaseModel):
    api_key_id: str
    secret_key_path: str
    base_url: str = "https://intersight.com"


# ── Connection endpoints ────────────────────────────────────────────────

@app.post("/api/connect")
async def connect(req: ConnectRequest):
    global _client, _cached_hierarchy

    if _client:
        await _client.close()
        _client = None

    # Preserve techsupport cache for hybrid mode; only clear pure-API cache
    if _cached_hierarchy and not (isinstance(_cached_hierarchy, dict) and "physical" in _cached_hierarchy):
        _cached_hierarchy = None

    try:
        _client = IntersightClient(req.api_key_id, req.secret_key_path, req.base_url)
        info = await _client.test_connection()
        return {"status": "connected", "account_name": info["account_name"]}
    except IntersightAuthError as exc:
        _client = None
        raise HTTPException(status_code=401, detail=str(exc))
    except Exception as exc:
        _client = None
        raise HTTPException(status_code=500, detail=str(exc))


@app.post("/api/disconnect")
async def disconnect():
    global _client, _cached_hierarchy, _uploaded_files, _parser
    if _client:
        await _client.close()
        _client = None
    _cached_hierarchy = None
    _uploaded_files = []
    _parser = None
    return {"status": "disconnected"}


@app.get("/api/status")
async def status():
    has_techsupport = (
        _cached_hierarchy is not None
        and isinstance(_cached_hierarchy, dict)
        and ("physical" in _cached_hierarchy or _cached_hierarchy.get("source") == "techsupport")
    )
    if _client and has_techsupport:
        source = "hybrid"
    elif _client:
        source = "intersight"
    elif has_techsupport:
        source = "techsupport"
    else:
        source = "none"
    return {
        "connected": source != "none",
        "source": source,
        "files": _uploaded_files,
    }


# ── Hierarchy endpoints ─────────────────────────────────────────────────

@app.get("/api/hierarchy")
async def hierarchy(
    org: str | None = Query(None, description="Filter by organization name"),
    refresh: bool = Query(False, description="Force refresh from API"),
    view: str = Query("logical", description="View: physical, logical, errors, or topology (techsupport only)"),
):
    global _cached_hierarchy

    has_techsupport = (
        _cached_hierarchy is not None
        and isinstance(_cached_hierarchy, dict)
        and "physical" in _cached_hierarchy
    )

    if not _client and not _cached_hierarchy:
        raise HTTPException(status_code=400, detail="Not connected — use Intersight API or upload a techsupport bundle")

    # Hybrid mode: logical view comes from live API, physical/errors from techsupport
    if _client and has_techsupport and view == "logical" and (refresh or not _cached_hierarchy.get("_api_logical")):
        try:
            api_tree = await build_hierarchy(_client, org_filter=org)
            _cached_hierarchy["_api_logical"] = api_tree
            return api_tree
        except Exception as exc:
            logger.warning("Hybrid: API fetch failed, falling back to techsupport logical: %s", exc)
            return _cached_hierarchy.get("logical")

    if _client and has_techsupport and view == "logical" and _cached_hierarchy.get("_api_logical"):
        return _cached_hierarchy["_api_logical"]

    if has_techsupport and not refresh and not org:
        chosen = _cached_hierarchy.get(view, _cached_hierarchy.get("logical"))
        return chosen

    if _cached_hierarchy and not isinstance(_cached_hierarchy, dict):
        return _cached_hierarchy

    if not _client:
        raise HTTPException(status_code=400, detail="Not connected to Intersight (techsupport data is cached — no live refresh available)")

    try:
        tree = await build_hierarchy(_client, org_filter=org)
        if not org:
            _cached_hierarchy = tree
        return tree
    except IntersightAuthError as exc:
        raise HTTPException(status_code=401, detail=str(exc))
    except IntersightAPIError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail)
    except Exception as exc:
        logger.exception("Hierarchy build failed")
        raise HTTPException(status_code=500, detail=str(exc))


@app.get("/api/policy/{object_type:path}/{moid}")
async def policy_detail(object_type: str, moid: str):
    if not _client:
        raise HTTPException(status_code=400, detail="Policy details require a live Intersight connection")
    try:
        return await fetch_policy_detail(_client, object_type, moid)
    except IntersightAPIError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail)
    except Exception as exc:
        logger.exception("Policy detail fetch failed")
        raise HTTPException(status_code=500, detail=str(exc))


@app.get("/api/export")
async def export_hierarchy(
    view: str = Query("logical", description="View to export: physical, logical, errors, or all"),
):
    if not _cached_hierarchy:
        raise HTTPException(status_code=400, detail="No hierarchy data — load it first")
    if isinstance(_cached_hierarchy, dict) and "physical" in _cached_hierarchy:
        if view == "all":
            content = _cached_hierarchy
        else:
            content = _cached_hierarchy.get(view, _cached_hierarchy.get("logical"))
    else:
        content = _cached_hierarchy
    return JSONResponse(
        content=content,
        headers={"Content-Disposition": f"attachment; filename=intersight_{view}.json"},
    )


# ── Techsupport upload ──────────────────────────────────────────────────

ALLOWED_EXTS = {".tar.gz", ".tgz", ".tar", ".zip", ".gz", ".json.gz", ".json", ".xml"}


def _suffix_for(filename: str) -> str:
    lower = filename.lower()
    if lower.endswith(".json.gz"):
        return ".json.gz"
    if lower.endswith((".tar.gz", ".tgz")):
        return ".tar.gz"
    return Path(lower).suffix


async def _save_upload(file: UploadFile) -> tuple[str, str]:
    """Save an UploadFile to a temp file; return (temp_path, suffix)."""
    if not file.filename:
        raise HTTPException(status_code=400, detail="No file provided")

    lower_name = file.filename.lower()
    if not any(lower_name.endswith(ext) for ext in ALLOWED_EXTS):
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported: {file.filename}. Accepted: {', '.join(sorted(ALLOWED_EXTS))}",
        )

    suffix = _suffix_for(file.filename)
    tmp = tempfile.NamedTemporaryFile(suffix=suffix, delete=False)
    try:
        size = 0
        while chunk := await file.read(1024 * 1024):
            size += len(chunk)
            if size > MAX_UPLOAD_SIZE:
                tmp.close()
                os.unlink(tmp.name)
                raise HTTPException(status_code=413, detail="File too large (max 2 GB)")
            tmp.write(chunk)
        tmp.flush()
        tmp.close()
        logger.info("Saved upload: %s (%d MB)", file.filename, size // (1024 * 1024))
        return tmp.name, file.filename
    except HTTPException:
        raise
    except Exception:
        tmp.close()
        os.unlink(tmp.name)
        raise


@app.post("/api/upload")
async def upload_techsupport(files: List[UploadFile] = File(...)):
    """Upload and parse one or more techsupport bundles with SSE progress stream."""
    global _cached_hierarchy, _uploaded_files, _parser

    _cached_hierarchy = None
    _uploaded_files = []

    saved: list[tuple[str, str]] = []
    try:
        for f in files:
            saved.append(await _save_upload(f))
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Upload error: {exc}")

    progress_q: queue.Queue[str | None] = queue.Queue()

    def _progress_cb(msg: str):
        progress_q.put(msg)

    def _parse_worker():
        global _cached_hierarchy, _uploaded_files, _parser
        try:
            _parser = TechSupportParser(on_progress=_progress_cb)
            for tmp_path, filename in saved:
                _progress_cb(f"▶ Parsing: {filename}")
                _parser.parse(tmp_path, filename=filename)
                _uploaded_files.append(filename)
            _progress_cb("Building visualization trees…")
            _cached_hierarchy = _parser.build_trees()
            _progress_cb("__DONE__")
        except Exception as exc:
            logger.exception("Techsupport parse failed")
            _progress_cb(f"__ERROR__:{exc}")
        finally:
            progress_q.put(None)
            for tmp_path, _ in saved:
                try:
                    os.unlink(tmp_path)
                except OSError:
                    pass

    thread = threading.Thread(target=_parse_worker, daemon=True)
    thread.start()

    async def _event_stream():
        loop = asyncio.get_event_loop()
        while True:
            msg = await loop.run_in_executor(None, progress_q.get)
            if msg is None:
                break
            yield f"data: {msg}\n\n"

    return StreamingResponse(
        _event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.post("/api/upload/add")
async def upload_add(files: List[UploadFile] = File(...)):
    """Add more techsupport files to the current session (incremental merge)."""
    global _cached_hierarchy, _uploaded_files, _parser

    if _parser is None:
        _parser = TechSupportParser()

    saved: list[tuple[str, str]] = []
    try:
        for f in files:
            saved.append(await _save_upload(f))

        for tmp_path, filename in saved:
            logger.info("Parsing additional techsupport: %s", filename)
            _parser.parse(tmp_path, filename=filename)
            _uploaded_files.append(filename)

        _cached_hierarchy = _parser.build_trees()
        return {
            "status": "parsed",
            "files": _uploaded_files,
            "file_count": len(_uploaded_files),
            "source": "techsupport",
        }

    except HTTPException:
        raise
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        logger.exception("Techsupport parse failed")
        raise HTTPException(status_code=500, detail=f"Parse error: {exc}")
    finally:
        for tmp_path, _ in saved:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass


# ── Best Practices Audit ─────────────────────────────────────────────────

def _build_effective_rules(rule_type: str | None = None) -> list[dict]:
    """Build the effective rule list by merging user edits and custom rules
    with the built-in defaults, preserving internal 'check' keys."""
    defaults = DEFAULT_RULES
    if rule_type:
        defaults = [r for r in DEFAULT_RULES if r.get("type") == rule_type]

    if _audit_rules is not None:
        edit_map = {r["id"]: r for r in _audit_rules}
        merged = []
        for default in defaults:
            user_edit = edit_map.get(default["id"])
            if user_edit:
                m = {**default, **user_edit}
                m["check"] = default["check"]
                merged.append(m)
            else:
                merged.append(copy.deepcopy(default))
    else:
        merged = copy.deepcopy(defaults)

    customs = _custom_rules
    if rule_type:
        customs = [r for r in customs if r.get("type") == rule_type]
    for cr in customs:
        cr_copy = copy.deepcopy(cr)
        cr_copy.setdefault("check", "_check_custom_pattern")
        merged.append(cr_copy)

    return merged


@app.get("/api/audit/rules")
async def get_audit_rules(rule_type: str | None = None):
    """Return current audit rules (defaults + custom, optionally filtered).
    Use ?rule_type=best-practices or ?rule_type=security-hardening to filter."""
    effective = _build_effective_rules(rule_type)
    safe = copy.deepcopy(effective)
    for r in safe:
        r.pop("check", None)
    return {"rules": safe}


class RulesUpdate(BaseModel):
    rules: list[dict]


@app.put("/api/audit/rules")
async def update_audit_rules(body: RulesUpdate):
    """Update the audit rules (toggle enabled, change severity, etc.).
    Only updates built-in rules; custom rules are managed separately."""
    global _audit_rules
    if _audit_rules is None:
        _audit_rules = []
    incoming_map = {r["id"]: r for r in body.rules if not r.get("custom")}
    existing_map = {r["id"]: r for r in _audit_rules}
    existing_map.update(incoming_map)
    _audit_rules = list(existing_map.values())

    for cr in body.rules:
        if cr.get("custom"):
            for existing in _custom_rules:
                if existing["id"] == cr["id"]:
                    existing["enabled"] = cr.get("enabled", True)
                    existing["severity"] = cr.get("severity", existing.get("severity", "info"))
                    break

    return {"status": "updated", "count": len(_audit_rules) + len(_custom_rules)}


class CustomRuleCreate(BaseModel):
    title: str
    category: str
    description: str
    severity: str = "warning"
    rule_type: str = "best-practices"
    match_field: str = ""
    match_value: str = ""
    match_classid: str = ""


@app.post("/api/audit/rules/add")
async def add_custom_rule(body: CustomRuleCreate):
    """Add a user-defined custom rule."""
    rule_id = f"custom-{uuid.uuid4().hex[:8]}"
    new_rule = {
        "id": rule_id,
        "category": body.category,
        "title": body.title,
        "description": body.description,
        "severity": body.severity,
        "enabled": True,
        "type": body.rule_type,
        "custom": True,
        "check": "_check_custom_pattern",
        "match_field": body.match_field,
        "match_value": body.match_value,
        "match_classid": body.match_classid,
        "reference": "Custom Rule",
    }
    _custom_rules.append(new_rule)
    safe = copy.deepcopy(new_rule)
    safe.pop("check", None)
    return {"status": "added", "rule": safe}


class CustomRuleDelete(BaseModel):
    rule_id: str


@app.post("/api/audit/rules/delete")
async def delete_custom_rule(body: CustomRuleDelete):
    """Delete a user-defined custom rule."""
    global _custom_rules
    before = len(_custom_rules)
    _custom_rules = [r for r in _custom_rules if r["id"] != body.rule_id]
    if len(_custom_rules) == before:
        raise HTTPException(status_code=404, detail="Custom rule not found")
    return {"status": "deleted", "rule_id": body.rule_id}


@app.post("/api/audit/rules/reset")
async def reset_audit_rules():
    """Reset built-in rules back to defaults and clear custom rules."""
    global _audit_rules, _custom_rules
    _audit_rules = None
    _custom_rules = []
    return {"status": "reset"}


@app.get("/api/audit")
async def run_best_practice_audit(rule_type: str | None = None):
    """Run all enabled checks against parsed techsupport data.
    Use ?rule_type=best-practices or ?rule_type=security-hardening to filter."""
    if _parser is None:
        raise HTTPException(
            status_code=400,
            detail="No techsupport data loaded. Upload files first."
        )

    effective = _build_effective_rules(rule_type)
    result = run_audit(_parser._mos, effective)
    return result


def _run_export_audit(rule_type: str | None) -> dict:
    """Common helper: run audit for export, raise if no data."""
    if _parser is None:
        raise HTTPException(
            status_code=400,
            detail="No techsupport data loaded. Upload files first."
        )
    effective = _build_effective_rules(rule_type)
    return run_audit(_parser._mos, effective)


_REPORT_TITLES = {
    "best-practices": "Cisco Intersight — Best Practices Audit Report",
    "security-hardening": "Cisco Intersight — Security Hardening Audit Report",
}

_REFERENCE_URLS = {
    "best-practices": (
        "Cisco Intersight Best Practices Configuration Guide — "
        "https://www.cisco.com/c/en/us/products/collateral/cloud-systems-management/"
        "intersight/intersight-best-practice-config-guide.html"
    ),
    "security-hardening": (
        "Cisco Compute Intersight Hardening Guide — "
        "https://www.cisco.com/c/en/us/products/collateral/cloud-systems-management/"
        "intersight/compute-intersight-hardening-guide-wp.html"
    ),
}


@app.get("/api/audit/export")
async def export_audit_docx(
    rule_type: str | None = None,
    customer_name: str = "",
    project_name: str = "",
    project_pid: str = "",
    author: str = "",
):
    """Export audit findings as a .docx Word document."""
    try:
        from docx import Document
        from docx.shared import Pt, Inches, RGBColor
        from docx.enum.table import WD_TABLE_ALIGNMENT
    except ImportError:
        raise HTTPException(
            status_code=500,
            detail="python-docx not installed. Run: pip install python-docx"
        )

    result = _run_export_audit(rule_type)
    report_title = _REPORT_TITLES.get(rule_type, "Cisco Intersight — Audit Report")
    now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    doc = Document()
    style = doc.styles['Normal']
    font = style.font
    font.name = 'Calibri'
    font.size = Pt(10)

    doc.add_heading(report_title, level=0)

    meta_fields = [
        ("Customer Name", customer_name),
        ("Author", author),
        ("Project ID", project_pid),
        ("Files Analyzed", ", ".join(_uploaded_files) if _uploaded_files else "N/A"),
        ("Report Generated", now_str),
    ]
    meta_table = doc.add_table(rows=0, cols=2)
    meta_table.style = 'Table Grid'
    for label, value in meta_fields:
        if not value and label in ("Customer Name", "Author", "Project ID"):
            continue
        row = meta_table.add_row().cells
        row[0].text = label
        row[1].text = value
        for p in row[0].paragraphs:
            for r in p.runs:
                r.bold = True
                r.font.size = Pt(9)
        for p in row[1].paragraphs:
            for r in p.runs:
                r.font.size = Pt(9)

    doc.add_paragraph()

    summary = result["summary"]
    p = doc.add_paragraph()
    p.add_run('Total Checks: ').bold = True
    p.add_run(str(result["total_rules_checked"]))
    p.add_run('  |  ')
    run_pass = p.add_run(f'Pass: {summary.get("pass", 0)}')
    run_pass.font.color.rgb = RGBColor(0x10, 0xB9, 0x81)
    p.add_run('  |  ')
    run_fail = p.add_run(f'Fail: {summary.get("fail", 0)}')
    run_fail.font.color.rgb = RGBColor(0xEF, 0x44, 0x44)
    p.add_run('  |  ')
    run_warn = p.add_run(f'Warning: {summary.get("warning", 0)}')
    run_warn.font.color.rgb = RGBColor(0xF5, 0x9E, 0x0B)
    p.add_run('  |  ')
    p.add_run(f'Info: {summary.get("info", 0)}')

    doc.add_paragraph()

    status_colors = {
        "pass": RGBColor(0x10, 0xB9, 0x81),
        "fail": RGBColor(0xEF, 0x44, 0x44),
        "warning": RGBColor(0xF5, 0x9E, 0x0B),
        "info": RGBColor(0x64, 0x74, 0x8B),
        "error": RGBColor(0xEF, 0x44, 0x44),
    }

    for category, findings in result["categories"].items():
        doc.add_heading(category, level=1)

        table = doc.add_table(rows=1, cols=4)
        table.style = 'Table Grid'
        table.alignment = WD_TABLE_ALIGNMENT.LEFT
        hdr = table.rows[0].cells
        for i, label in enumerate(['Status', 'Rule', 'Details', 'Affected Items']):
            hdr[i].text = label
            for paragraph in hdr[i].paragraphs:
                for run in paragraph.runs:
                    run.bold = True
                    run.font.size = Pt(9)

        for f in findings:
            row = table.add_row().cells
            status_text = f["status"].upper()
            row[0].text = status_text
            for paragraph in row[0].paragraphs:
                for run in paragraph.runs:
                    run.font.color.rgb = status_colors.get(
                        f["status"], RGBColor(0, 0, 0))
                    run.bold = True
                    run.font.size = Pt(9)

            row[1].text = f["rule_title"]
            for paragraph in row[1].paragraphs:
                for run in paragraph.runs:
                    run.font.size = Pt(9)

            row[2].text = f["message"]
            for paragraph in row[2].paragraphs:
                for run in paragraph.runs:
                    run.font.size = Pt(9)

            affected = f.get("affected", [])
            row[3].text = "\n".join(affected[:10])
            if len(affected) > 10:
                row[3].text += f"\n… and {len(affected) - 10} more"
            for paragraph in row[3].paragraphs:
                for run in paragraph.runs:
                    run.font.size = Pt(8)

        doc.add_paragraph()

    doc.add_heading('Reference', level=1)
    ref_text = _REFERENCE_URLS.get(rule_type, _REFERENCE_URLS["best-practices"])
    doc.add_paragraph(ref_text)

    tmp = tempfile.NamedTemporaryFile(suffix=".docx", delete=False)
    doc.save(tmp.name)
    tmp.close()

    filename_map = {
        "best-practices": "intersight_best_practices_audit.docx",
        "security-hardening": "intersight_security_hardening_audit.docx",
    }
    return FileResponse(
        tmp.name,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        filename=filename_map.get(rule_type, "intersight_audit.docx"),
        background=None,
    )


@app.get("/api/audit/export/html")
async def export_audit_html(
    rule_type: str | None = None,
    customer_name: str = "",
    project_name: str = "",
    project_pid: str = "",
):
    """Export audit findings as a self-contained HTML file for email sharing."""
    result = _run_export_audit(rule_type)
    report_title = _REPORT_TITLES.get(rule_type, "Cisco Intersight — Audit Report")
    now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    summary = result["summary"]
    files_text = ", ".join(_uploaded_files) if _uploaded_files else "N/A"
    ref_text = _REFERENCE_URLS.get(rule_type, _REFERENCE_URLS["best-practices"])

    status_colors = {
        "pass": "#10b981", "fail": "#ef4444", "warning": "#f59e0b",
        "info": "#64748b", "error": "#ef4444",
    }
    status_bg = {
        "pass": "#ecfdf5", "fail": "#fef2f2", "warning": "#fffbeb",
        "info": "#f8fafc", "error": "#fef2f2",
    }

    def h(s: str) -> str:
        return html_mod.escape(str(s))

    meta_rows = ""
    if customer_name:
        meta_rows += f"<tr><td class='meta-label'>Customer Name</td><td>{h(customer_name)}</td></tr>"
    if project_name:
        meta_rows += f"<tr><td class='meta-label'>Project Name</td><td>{h(project_name)}</td></tr>"
    if project_pid:
        meta_rows += f"<tr><td class='meta-label'>Project PID</td><td>{h(project_pid)}</td></tr>"
    meta_rows += f"<tr><td class='meta-label'>Files Analyzed</td><td>{h(files_text)}</td></tr>"
    meta_rows += f"<tr><td class='meta-label'>Report Generated</td><td>{h(now_str)}</td></tr>"

    categories_html = ""
    for category, findings in result["categories"].items():
        rows_html = ""
        for f in findings:
            st = f["status"]
            color = status_colors.get(st, "#333")
            bg = status_bg.get(st, "#fff")
            affected = f.get("affected", [])
            affected_html = ""
            if affected:
                items = affected[:20]
                affected_html = "<ul class='affected-list'>" + "".join(
                    f"<li>{h(a)}</li>" for a in items
                ) + "</ul>"
                if len(affected) > 20:
                    affected_html += f"<p class='more'>… and {len(affected) - 20} more</p>"
            ref = f.get("reference", "")
            ref_html = f"<div class='ref'>{h(ref)}</div>" if ref else ""

            rows_html += f"""<tr>
              <td><span class='status-badge' style='background:{bg};color:{color}'>{h(st.upper())}</span></td>
              <td class='rule-title'>{h(f['rule_title'])}
                <span class='sev-tag sev-{h(f.get("severity","info"))}'>{h(f.get("severity","info"))}</span>
              </td>
              <td>{h(f['message'])}{ref_html}</td>
              <td>{affected_html}</td>
            </tr>"""

        categories_html += f"""
        <h2>{h(category)}</h2>
        <table class='findings-table'>
          <thead><tr><th width='80'>Status</th><th>Rule</th><th>Details</th><th>Affected Items</th></tr></thead>
          <tbody>{rows_html}</tbody>
        </table>"""

    html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{h(report_title)}</title>
<style>
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ font-family: 'Segoe UI', Calibri, Arial, sans-serif; color: #1e293b;
         line-height: 1.5; padding: 32px; max-width: 1100px; margin: 0 auto;
         background: #fff; }}
  h1 {{ font-size: 22px; color: #0f172a; margin-bottom: 16px; padding-bottom: 8px;
       border-bottom: 3px solid #0891b2; }}
  h2 {{ font-size: 16px; color: #0f172a; margin: 24px 0 8px; padding-bottom: 4px;
       border-bottom: 1px solid #e2e8f0; }}
  .meta-table {{ width: 100%; border-collapse: collapse; margin-bottom: 20px; font-size: 13px; }}
  .meta-table td {{ padding: 5px 12px; border: 1px solid #e2e8f0; }}
  .meta-label {{ font-weight: 700; background: #f1f5f9; width: 160px; color: #475569; }}
  .summary {{ display: flex; gap: 16px; margin-bottom: 24px; flex-wrap: wrap; }}
  .summary-card {{ padding: 12px 20px; border-radius: 8px; text-align: center;
                   border: 1px solid #e2e8f0; min-width: 90px; }}
  .summary-card .count {{ font-size: 28px; font-weight: 700; }}
  .summary-card .label {{ font-size: 11px; color: #64748b; text-transform: uppercase;
                          letter-spacing: 0.5px; margin-top: 2px; }}
  .count-pass {{ color: #10b981; }}
  .count-fail {{ color: #ef4444; }}
  .count-warning {{ color: #f59e0b; }}
  .count-info {{ color: #64748b; }}
  .findings-table {{ width: 100%; border-collapse: collapse; font-size: 12px; margin-bottom: 16px; }}
  .findings-table th {{ background: #f1f5f9; padding: 8px 10px; text-align: left;
                        font-size: 11px; font-weight: 700; color: #475569;
                        text-transform: uppercase; letter-spacing: 0.3px;
                        border: 1px solid #e2e8f0; }}
  .findings-table td {{ padding: 8px 10px; border: 1px solid #e2e8f0; vertical-align: top; }}
  .status-badge {{ display: inline-block; padding: 2px 8px; border-radius: 10px;
                   font-size: 10px; font-weight: 700; letter-spacing: 0.3px; }}
  .rule-title {{ font-weight: 600; }}
  .sev-tag {{ font-size: 9px; padding: 1px 5px; border-radius: 6px; margin-left: 6px;
              font-weight: 600; text-transform: uppercase; }}
  .sev-critical {{ background: rgba(239,68,68,0.15); color: #ef4444; }}
  .sev-warning {{ background: rgba(245,158,11,0.15); color: #d97706; }}
  .sev-info {{ background: rgba(100,116,139,0.15); color: #64748b; }}
  .affected-list {{ margin: 4px 0 0 16px; font-size: 11px; color: #64748b; font-family: monospace; }}
  .affected-list li {{ margin-bottom: 2px; }}
  .more {{ font-size: 10px; color: #94a3b8; margin-top: 2px; }}
  .ref {{ font-size: 10px; color: #94a3b8; font-style: italic; margin-top: 4px; }}
  .footer {{ margin-top: 32px; padding-top: 12px; border-top: 1px solid #e2e8f0;
             font-size: 11px; color: #94a3b8; }}
  @media print {{
    body {{ padding: 16px; font-size: 11px; }}
    .summary-card {{ min-width: 70px; padding: 8px 12px; }}
    .summary-card .count {{ font-size: 20px; }}
  }}
</style>
</head>
<body>
<h1>{h(report_title)}</h1>

<table class='meta-table'>{meta_rows}</table>

<div class='summary'>
  <div class='summary-card'><div class='count count-pass'>{summary.get("pass",0)}</div><div class='label'>Pass</div></div>
  <div class='summary-card'><div class='count count-fail'>{summary.get("fail",0)}</div><div class='label'>Fail</div></div>
  <div class='summary-card'><div class='count count-warning'>{summary.get("warning",0)}</div><div class='label'>Warning</div></div>
  <div class='summary-card'><div class='count count-info'>{summary.get("info",0)}</div><div class='label'>Info</div></div>
  <div class='summary-card'><div class='count' style='color:#1e293b'>{result["total_rules_checked"]}</div><div class='label'>Total</div></div>
</div>

{categories_html}

<div class='footer'>
  <p>{h(ref_text)}</p>
</div>
</body>
</html>"""

    tmp = tempfile.NamedTemporaryFile(suffix=".html", delete=False, mode="w",
                                     encoding="utf-8")
    tmp.write(html_content)
    tmp.close()

    filename_map = {
        "best-practices": "intersight_best_practices_audit.html",
        "security-hardening": "intersight_security_hardening_audit.html",
    }
    return FileResponse(
        tmp.name,
        media_type="text/html; charset=utf-8",
        filename=filename_map.get(rule_type, "intersight_audit.html"),
        headers={"Content-Disposition": f"attachment; filename={filename_map.get(rule_type, 'intersight_audit.html')}"},
        background=None,
    )


# ── Serve frontend ──────────────────────────────────────────────────────

@app.get("/")
async def serve_index():
    index = FRONTEND_DIR / "index.html"
    if not index.is_file():
        raise HTTPException(status_code=404, detail="Frontend not found")
    return FileResponse(index)


if FRONTEND_DIR.is_dir():
    app.mount("/", StaticFiles(directory=str(FRONTEND_DIR)), name="frontend")
