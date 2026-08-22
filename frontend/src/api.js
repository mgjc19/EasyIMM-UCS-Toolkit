const BASE = '';

async function request(path, options = {}) {
  const res = await fetch(`${BASE}${path}`, {
    headers: { 'Content-Type': 'application/json' },
    ...options,
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || res.statusText);
  }
  return res.json();
}

export const api = {
  getTypes: () => request('/api/schema/types'),
  getSchema: (category, type) => request(`/api/schema/${category}/${type}`),

  getTree: () => request('/api/tree'),
  getOrgs: () => request('/api/orgs'),
  createOrg: (name) => request('/api/orgs', { method: 'POST', body: JSON.stringify({ name }) }),
  deleteOrg: (name) => request(`/api/orgs/${name}`, { method: 'DELETE' }),

  getOrgResources: (org) => request(`/api/resources/${org}`),
  getResources: (org, category, type) => request(`/api/resources/${org}/${category}/${type}`),
  saveResource: (org, category, type, data) =>
    request(`/api/resources/${org}/${category}/${type}`, {
      method: 'POST',
      body: JSON.stringify({ data }),
    }),
  deleteResource: (org, category, type, name) =>
    request(`/api/resources/${org}/${category}/${type}/${name}`, { method: 'DELETE' }),
  cloneResource: (payload) =>
    request('/api/resources/clone', { method: 'POST', body: JSON.stringify(payload) }),

  getSettings: () => request('/api/settings'),
  saveSettings: (settings) =>
    request('/api/settings', { method: 'PUT', body: JSON.stringify(settings) }),
  clearSettings: () => request('/api/settings', { method: 'DELETE' }),
  testConnection: () => request('/api/settings/test', { method: 'POST' }),

  runTerraform: (action) => request(`/api/terraform/${action}`, { method: 'POST' }),
  validateConfig: () => request('/api/terraform/validate-config', { method: 'POST' }),

  importTestConnection: () => request('/api/import/test', { method: 'POST' }),
  importListOrgs: () => request('/api/import/orgs'),
  importListResources: (orgFilter, categories) =>
    request('/api/import/resources', {
      method: 'POST',
      body: JSON.stringify({ org_filter: orgFilter || null, categories: categories || null }),
    }),
  importListByType: (category, type, org) =>
    request(`/api/import/resources/${category}/${type}${org ? `?org=${org}` : ''}`),

  triggerSync: (orgFilter) =>
    request('/api/sync', {
      method: 'POST',
      body: JSON.stringify({ org_filter: orgFilter || null }),
    }),
  getSyncStatus: () => request('/api/sync/status'),
  listSyncedDomains: () => request('/api/sync/domains'),
  unsyncDomain: (domainName) =>
    request(`/api/sync/domains/${encodeURIComponent(domainName)}`, { method: 'DELETE' }),
  unsyncAll: () => request('/api/sync/all', { method: 'DELETE' }),

  importLocalPreview: (path) =>
    request('/api/import-local/preview', { method: 'POST', body: JSON.stringify({ path }) }),
  importLocalApply: (path) =>
    request('/api/import-local/apply', { method: 'POST', body: JSON.stringify({ path }) }),

  downloadFullState: () => window.open('/api/export/full-state', '_blank'),
  downloadFullStateXml: () => window.open('/api/export/full-state-xml', '_blank'),
  previewTechShared: () => request('/api/export/preview/tech-shared'),
  previewTechUcs: () => request('/api/export/preview/tech-ucs'),
  downloadTechShared: () => window.open('/api/export/tech-shared', '_blank'),
  downloadTechUcs: () => window.open('/api/export/tech-ucs', '_blank'),

  getRedfishSchemas: () => request('/api/redfish/schemas'),
  getRedfishServer: () => request('/api/redfish/server'),
  saveRedfishServer: (data) =>
    request('/api/redfish/server', { method: 'PUT', body: JSON.stringify(data) }),
  getRedfishConfigs: () => request('/api/redfish/config'),
  getRedfishConfig: (key) => request(`/api/redfish/config/${key}`),
  saveRedfishConfig: (key, data) =>
    request(`/api/redfish/config/${key}`, {
      method: 'PUT',
      body: JSON.stringify({ resource_key: key, data }),
    }),
  generateRedfishTf: () => request('/api/redfish/generate', { method: 'POST' }),
  runRedfishTerraform: (action) => request(`/api/redfish/terraform/${action}`, { method: 'POST' }),
  directPushAll: () => request('/api/redfish/direct-push', { method: 'POST' }),
  directPushSingle: (key) => request(`/api/redfish/direct-push/${key}`, { method: 'POST' }),
  readRedfishLive: () => request('/api/redfish/live'),
};
