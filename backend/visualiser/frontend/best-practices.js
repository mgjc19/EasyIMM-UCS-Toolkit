/**
 * Best Practices / Security Hardening Audit — frontend module.
 *
 * Provides:
 *   window.BestPractices.show(ruleType)  — fetch audit, render results
 *   window.BestPractices.hide()          — hide the container
 *
 * ruleType: 'best-practices' | 'security-hardening'
 */
(function () {
  'use strict';

  const API = window.location.origin + '/visualiser';
  const container = document.getElementById('bp-container');

  let _auditData = null;
  let _rules = null;
  let _filter = 'all';
  let _showEditor = false;
  let _showAddForm = false;
  let _ruleType = 'best-practices';

  const TITLES = {
    'best-practices': 'Best Practices Audit',
    'security-hardening': 'Security Hardening Audit',
  };
  const DOCX_NAMES = {
    'best-practices': 'intersight_best_practices_audit.docx',
    'security-hardening': 'intersight_security_hardening_audit.docx',
  };

  async function fetchJSON(url, opts) {
    const r = await fetch(API + url, opts);
    if (!r.ok) {
      const err = await r.json().catch(() => ({ detail: r.statusText }));
      throw new Error(err.detail || r.statusText);
    }
    return r.json();
  }

  function _qs() {
    return `?rule_type=${encodeURIComponent(_ruleType)}`;
  }

  function show(ruleType) {
    _ruleType = ruleType || 'best-practices';
    _filter = 'all';
    _showEditor = false;
    _showAddForm = false;
    container.classList.remove('hidden');
    document.getElementById('tree-container').classList.add('hidden');
    document.getElementById('legend').classList.add('hidden');
    const dp = document.getElementById('detail-panel');
    if (dp) dp.classList.add('hidden');
    renderLoading();
    runAudit();
  }

  function hide() {
    container.classList.add('hidden');
    document.getElementById('tree-container').classList.remove('hidden');
  }

  async function runAudit() {
    try {
      _auditData = await fetchJSON('/api/audit' + _qs());
      const rulesResp = await fetchJSON('/api/audit/rules' + _qs());
      _rules = rulesResp.rules || [];
      render();
    } catch (err) {
      renderError(err.message);
    }
  }

  function renderLoading() {
    const label = TITLES[_ruleType] || 'Audit';
    container.innerHTML = `
      <div class="bp-loading">
        <div class="spinner"></div>
        <p style="color:var(--text-dim);font-size:13px">Running ${esc(label.toLowerCase())}…</p>
      </div>`;
  }

  function renderError(msg) {
    container.innerHTML = `
      <div class="bp-empty">
        <p style="font-size:14px;color:#ef4444">${esc(msg)}</p>
        <p style="margin-top:8px;font-size:12px">Upload techsupport files first, then switch to the audit view.</p>
      </div>`;
  }

  function esc(s) {
    const d = document.createElement('div');
    d.textContent = s;
    return d.innerHTML;
  }

  /* ── Main render ── */
  function render() {
    if (!_auditData) return;
    const s = _auditData.summary;
    const title = TITLES[_ruleType] || 'Audit';
    const customCount = (_rules || []).filter(r => r.custom).length;

    let html = `<div class="bp-header">
      <h2>${esc(title)}</h2>
      <div class="bp-actions">
        <button id="bp-btn-rerun" class="bp-act-btn" title="Re-run audit">
          <svg width="14" height="14" viewBox="0 0 20 20"><path d="M14.66 15.66A8 8 0 1 1 17 10h-2" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/><polyline points="17 6 17 10 13 10" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/></svg>
          Re-run
        </button>
        <button id="bp-btn-rules" class="bp-act-btn${_showEditor ? ' active' : ''}" title="Edit rules">
          <svg width="14" height="14" viewBox="0 0 20 20"><path d="M10 3v14M3 10h14" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/></svg>
          ${_showEditor ? 'Hide Rules' : 'Edit Rules'}
        </button>
        <button id="bp-btn-reset" class="bp-act-btn" title="Reset all rules to defaults">Reset</button>
        <button id="bp-btn-export" class="bp-act-btn bp-act-download" title="Download audit as Word document">
          <svg width="14" height="14" viewBox="0 0 20 20"><path d="M3 14v3h14v-3M10 3v10M6 9l4 4 4-4" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/></svg>
          Download .docx
        </button>
        <button id="bp-btn-export-html" class="bp-act-btn bp-act-download" title="Download audit as HTML file">
          <svg width="14" height="14" viewBox="0 0 20 20"><path d="M4 4h5l2 2h5v10H4z" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linejoin="round"/><path d="M8 12l2-3 2 3" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/></svg>
          Download .html
        </button>
      </div>
    </div>`;

    /* Summary cards */
    html += `<div class="bp-summary">
      <div class="bp-summary-card"><div class="bp-count bp-count-pass">${s.pass || 0}</div><div class="bp-label">Pass</div></div>
      <div class="bp-summary-card"><div class="bp-count bp-count-fail">${s.fail || 0}</div><div class="bp-label">Fail</div></div>
      <div class="bp-summary-card"><div class="bp-count bp-count-warning">${s.warning || 0}</div><div class="bp-label">Warning</div></div>
      <div class="bp-summary-card"><div class="bp-count bp-count-info">${s.info || 0}</div><div class="bp-label">Info</div></div>
      <div class="bp-summary-card"><div class="bp-count" style="color:var(--text)">${_auditData.total_rules_checked}</div><div class="bp-label">Total</div></div>
    </div>`;

    /* Rules editor (shown above findings when toggled) */
    if (_showEditor) {
      html += renderRulesEditor(customCount);
    }

    /* Filter bar */
    html += `<div class="bp-filter-bar">
      ${['all','fail','warning','pass','info'].map(f =>
        `<button class="bp-filter-btn${_filter === f ? ' active' : ''}" data-filter="${f}">${f === 'all' ? 'All' : f.charAt(0).toUpperCase() + f.slice(1)}</button>`
      ).join('')}
    </div>`;

    /* Findings by category */
    const cats = _auditData.categories || {};
    const catNames = Object.keys(cats).sort();
    if (!catNames.length) {
      html += `<div class="bp-empty" style="padding:32px 0"><p style="color:var(--text-dim);font-size:13px">No findings to display.</p></div>`;
    }
    for (const cat of catNames) {
      const findings = cats[cat].filter(f => _filter === 'all' || f.status === _filter);
      if (!findings.length) continue;
      html += `<div class="bp-category"><div class="bp-category-title">${esc(cat)}</div>`;
      for (const f of findings) {
        const sevClass = f.severity === 'critical' ? 'bp-sev-critical'
          : f.severity === 'warning' ? 'bp-sev-warning' : 'bp-sev-info';
        html += `<div class="bp-finding bp-status-${f.status}">
          <span class="bp-status-badge bp-badge-${f.status}">${f.status}</span>
          <div class="bp-finding-body">
            <div class="bp-finding-title">${esc(f.rule_title)}
              <span class="bp-severity-tag ${sevClass}">${f.severity}</span>
            </div>
            <div class="bp-finding-message">${esc(f.message)}</div>`;
        if (f.affected && f.affected.length) {
          html += `<div class="bp-finding-affected">${f.affected.map(a => esc(a)).join('\n')}</div>`;
        }
        if (f.reference) {
          html += `<div class="bp-finding-ref">${esc(f.reference)}</div>`;
        }
        html += `</div></div>`;
      }
      html += `</div>`;
    }

    container.innerHTML = html;
    attachEvents();
  }

  /* ── Rules editor panel ── */
  function renderRulesEditor(customCount) {
    if (!_rules || !_rules.length) return '';

    let html = `<div class="bp-rules-editor">
      <div class="bp-rules-header">
        <h3>Audit Rules</h3>
        <button id="bp-btn-add-rule" class="bp-act-btn bp-act-add">+ Add Custom Rule</button>
      </div>`;

    /* Add-rule form */
    if (_showAddForm) {
      html += `<div class="bp-add-form">
        <div class="bp-add-form-title">New Custom Rule</div>
        <div class="bp-add-form-grid">
          <label><span>Title</span><input id="bp-new-title" type="text" placeholder="e.g. Require AES-256 on storage" /></label>
          <label><span>Category</span><input id="bp-new-category" type="text" placeholder="e.g. Storage Security" /></label>
          <label><span>Severity</span>
            <select id="bp-new-severity">
              <option value="critical">Critical</option>
              <option value="warning" selected>Warning</option>
              <option value="info">Info</option>
            </select>
          </label>
          <label class="bp-add-full"><span>Description</span><textarea id="bp-new-desc" rows="2" placeholder="Describe what this rule checks for…"></textarea></label>
          <label><span>MO Class ID (optional)</span><input id="bp-new-classid" type="text" placeholder="e.g. biosPolicy, commSyslog" /></label>
          <label><span>Field to Check (optional)</span><input id="bp-new-field" type="text" placeholder="e.g. secureBoot" /></label>
          <label><span>Expected Value (optional)</span><input id="bp-new-value" type="text" placeholder="e.g. enabled" /></label>
        </div>
        <p class="bp-add-hint">If MO Class ID + Field + Value are provided, the rule will check all objects of that class and flag any where the field does not match the expected value. Leave them empty for an informational-only rule.</p>
        <div class="bp-add-actions">
          <button id="bp-btn-save-rule" class="bp-act-btn bp-act-save">Save Rule</button>
          <button id="bp-btn-cancel-rule" class="bp-act-btn">Cancel</button>
        </div>
      </div>`;
    }

    /* Group rules by category */
    const cats = {};
    for (const r of _rules) {
      (cats[r.category] = cats[r.category] || []).push(r);
    }

    for (const [cat, rules] of Object.entries(cats).sort((a,b) => a[0].localeCompare(b[0]))) {
      html += `<div class="bp-rules-cat-label">${esc(cat)}</div>`;
      for (const r of rules) {
        const isCustom = !!r.custom;
        html += `<div class="bp-rule-row${isCustom ? ' bp-rule-custom' : ''}">
          <div class="bp-rule-toggle${r.enabled !== false ? ' active' : ''}" data-rule-id="${esc(r.id)}"></div>
          <span class="bp-rule-title">${esc(r.title)}</span>
          <span class="bp-rule-sev bp-sev-tag-${r.severity || 'info'}">${r.severity || 'info'}</span>
          ${isCustom ? `<button class="bp-rule-delete" data-rule-id="${esc(r.id)}" title="Delete custom rule">&times;</button>` : ''}
        </div>`;
      }
    }

    html += `</div>`;
    return html;
  }

  /* ── Event binding ── */
  function attachEvents() {
    const btnRerun = document.getElementById('bp-btn-rerun');
    const btnRules = document.getElementById('bp-btn-rules');
    const btnReset = document.getElementById('bp-btn-reset');
    const btnExport = document.getElementById('bp-btn-export');
    const btnAddRule = document.getElementById('bp-btn-add-rule');
    const btnSaveRule = document.getElementById('bp-btn-save-rule');
    const btnCancelRule = document.getElementById('bp-btn-cancel-rule');

    if (btnRerun) btnRerun.addEventListener('click', () => {
      renderLoading();
      runAudit();
    });

    if (btnRules) btnRules.addEventListener('click', () => {
      _showEditor = !_showEditor;
      _showAddForm = false;
      render();
    });

    if (btnReset) btnReset.addEventListener('click', async () => {
      if (!confirm('Reset all rules to defaults and remove custom rules?')) return;
      try {
        await fetchJSON('/api/audit/rules/reset', { method: 'POST' });
        _showEditor = false;
        _showAddForm = false;
        renderLoading();
        runAudit();
      } catch (err) {
        alert('Reset failed: ' + err.message);
      }
    });

    if (btnExport) btnExport.addEventListener('click', () => showExportModal());

    const btnExportHtml = document.getElementById('bp-btn-export-html');
    if (btnExportHtml) btnExportHtml.addEventListener('click', () => exportAuditHTML());

    /* Add Rule form */
    if (btnAddRule) btnAddRule.addEventListener('click', () => {
      _showAddForm = !_showAddForm;
      render();
    });

    if (btnSaveRule) btnSaveRule.addEventListener('click', async () => {
      const title = (document.getElementById('bp-new-title') || {}).value || '';
      const category = (document.getElementById('bp-new-category') || {}).value || '';
      const desc = (document.getElementById('bp-new-desc') || {}).value || '';
      const severity = (document.getElementById('bp-new-severity') || {}).value || 'warning';
      const classid = (document.getElementById('bp-new-classid') || {}).value || '';
      const field = (document.getElementById('bp-new-field') || {}).value || '';
      const value = (document.getElementById('bp-new-value') || {}).value || '';

      if (!title.trim()) { alert('Title is required.'); return; }
      if (!category.trim()) { alert('Category is required.'); return; }

      try {
        btnSaveRule.textContent = 'Saving…';
        btnSaveRule.disabled = true;
        await fetchJSON('/api/audit/rules/add', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            title: title.trim(),
            category: category.trim(),
            description: desc.trim() || title.trim(),
            severity,
            rule_type: _ruleType,
            match_classid: classid.trim(),
            match_field: field.trim(),
            match_value: value.trim(),
          }),
        });
        _showAddForm = false;
        renderLoading();
        runAudit();
      } catch (err) {
        alert('Failed to add rule: ' + err.message);
        btnSaveRule.textContent = 'Save Rule';
        btnSaveRule.disabled = false;
      }
    });

    if (btnCancelRule) btnCancelRule.addEventListener('click', () => {
      _showAddForm = false;
      render();
    });

    /* Filter buttons */
    container.querySelectorAll('.bp-filter-btn').forEach(btn => {
      btn.addEventListener('click', () => {
        _filter = btn.dataset.filter;
        render();
      });
    });

    /* Toggle switches (enable/disable rules) */
    container.querySelectorAll('.bp-rule-toggle').forEach(toggle => {
      toggle.addEventListener('click', async () => {
        const ruleId = toggle.dataset.ruleId;
        const rule = _rules.find(r => r.id === ruleId);
        if (!rule) return;

        const wasActive = toggle.classList.contains('active');
        rule.enabled = !wasActive;
        toggle.classList.toggle('active');

        try {
          await fetch(API + '/api/audit/rules', {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ rules: _rules }),
          });
        } catch (err) {
          rule.enabled = wasActive;
          toggle.classList.toggle('active');
          console.error('Rule update failed:', err);
        }
      });
    });

    /* Delete custom rules */
    container.querySelectorAll('.bp-rule-delete').forEach(btn => {
      btn.addEventListener('click', async (e) => {
        e.stopPropagation();
        const ruleId = btn.dataset.ruleId;
        if (!confirm('Delete this custom rule?')) return;
        try {
          await fetchJSON('/api/audit/rules/delete', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ rule_id: ruleId }),
          });
          renderLoading();
          runAudit();
        } catch (err) {
          alert('Delete failed: ' + err.message);
        }
      });
    });
  }

  /* ── Download Document modal ── */

  function showExportModal() {
    let overlay = document.getElementById('bp-export-overlay');
    if (overlay) { overlay.remove(); }

    overlay = document.createElement('div');
    overlay.id = 'bp-export-overlay';
    overlay.className = 'bp-modal-overlay';
    overlay.innerHTML = `
      <div class="bp-modal">
        <div class="bp-modal-title">Download Document</div>
        <div class="bp-modal-form">
          <label><span>Customer Name</span><input id="bp-exp-customer" type="text" placeholder="e.g. Acme Corp" /></label>
          <label><span>Author Name</span><input id="bp-exp-author" type="text" placeholder="e.g. John Doe" /></label>
          <label><span>Project ID</span><input id="bp-exp-pid" type="text" placeholder="e.g. PID-12345" /></label>
        </div>
        <div class="bp-modal-actions">
          <button id="bp-exp-ok" class="bp-act-btn bp-act-ok">OK</button>
          <button id="bp-exp-cancel" class="bp-act-btn">Cancel</button>
        </div>
      </div>`;
    document.body.appendChild(overlay);

    overlay.addEventListener('click', (e) => {
      if (e.target === overlay) overlay.remove();
    });
    document.getElementById('bp-exp-cancel').addEventListener('click', () => overlay.remove());
    document.getElementById('bp-exp-ok').addEventListener('click', () => doExport(overlay));

    const firstInput = document.getElementById('bp-exp-customer');
    if (firstInput) firstInput.focus();
  }

  async function doExport(overlay) {
    const btn = document.getElementById('bp-exp-ok');
    const customerName = (document.getElementById('bp-exp-customer') || {}).value || '';
    const author = (document.getElementById('bp-exp-author') || {}).value || '';
    const projectPid = (document.getElementById('bp-exp-pid') || {}).value || '';

    try {
      btn.textContent = 'Generating…';
      btn.disabled = true;

      const qs = new URLSearchParams({
        rule_type: _ruleType,
        customer_name: customerName,
        project_name: customerName,
        project_pid: projectPid,
        author: author || 'Cisco Customer Experience',
      });

      const r = await fetch(API + '/api/audit/export?' + qs.toString());
      if (!r.ok) {
        const err = await r.json().catch(() => ({ detail: r.statusText }));
        throw new Error(err.detail || 'Export failed');
      }

      const blob = await r.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      const custSlug = (customerName || 'UCS').replace(/\s+/g, '_').substring(0, 30);
      a.download = custSlug + '_UCS_Health_Check_Audit.docx';
      a.click();
      URL.revokeObjectURL(url);

      overlay.remove();
    } catch (err) {
      alert('Export failed: ' + err.message);
      btn.textContent = 'OK';
      btn.disabled = false;
    }
  }

  async function exportAuditHTML() {
    try {
      const qs = new URLSearchParams({ rule_type: _ruleType });
      const r = await fetch(API + '/api/audit/export/html?' + qs.toString());
      if (!r.ok) {
        const err = await r.json().catch(() => ({ detail: r.statusText }));
        throw new Error(err.detail || 'Export failed');
      }
      const blob = await r.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      const names = {
        'best-practices': 'intersight_best_practices_audit.html',
        'security-hardening': 'intersight_security_hardening_audit.html',
      };
      a.download = names[_ruleType] || 'intersight_audit.html';
      a.click();
      URL.revokeObjectURL(url);
    } catch (err) {
      alert('HTML export failed: ' + err.message);
    }
  }

  window.BestPractices = { show, hide };
})();

