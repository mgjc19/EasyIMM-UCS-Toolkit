/**
 * Intersight Visualiser — main application logic.
 *
 * Supports three data source modes:
 *   1. Live Intersight API (connect with API key)
 *   2. Offline techsupport upload (one or more bundles)
 *   3. Hybrid: techsupport + Intersight API together
 */

(function () {
  'use strict';

  const API = '/visualiser/api';

  // ── DOM refs ──
  const connectModal   = document.getElementById('connect-modal');
  const connectForm    = document.getElementById('connect-form');
  const connectError   = document.getElementById('connect-error');
  const uploadModal    = document.getElementById('upload-modal');
  const dropZone       = document.getElementById('drop-zone');
  const fileInput      = document.getElementById('file-input');
  const btnBrowse      = document.getElementById('btn-browse');
  const fileListEl     = document.getElementById('file-list');
  const btnUploadGo    = document.getElementById('btn-upload-go');
  const uploadProgress = document.getElementById('upload-progress');
  const progressFill   = document.getElementById('progress-fill');
  const uploadStatus   = document.getElementById('upload-status');
  const uploadError    = document.getElementById('upload-error');
  const loadingOverlay = document.getElementById('loading-overlay');
  const loadingMessage = document.getElementById('loading-message');
  const emptyState     = document.getElementById('empty-state');
  const treeContainer  = document.getElementById('tree-container');
  const detailPanel    = document.getElementById('detail-panel');
  const detailTitle    = document.getElementById('detail-title');
  const detailContent  = document.getElementById('detail-content');
  const detailClose    = document.getElementById('detail-close');
  const accountBadge   = document.getElementById('account-badge');
  const statusText     = document.getElementById('status-text');
  const nodeCountEl    = document.getElementById('node-count');
  const searchInput    = document.getElementById('search-input');
  const btnConnect     = document.getElementById('btn-connect');
  const btnRefresh     = document.getElementById('btn-refresh');
  const btnExpandAll   = document.getElementById('btn-expand-all');
  const btnCollapseAll = document.getElementById('btn-collapse-all');
  const btnExport      = document.getElementById('btn-export');
  const legend         = document.getElementById('legend');
  const legendItems    = document.getElementById('legend-items');

  const viewSelector = document.getElementById('view-selector');
  const btnAddFiles  = document.getElementById('btn-add-files');
  const btnAddApi    = document.getElementById('btn-add-api');

  const vlanModal      = document.getElementById('vlan-modal');
  const vlanModalTitle = document.getElementById('vlan-modal-title');
  const vlanModalBody  = document.getElementById('vlan-modal-body');
  const vlanModalClose = document.getElementById('vlan-modal-close');
  const vlanModalHeader = vlanModal ? vlanModal.querySelector('.vlan-modal-header') : null;

  const viz = new TreeVisualizer('#tree-container');
  let dataSource = 'none'; // 'none' | 'intersight' | 'techsupport' | 'hybrid'
  let currentView = 'logical';
  let pendingFiles = [];   // files queued for upload

  // ── Helpers ──
  function showLoading(msg) { loadingMessage.textContent = msg || 'Loading…'; loadingOverlay.classList.remove('hidden'); }
  function hideLoading() { loadingOverlay.classList.add('hidden'); }
  function showError(el, msg) { el.textContent = msg; el.classList.remove('hidden'); }
  function hideError(el) { el.classList.add('hidden'); }

  function fmtSize(bytes) {
    if (bytes < 1024) return bytes + ' B';
    if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB';
    if (bytes < 1024 * 1024 * 1024) return (bytes / (1024 * 1024)).toFixed(1) + ' MB';
    return (bytes / (1024 * 1024 * 1024)).toFixed(2) + ' GB';
  }

  function setActive(source, label) {
    dataSource = source;
    accountBadge.textContent = label;
    accountBadge.classList.remove('hidden');

    if (source === 'techsupport' || source === 'hybrid') {
      btnConnect.textContent = 'Clear';
      viewSelector.classList.remove('hidden');
      viewSelector.value = currentView;
      btnRefresh.disabled = source !== 'hybrid';
      btnAddFiles.classList.remove('hidden');
      btnAddApi.classList.toggle('hidden', source === 'hybrid');
    } else {
      btnConnect.textContent = 'Disconnect';
      viewSelector.classList.add('hidden');
      currentView = 'logical';
      btnRefresh.disabled = false;
      btnAddFiles.classList.add('hidden');
      btnAddApi.classList.add('hidden');
    }
    btnConnect.classList.remove('primary');
    btnExpandAll.disabled = false;
    btnCollapseAll.disabled = false;
    btnExport.disabled = false;

    if (source === 'intersight') {
      statusText.textContent = `Connected to ${label}`;
    } else if (source === 'hybrid') {
      statusText.textContent = `Hybrid: ${label}`;
    } else {
      statusText.textContent = `Loaded: ${label}`;
    }
  }

  function setDisconnected() {
    dataSource = 'none';
    currentView = 'logical';
    pendingFiles = [];
    accountBadge.classList.add('hidden');
    viewSelector.classList.add('hidden');
    btnAddFiles.classList.add('hidden');
    btnAddApi.classList.add('hidden');
    btnConnect.textContent = 'Connect';
    btnConnect.classList.add('primary');
    btnRefresh.disabled = true;
    btnExpandAll.disabled = true;
    btnCollapseAll.disabled = true;
    btnExport.disabled = true;
    statusText.textContent = 'Disconnected';
    nodeCountEl.textContent = '';
    emptyState.classList.remove('hidden');
    treeContainer.innerHTML = '';
    legend.classList.add('hidden');
    detailPanel.classList.add('hidden');
    if (window.BestPractices) window.BestPractices.hide();
  }

  // ── API ──
  async function apiPost(path, body) {
    const r = await fetch(`${API}${path}`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
    const d = await r.json();
    if (!r.ok) throw new Error(d.detail || `HTTP ${r.status}`);
    return d;
  }
  async function apiGet(path) {
    const r = await fetch(`${API}${path}`);
    const d = await r.json();
    if (!r.ok) throw new Error(d.detail || `HTTP ${r.status}`);
    return d;
  }

  // ── Connect (Intersight API) ──
  connectForm.addEventListener('submit', async (e) => {
    e.preventDefault();
    hideError(connectError);
    const apiKeyId   = document.getElementById('input-api-key').value.trim();
    const secretPath = document.getElementById('input-secret-path').value.trim();
    const baseUrl    = document.getElementById('input-base-url').value.trim();
    if (!apiKeyId || !secretPath) { showError(connectError, 'API Key ID and Secret Key Path are required.'); return; }

    connectModal.classList.add('hidden');
    showLoading('Connecting to Intersight…');
    try {
      const res = await apiPost('/connect', { api_key_id: apiKeyId, secret_key_path: secretPath, base_url: baseUrl || 'https://intersight.com' });
      const s = await apiGet('/status');
      const mode = s.source || 'intersight';
      const label = mode === 'hybrid'
        ? `${res.account_name} + ${s.files.length} file(s)`
        : res.account_name || 'Intersight';
      setActive(mode, label);
      hideLoading();
      await loadHierarchy();
    } catch (err) {
      hideLoading();
      connectModal.classList.remove('hidden');
      showError(connectError, err.message);
    }
  });

  btnConnect.addEventListener('click', async () => {
    if (dataSource !== 'none') {
      const msg = (dataSource === 'techsupport' || dataSource === 'hybrid') ? 'Clearing session…' : 'Disconnecting…';
      showLoading(msg);
      try { await apiPost('/disconnect', {}); } catch (_) {}
      hideLoading();
      setDisconnected();
    } else {
      connectModal.classList.remove('hidden');
    }
  });

  // ── Upload: file staging ──
  function renderFileList() {
    if (!pendingFiles.length) {
      fileListEl.classList.add('hidden');
      btnUploadGo.classList.add('hidden');
      return;
    }
    fileListEl.classList.remove('hidden');
    btnUploadGo.classList.remove('hidden');
    fileListEl.innerHTML = pendingFiles.map((f, i) =>
      `<div class="file-list-item" data-idx="${i}">
        <span class="file-name">${esc(f.name)}</span>
        <span class="file-size">${fmtSize(f.size)}</span>
        <button class="file-remove" title="Remove">&times;</button>
      </div>`
    ).join('');
    fileListEl.querySelectorAll('.file-remove').forEach(btn => {
      btn.addEventListener('click', (e) => {
        const idx = parseInt(e.target.closest('.file-list-item').dataset.idx, 10);
        pendingFiles.splice(idx, 1);
        renderFileList();
      });
    });
  }

  function addFiles(fileList) {
    for (const f of fileList) {
      if (!pendingFiles.some(p => p.name === f.name && p.size === f.size)) {
        pendingFiles.push(f);
      }
    }
    renderFileList();
    hideError(uploadError);
  }

  btnBrowse.addEventListener('click', () => fileInput.click());
  fileInput.addEventListener('change', () => {
    if (fileInput.files.length) addFiles(fileInput.files);
    fileInput.value = '';
  });

  dropZone.addEventListener('click', (e) => {
    if (e.target === dropZone || e.target.tagName === 'P' || e.target.tagName === 'SPAN') fileInput.click();
  });
  dropZone.addEventListener('dragover', (e) => { e.preventDefault(); dropZone.classList.add('drag-over'); });
  dropZone.addEventListener('dragleave', () => dropZone.classList.remove('drag-over'));
  dropZone.addEventListener('drop', (e) => {
    e.preventDefault();
    dropZone.classList.remove('drag-over');
    if (e.dataTransfer.files.length) addFiles(e.dataTransfer.files);
  });

  // ── Upload: open fresh vs. add-more ──
  let uploadIsAdd = false;
  window._openUploadFresh = function () {
    pendingFiles = [];
    renderFileList();
    hideError(uploadError);
    uploadProgress.classList.add('hidden');
    uploadIsAdd = false;
    btnUploadGo.textContent = 'Upload & Parse';
    uploadModal.classList.remove('hidden');
  };

  btnUploadGo.addEventListener('click', () => handleUpload(pendingFiles, uploadIsAdd));

  async function handleUpload(files, isAdd) {
    if (!files.length) return;
    hideError(uploadError);
    uploadProgress.classList.remove('hidden');
    progressFill.style.width = '0%';
    const label = files.length === 1 ? files[0].name : `${files.length} files`;
    uploadStatus.textContent = `Uploading ${label}…`;

    const formData = new FormData();
    for (const f of files) formData.append('files', f);

    // For incremental adds, use plain XHR (no SSE)
    if (isAdd) {
      try {
        const xhr = new XMLHttpRequest();
        const result = await new Promise((resolve, reject) => {
          xhr.upload.addEventListener('progress', (e) => {
            if (e.lengthComputable) {
              const pct = Math.round((e.loaded / e.total) * 100);
              progressFill.style.width = pct + '%';
              uploadStatus.textContent = pct < 100 ? `Uploading… ${pct}%` : 'Parsing…';
            }
          });
          xhr.addEventListener('load', () => {
            if (xhr.status >= 200 && xhr.status < 300) resolve(JSON.parse(xhr.responseText));
            else { try { reject(new Error(JSON.parse(xhr.responseText).detail)); } catch (_e) { reject(new Error(`HTTP ${xhr.status}`)); } }
          });
          xhr.addEventListener('error', () => reject(new Error('Network error')));
          xhr.open('POST', `${API}/upload/add`);
          xhr.send(formData);
        });
        uploadModal.classList.add('hidden');
        uploadProgress.classList.add('hidden');
        pendingFiles = []; renderFileList();
        const s = await apiGet('/status');
        const fileNames = s.files || result.files || [label];
        const badge = fileNames.length === 1 ? fileNames[0] : `${fileNames.length} techsupport files`;
        const mode = s.source || 'techsupport';
        setActive(mode, mode === 'hybrid' ? `Intersight + ${badge}` : badge);
        await loadHierarchy();
      } catch (err) { uploadProgress.classList.add('hidden'); showError(uploadError, err.message); }
      return;
    }

    // New upload with SSE parse progress stream
    try {
      // Upload via XHR (progress bar), response is an SSE stream
      const xhr = new XMLHttpRequest();
      xhr.open('POST', `${API}/upload`);

      // Track upload progress
      xhr.upload.addEventListener('progress', (e) => {
        if (e.lengthComputable) {
          const pct = Math.round((e.loaded / e.total) * 100);
          progressFill.style.width = pct + '%';
          uploadStatus.textContent = pct < 100
            ? `Uploading ${label}… ${pct}%`
            : 'Upload complete. Starting parse…';
        }
      });

      // Show parse log container
      let parseLog = document.getElementById('parse-log');
      if (!parseLog) {
        parseLog = document.createElement('div');
        parseLog.id = 'parse-log';
        parseLog.className = 'parse-log';
        uploadProgress.parentNode.insertBefore(parseLog, uploadError);
      }
      parseLog.innerHTML = '';
      parseLog.classList.remove('hidden');

      xhr.addEventListener('loadstart', () => {
        progressFill.style.width = '0%';
      });

      // Process SSE stream from response
      const onComplete = new Promise((resolve, reject) => {
        xhr.addEventListener('load', () => {
          if (xhr.status >= 400) {
            try { reject(new Error(JSON.parse(xhr.responseText).detail)); }
            catch (_e) { reject(new Error(`Upload failed: HTTP ${xhr.status}`)); }
            return;
          }
          // Parse SSE lines from response text
          const lines = xhr.responseText.split('\n');
          let error = null;
          for (const line of lines) {
            if (!line.startsWith('data: ')) continue;
            const msg = line.slice(6);
            if (msg.startsWith('__ERROR__:')) {
              error = msg.slice(10);
              continue;
            }
            if (msg === '__DONE__') continue;
            const el = document.createElement('div');
            el.className = 'parse-log-line';
            el.textContent = msg;
            parseLog.appendChild(el);
            parseLog.scrollTop = parseLog.scrollHeight;
          }
          if (error) reject(new Error(error));
          else resolve();
        });
        xhr.addEventListener('error', () => reject(new Error('Network error')));
      });

      // Use streaming with XHR - poll responseText for incremental SSE data
      let lastLen = 0;
      const pollInterval = setInterval(() => {
        if (xhr.readyState < 2) return;
        const text = xhr.responseText || '';
        if (text.length <= lastLen) return;
        const newText = text.slice(lastLen);
        lastLen = text.length;
        const lines = newText.split('\n');
        for (const line of lines) {
          if (!line.startsWith('data: ')) continue;
          const msg = line.slice(6);
          if (msg === '__DONE__' || msg.startsWith('__ERROR__:')) continue;
          const el = document.createElement('div');
          el.className = 'parse-log-line';
          el.textContent = msg;
          parseLog.appendChild(el);
          parseLog.scrollTop = parseLog.scrollHeight;
          uploadStatus.textContent = msg;
        }
      }, 150);

      xhr.send(formData);
      await onComplete;
      clearInterval(pollInterval);

      // Success
      parseLog.classList.add('hidden');
      uploadModal.classList.add('hidden');
      uploadProgress.classList.add('hidden');
      pendingFiles = []; renderFileList();

      const s = await apiGet('/status');
      const fileNames = s.files || [label];
      const badge = fileNames.length === 1 ? fileNames[0] : `${fileNames.length} techsupport files`;
      const mode = s.source || 'techsupport';
      setActive(mode, mode === 'hybrid' ? `Intersight + ${badge}` : badge);
      await loadHierarchy();

    } catch (err) {
      uploadProgress.classList.add('hidden');
      const parseLog = document.getElementById('parse-log');
      if (parseLog) parseLog.classList.add('hidden');
      showError(uploadError, err.message);
    }
  }

  // ── View selector ──
  viewSelector.addEventListener('change', () => {
    currentView = viewSelector.value;
    if (currentView === 'bestpractices') {
      if (window.BestPractices) window.BestPractices.show('best-practices');
      return;
    }
    if (currentView === 'securityhardening') {
      if (window.BestPractices) window.BestPractices.show('security-hardening');
      return;
    }
    if (window.BestPractices) window.BestPractices.hide();
    loadHierarchy(false);
  });

  // ── Load hierarchy ──
  async function loadHierarchy(refresh) {
    showLoading('Building infrastructure hierarchy…');
    try {
      const params = new URLSearchParams();
      if (refresh) params.set('refresh', 'true');
      if (dataSource === 'techsupport' || dataSource === 'hybrid') {
        params.set('view', currentView);
      }
      const qs = params.toString() ? `?${params}` : '';
      const tree = await apiGet(`/hierarchy${qs}`);
      emptyState.classList.add('hidden');
      viz.render(tree);
      viz.onNodeClick = handleNodeClick;
      nodeCountEl.textContent = `${viz.getNodeCount()} nodes`;
      buildLegend(tree);
      legend.classList.remove('hidden');
    } catch (err) {
      statusText.textContent = `Error: ${err.message}`;
    } finally {
      hideLoading();
    }
  }

  // ── Legend ──
  function buildLegend(tree) {
    const view = tree.view || currentView;
    let items;

    if (view === 'physical') {
      items = [
        { label: 'Fabric Interconnect', colour: '#06b6d4' },
        { label: 'Uplink Port',         colour: '#22d3ee' },
        { label: 'Server Port',         colour: '#a3e635' },
        { label: 'FC Port',             colour: '#c084fc' },
        { label: 'Port Channel',        colour: '#67e8f9' },
        { label: 'CDP Neighbor',        colour: '#94a3b8' },
        { label: 'Chassis',             colour: '#f59e0b' },
        { label: 'IOM',                 colour: '#fb923c' },
        { label: 'Blade / Rack',        colour: '#34d399' },
        { label: 'Adapter',             colour: '#f472b6' },
        { label: 'CPU',                 colour: '#818cf8' },
        { label: 'Memory / DIMM',       colour: '#34d399' },
        { label: 'Storage / Disk',      colour: '#fbbf24' },
        { label: 'PSU',                 colour: '#eab308' },
        { label: 'Fan Module',          colour: '#a3e635' },
        { label: 'Firmware',            colour: '#64748b' },
        { label: 'Service Profile',      colour: '#10b981' },
        { label: 'Policy',              colour: '#8b5cf6' },
        { label: 'Pool',                colour: '#06b6d4' },
        { label: 'VLAN',                colour: '#3b82f6' },
        { label: 'Disjoint VLAN',       colour: '#dc2626' },
        { label: 'VSAN',                colour: '#8b5cf6' },
      ];
    } else if (view === 'topology') {
      items = [
        { label: 'Chassis',             colour: '#f59e0b' },
        { label: 'Blade / Rack',        colour: '#34d399' },
        { label: 'IOM',                 colour: '#fb923c' },
        { label: 'Fabric Interconnect', colour: '#06b6d4' },
        { label: 'Port Channel',        colour: '#67e8f9' },
        { label: 'FC Port',             colour: '#c084fc' },
        { label: 'vNIC',                colour: '#f472b6' },
        { label: 'vHBA',                colour: '#f43f5e' },
        { label: 'VLAN',                colour: '#3b82f6' },
      ];
    } else if (view === 'errors') {
      items = [
        { label: 'Critical',            colour: '#dc2626' },
        { label: 'Major',               colour: '#f97316' },
        { label: 'Minor',               colour: '#eab308' },
        { label: 'Warning',             colour: '#64748b' },
        { label: 'Root Cause',          colour: '#f59e0b' },
        { label: 'Recommended Action',  colour: '#10b981' },
        { label: 'Individual Fault',    colour: '#94a3b8' },
      ];
    } else {
      const isTechsupport = tree.source === 'techsupport';
      items = [
        { label: 'Organization',     colour: '#3b82f6' },
        ...(isTechsupport ? [
          { label: 'Fabric Interconnect', colour: '#06b6d4' },
          { label: 'Chassis',          colour: '#f59e0b' },
          { label: 'Blade / Rack',     colour: '#34d399' },
          { label: 'VLAN',             colour: '#3b82f6' },
          { label: 'VSAN',             colour: '#8b5cf6' },
        ] : [
          { label: 'UCS Domain',       colour: '#8b5cf6' },
          { label: 'Switch Profile',   colour: '#06b6d4' },
          { label: 'Chassis Profile',  colour: '#f59e0b' },
        ]),
        { label: 'Server Template',    colour: '#10b981' },
        { label: 'Server Profile',     colour: '#34d399' },
        { label: 'Domain Profile',     colour: '#8b5cf6' },
        { label: 'Compute Policy',     colour: '#ef4444' },
        { label: 'Mgmt Policy',        colour: '#f97316' },
        { label: 'Networking Policy',  colour: '#3b82f6' },
        { label: 'Storage Policy',     colour: '#a855f7' },
        { label: 'Infrastructure',     colour: '#64748b' },
        { label: 'Power/Thermal',      colour: '#eab308' },
        { label: 'Monitoring',         colour: '#14b8a6' },
        { label: 'vNIC',               colour: '#ec4899' },
        { label: 'vHBA',               colour: '#f43f5e' },
        { label: 'Pool',               colour: '#06b6d4' },
      ];
    }

    legendItems.innerHTML = items.map(i =>
      `<div class="legend-item"><span class="legend-swatch" style="background:${i.colour}"></span>${i.label}</div>`
    ).join('');
  }

  // ── Structured description renderer ──
  function renderStructuredDescription(nodeData) {
    const lines = nodeData.description.split('\n');
    const typeLabel = (nodeData.type || '').replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase());

    // Classify lines into sections
    const identity = [];      // SN, PN, Model
    const status = [];        // Power, State, OperState
    const profile = [];       // SP, Profile, Template
    const connectivity = [];  // MAC, WWPN, Veth, Pinned, Rate, Burst, VLAN, VSAN
    const policies = [];      // *Policy, *Pool
    const config = [];        // all other key-value pairs
    const freetext = [];      // non key-value lines (freeform Description, etc.)

    lines.forEach(line => {
      const trimmed = line.trim();
      if (!trimmed) return;
      const sep = trimmed.indexOf(': ');

      // Lines without key:value structure
      if (sep <= 0) {
        // Detect hardware specs like "2×CPU/20C", "512GB RAM"
        if (/\d+.*CPU|GB\s*RAM|cores?/i.test(trimmed))
          identity.push('Hardware: ' + trimmed);
        else
          freetext.push(trimmed);
        return;
      }

      const key = trimmed.substring(0, sep);
      const kl = key.toLowerCase();

      if (['sn', 'pn', 'serial', 'part number', 'model', 'vendor', 'revision', 'hardware', 'firmware', 'fw', 'bios', 'cimc', 'version', 'component', 'package', 'connection', 'side', 'cpus', 'memory'].includes(kl))
        identity.push(trimmed);
      else if (['power', 'state', 'oper', 'operstate', 'admin', 'status', 'size', 'assigned', 'mgmt', 'ip', 'deploy status', 'assigned server', 'config state'].includes(kl))
        status.push(trimmed);
      else if (kl === 'type' && /profile|template/i.test(trimmed))
        profile.push(trimmed);
      else if (kl === 'type')
        identity.push(trimmed);
      else if (kl.includes('service profile') || kl.includes('template') || kl.includes('derived'))
        profile.push(trimmed);
      else if (['mac', 'wwpn', 'wwnn', 'veth', 'vfc', 'pinned', 'rate', 'burst', 'vsan', 'fabric', 'fcoe', 'cdn', 'native vlan', 'capability'].includes(kl))
        connectivity.push(trimmed);
      else if (kl.includes('policy') || kl.includes('pool'))
        policies.push(trimmed);
      else if (kl === 'notes' || kl === 'description')
        freetext.push(trimmed);
      else if (['bw', 'mtu', 'weight', 'drop', 'raid'].includes(kl))
        config.push(trimmed);
      else
        config.push(trimmed);
    });

    let html = '';

    function renderSection(title, items) {
      if (!items.length) return '';
      let s = `<div class="detail-section"><div class="detail-section-title">${esc(title)}</div>`;
      items.forEach(line => {
        const sep = line.indexOf(': ');
        if (sep > 0) {
          s += `<div class="detail-row"><span class="detail-key">${esc(line.substring(0, sep))}</span><span class="detail-value" style="word-break:break-word">${esc(line.substring(sep + 2))}</span></div>`;
        } else {
          s += `<div class="detail-row"><span class="detail-value" style="word-break:break-word">${esc(line)}</span></div>`;
        }
      });
      s += '</div>';
      return s;
    }

    html += renderSection('Identity', identity);
    html += renderSection('Profile & Template', profile);
    html += renderSection('Status', status);
    html += renderSection('Connectivity', connectivity);
    html += renderSection('Policies', policies);

    // Determine best title for remaining config
    const cfgTitle = nodeData.type === 'policy' ? 'Policy Configuration' : 'Configuration';
    html += renderSection(cfgTitle, config);

    // Freeform text (Notes / Description) at the very bottom, de-emphasized
    if (freetext.length) {
      html += '<div class="detail-section"><div class="detail-section-title">Notes</div>';
      freetext.forEach(line => {
        const sep = line.indexOf(': ');
        const label = sep > 0 ? line.substring(0, sep).toLowerCase() : '';
        const text = (sep > 0 && ['notes', 'description'].includes(label))
          ? line.substring(sep + 2) : line;
        html += `<p style="color:var(--text-muted);line-height:1.6;font-size:12px;margin:4px 0;word-break:break-word;font-style:italic">${esc(text)}</p>`;
      });
      html += '</div>';
    }

    // Fallback: if nothing rendered, show raw
    if (!html) {
      html = `<div class="detail-section"><div class="detail-section-title">Details</div>`;
      html += `<p style="color:var(--text-muted);line-height:1.6;font-size:12px;word-break:break-word">${esc(nodeData.description)}</p></div>`;
    }
    return html;
  }

  // ── Node click → detail panel (unified) ──
  async function handleNodeClick(nodeData) {
    detailPanel.classList.remove('hidden');
    detailTitle.textContent = nodeData.name || 'Details';
    let html = '';

    // VLAN list → show full list in side panel
    if (nodeData.type === 'vlan_list' && nodeData.vlanIds) {
      const ids = nodeData.vlanIds;
      html += `<div class="detail-section"><div class="detail-section-title">VLAN Summary</div>`;
      html += `<div class="detail-row"><span class="detail-key">Total VLANs</span><span class="detail-value">${ids.length}</span></div>`;
      html += `<div class="detail-row"><span class="detail-key">Range</span><span class="detail-value" style="word-break:break-all;font-size:11px;line-height:1.5">${esc(nodeData.vlanRanges || '')}</span></div>`;
      html += `</div><div class="detail-section"><div class="detail-section-title">All VLANs</div>`;
      html += `<div class="detail-vlan-list">${ids.map(v => esc(v)).join(', ')}</div></div>`;
      detailContent.innerHTML = html;
      return;
    }

    // Severity / disjoint / error nodes
    if (nodeData.severity || nodeData.disjoint) {
      if (nodeData.description) {
        html += `<div class="detail-section"><div class="detail-section-title">Description</div><p style="color:var(--text-muted);line-height:1.6;font-size:12px;">${esc(nodeData.description)}</p></div>`;
      }
      if (nodeData.severity) {
        html += `<div class="detail-row"><span class="detail-key">Severity</span><span class="detail-value" style="color:${severityColour(nodeData.severity)}">${esc(nodeData.severity.toUpperCase())}</span></div>`;
      }
      if (nodeData.disjoint) {
        html += `<div class="detail-section"><div class="detail-section-title" style="color:#dc2626">Disjoint VLAN</div><p style="color:var(--text-muted);font-size:12px;">This VLAN exists on only one Fabric Interconnect. Ensure both FIs carry matching VLANs for redundancy.</p></div>`;
      }
      detailContent.innerHTML = html || '<div class="detail-loading">No additional details.</div>';
      return;
    }

    // Any node with a description (techsupport nodes: policies, hw, profiles, etc.)
    if (nodeData.description && !nodeData.moid) {
      html += renderStructuredDescription(nodeData);
      detailContent.innerHTML = html;
      return;
    }

    // Intersight API policy detail
    if (!nodeData.moid || !nodeData.objectType) return;

    if (dataSource !== 'intersight' && dataSource !== 'hybrid') {
      detailContent.innerHTML = '<div class="detail-loading">Full policy details require a live Intersight connection.<br>Upload techsupport + connect to Intersight API for hybrid mode.</div>';
      return;
    }

    detailContent.innerHTML = '<div class="detail-loading">Loading policy details…</div>';
    try {
      const data = await apiGet(`/policy/${nodeData.objectType}/${nodeData.moid}`);
      renderDetail(data);
    } catch (err) {
      detailContent.innerHTML = `<div class="form-error">${esc(err.message)}</div>`;
    }
  }

  function severityColour(sev) {
    return { critical: '#dc2626', major: '#f97316', minor: '#eab308', warning: '#64748b', info: '#94a3b8' }[sev] || '#94a3b8';
  }

  function renderDetail(data) {
    const skip = new Set(['ClassId','ObjectType','AccountMoid','DomainGroupMoid','SharedScope','Ancestors','Parent',
      'PermissionResources','Profiles','Organization','PolicyBucket','SwitchProfiles','ClusterProfiles',
      'RunningWorkflows','ResultEntries','VersionContext','SrcTemplate','ConfigContext','link','href']);
    const meta = {}, config = {};
    for (const [k, v] of Object.entries(data)) {
      if (skip.has(k) || v === null || v === undefined) continue;
      if (Array.isArray(v) && !v.length) continue;
      if (typeof v === 'object' && !Array.isArray(v) && !Object.keys(v).length) continue;
      if (['Moid','Name','Description','Tags','CreateTime','ModTime'].includes(k)) meta[k] = v;
      else config[k] = v;
    }
    let html = '';
    if (Object.keys(meta).length) {
      html += '<div class="detail-section"><div class="detail-section-title">General</div>';
      for (const [k,v] of Object.entries(meta)) html += fmtRow(k,v);
      html += '</div>';
    }
    if (Object.keys(config).length) {
      html += '<div class="detail-section"><div class="detail-section-title">Configuration</div>';
      for (const [k,v] of Object.entries(config)) html += fmtRow(k,v);
      html += '</div>';
    }
    detailContent.innerHTML = html || '<div class="detail-loading">No configuration data.</div>';
  }

  function fmtRow(key, value) {
    const label = key.replace(/([A-Z])/g, ' $1').trim();
    if (typeof value === 'boolean') {
      const cls = value ? 'bool-true' : 'bool-false';
      return `<div class="detail-row"><span class="detail-key">${esc(label)}</span><span class="detail-value ${cls}">${value ? 'Enabled' : 'Disabled'}</span></div>`;
    }
    if (typeof value === 'object' && !Array.isArray(value)) {
      if (value.ClassId === 'mo.MoRef') return `<div class="detail-row"><span class="detail-key">${esc(label)}</span><span class="detail-value">${esc(value.ObjectType || value.Moid || '')}</span></div>`;
      let r = '';
      for (const [k,v] of Object.entries(value)) { if (v != null) r += fmtRow(`${label} › ${k}`, v); }
      return r;
    }
    if (Array.isArray(value)) {
      if (!value.length) return '';
      if (typeof value[0] === 'object') {
        let r = `<div class="detail-row"><span class="detail-key">${esc(label)}</span><span class="detail-value">${value.length} items</span></div>`;
        value.forEach((item, i) => {
          if (typeof item === 'object' && item) {
            const il = item.Name || item.Key || `#${i+1}`;
            for (const [k,v] of Object.entries(item)) { if (!['ClassId','ObjectType','link','Moid'].includes(k)) r += fmtRow(`${il} › ${k}`, v); }
          }
        });
        return r;
      }
      return `<div class="detail-row"><span class="detail-key">${esc(label)}</span><span class="detail-value">${esc(value.join(', '))}</span></div>`;
    }
    return `<div class="detail-row"><span class="detail-key">${esc(label)}</span><span class="detail-value">${esc(String(value))}</span></div>`;
  }

  detailClose.addEventListener('click', () => detailPanel.classList.add('hidden'));

  // ── VLAN floating modal ──
  function showVlanModal(title, vlanIds, ranges) {
    vlanModalTitle.textContent = `${title} — ${vlanIds.length} VLANs`;
    let html = `<div class="vlan-summary"><span><strong>${vlanIds.length}</strong> VLANs</span></div>`;
    html += `<div class="vlan-ranges"><strong>Range notation:</strong> ${esc(ranges)}</div>`;
    html += `<div class="vlan-csv">${vlanIds.map(v => esc(v)).join(', ')}</div>`;
    vlanModalBody.innerHTML = html;
    vlanModal.classList.remove('hidden');
    // Center on first open
    vlanModal.style.top = '50%';
    vlanModal.style.left = '50%';
    vlanModal.style.transform = 'translate(-50%, -50%)';
  }

  vlanModalClose.addEventListener('click', () => vlanModal.classList.add('hidden'));

  // Make VLAN modal draggable by its header
  (function initDrag() {
    let dragging = false, startX = 0, startY = 0, origX = 0, origY = 0;
    vlanModalHeader.addEventListener('mousedown', (e) => {
      dragging = true;
      const rect = vlanModal.getBoundingClientRect();
      origX = rect.left; origY = rect.top;
      startX = e.clientX; startY = e.clientY;
      vlanModal.style.transform = 'none';
      vlanModal.style.left = origX + 'px';
      vlanModal.style.top = origY + 'px';
      e.preventDefault();
    });
    document.addEventListener('mousemove', (e) => {
      if (!dragging) return;
      vlanModal.style.left = (origX + e.clientX - startX) + 'px';
      vlanModal.style.top = (origY + e.clientY - startY) + 'px';
    });
    document.addEventListener('mouseup', () => { dragging = false; });
  })();

  // ── Toolbar ──
  btnRefresh.addEventListener('click', () => loadHierarchy(true));
  btnExpandAll.addEventListener('click', () => { viz.expandAll(); nodeCountEl.textContent = `${viz.getNodeCount()} nodes`; });
  btnCollapseAll.addEventListener('click', () => viz.collapseAll());
  btnExport.addEventListener('click', (e) => {
    let menu = document.getElementById('export-dropdown');
    if (menu) { menu.remove(); return; }
    menu = document.createElement('div');
    menu.id = 'export-dropdown';
    menu.className = 'export-dropdown';
    const views = [
      { key: 'physical',  label: 'Physical View' },
      { key: 'logical',   label: 'Logical View' },
      { key: 'topology',  label: 'Topology View' },
    ];
    menu.innerHTML = views.map(v =>
      `<button data-view="${v.key}" data-fmt="html">${v.label} (.html)</button>`
    ).join('') + `<div style="border-top:1px solid var(--border-light)"></div>` +
    `<button data-fmt="json">Current View as JSON</button>`;

    const rect = btnExport.getBoundingClientRect();
    menu.style.position = 'fixed';
    menu.style.top = (rect.bottom + 4) + 'px';
    menu.style.right = (window.innerWidth - rect.right) + 'px';
    document.body.appendChild(menu);

    menu.addEventListener('click', async (ev) => {
      const btn = ev.target.closest('button');
      if (!btn) return;
      const fmt = btn.dataset.fmt;
      if (!fmt) return;
      menu.remove();

      if (fmt === 'json') {
        try {
          const viewParam = (dataSource === 'techsupport' || dataSource === 'hybrid') ? `?view=${currentView}` : '';
          const r = await fetch(`${API}/export${viewParam}`);
          if (!r.ok) throw new Error('Export failed');
          const b = await r.blob(), u = URL.createObjectURL(b), a = document.createElement('a');
          a.href = u; a.download = `intersight_${currentView}.json`; a.click(); URL.revokeObjectURL(u);
        } catch (err) { statusText.textContent = `Export error: ${err.message}`; }
      } else if (fmt === 'html') {
        const viewKey = btn.dataset.view;
        const viewLabel = views.find(v => v.key === viewKey)?.label || viewKey;
        statusText.textContent = `Exporting ${viewLabel}…`;
        try {
          const params = new URLSearchParams({ view: viewKey });
          const r = await fetch(`${API}/hierarchy?${params}`);
          if (!r.ok) throw new Error('Failed to fetch view data');
          const treeData = await r.json();

          const tmpViz = new TreeVisualizer(null);
          tmpViz.root = d3.hierarchy(treeData);
          tmpViz.treeLayout = d3.tree().nodeSize([tmpViz.nodeHeight + 6, tmpViz.depthSpacing]);
          const htmlStr = tmpViz.exportHTML(viewLabel + ' — Cisco Intersight Visualiser');

          if (!htmlStr) { statusText.textContent = 'No data to export'; return; }
          const blob = new Blob([htmlStr], { type: 'text/html' });
          const u = URL.createObjectURL(blob), a = document.createElement('a');
          a.href = u; a.download = `intersight_${viewKey}.html`; a.click(); URL.revokeObjectURL(u);
          statusText.textContent = `Exported ${viewLabel}`;
        } catch (err) { statusText.textContent = `Export error: ${err.message}`; }
      }
    });

    const dismiss = (ev) => { if (!menu.contains(ev.target) && ev.target !== btnExport) { menu.remove(); document.removeEventListener('click', dismiss); } };
    setTimeout(() => document.addEventListener('click', dismiss), 0);
  });

  // ── Add Files / Add API (toolbar actions while active) ──
  btnAddFiles.addEventListener('click', () => {
    pendingFiles = [];
    renderFileList();
    hideError(uploadError);
    uploadProgress.classList.add('hidden');
    uploadIsAdd = true;
    btnUploadGo.textContent = 'Upload & Merge';
    uploadModal.classList.remove('hidden');
  });
  btnAddApi.addEventListener('click', () => {
    connectModal.classList.remove('hidden');
  });

  // ── Search ──
  let searchTimeout = null;
  searchInput.addEventListener('input', () => {
    clearTimeout(searchTimeout);
    searchTimeout = setTimeout(() => {
      const q = searchInput.value, c = viz.search(q);
      if (c >= 0) nodeCountEl.textContent = q ? `${c} matches` : `${viz.getNodeCount()} nodes`;
    }, 200);
  });

  // ── Keyboard ──
  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') { detailPanel.classList.add('hidden'); connectModal.classList.add('hidden'); uploadModal.classList.add('hidden'); vlanModal.classList.add('hidden'); }
    if ((e.metaKey || e.ctrlKey) && e.key === 'f') { e.preventDefault(); searchInput.focus(); }
  });

  // ── Auto-check ──
  (async function () {
    try {
      const s = await apiGet('/status');
      if (s.connected) {
        let label;
        if (s.source === 'hybrid') {
          label = `Intersight + ${(s.files || []).length} file(s)`;
        } else if (s.source === 'techsupport') {
          const files = s.files || [];
          label = files.length === 1 ? files[0] : `${files.length} techsupport files`;
        } else {
          label = 'Intersight';
        }
        setActive(s.source || 'intersight', label);
        await loadHierarchy();
      }
    } catch (_) {}
  })();

  function esc(s) { const el = document.createElement('span'); el.textContent = s || ''; return el.innerHTML; }
})();
