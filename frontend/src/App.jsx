import { useState, useEffect, useCallback, useRef } from 'react';
import { ThemeProvider } from '@mui/material/styles';
import CssBaseline from '@mui/material/CssBaseline';
import Box from '@mui/material/Box';
import AppBar from '@mui/material/AppBar';
import Toolbar from '@mui/material/Toolbar';
import Typography from '@mui/material/Typography';
import IconButton from '@mui/material/IconButton';
import SettingsIcon from '@mui/icons-material/Settings';
import RefreshIcon from '@mui/icons-material/Refresh';
import CloudDownloadIcon from '@mui/icons-material/CloudDownload';
import FileDownloadIcon from '@mui/icons-material/FileDownload';
import DownloadForOfflineIcon from '@mui/icons-material/DownloadForOffline';
import SyncIcon from '@mui/icons-material/Sync';
import SyncDisabledIcon from '@mui/icons-material/SyncDisabled';
import FolderOpenIcon from '@mui/icons-material/FolderOpen';
import CircularProgress from '@mui/material/CircularProgress';
import Chip from '@mui/material/Chip';
import Menu from '@mui/material/Menu';
import MenuItem from '@mui/material/MenuItem';
import ListItemIcon from '@mui/material/ListItemIcon';
import ListItemText from '@mui/material/ListItemText';
import Tooltip from '@mui/material/Tooltip';
import Snackbar from '@mui/material/Snackbar';
import Alert from '@mui/material/Alert';
import Dialog from '@mui/material/Dialog';
import DialogTitle from '@mui/material/DialogTitle';
import DialogContent from '@mui/material/DialogContent';
import DialogActions from '@mui/material/DialogActions';
import Button from '@mui/material/Button';
import TextField from '@mui/material/TextField';
import Tabs from '@mui/material/Tabs';
import Tab from '@mui/material/Tab';
import DeviceHubIcon from '@mui/icons-material/DeviceHub';
import MemoryIcon from '@mui/icons-material/Memory';
import BubbleChartIcon from '@mui/icons-material/BubbleChart';
import CodeIcon from '@mui/icons-material/Code';
import DataObjectIcon from '@mui/icons-material/DataObject';
import { dump as yamlDump } from 'js-yaml';
import theme from './theme';
import { api } from './api';
import TreeNavigator from './components/TreeNavigator';
import ResourcePanel from './components/ResourcePanel';
import SettingsDialog from './components/SettingsDialog';
import TerraformPanel from './components/TerraformPanel';
import CloneDialog from './components/CloneDialog';
import ImportDialog from './components/ImportDialog';
import RedfishPanel from './components/RedfishPanel';
import ExportDialog from './components/ExportDialog';
import SiteDetailPanel from './components/SiteDetailPanel';

export default function App() {
  const [mainTab, setMainTab] = useState(0);
  const [tree, setTree] = useState(null);
  const [types, setTypes] = useState(null);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [importOpen, setImportOpen] = useState(false);
  const [exportOpen, setExportOpen] = useState(false);
  const [localImportOpen, setLocalImportOpen] = useState(false);
  const [localImportPath, setLocalImportPath] = useState('');
  const [localImportPreview, setLocalImportPreview] = useState(null);
  const [localImporting, setLocalImporting] = useState(false);
  const [fullStateConfirmOpen, setFullStateConfirmOpen] = useState(false);
  const [toast, setToast] = useState(null);

  const [panelSchema, setPanelSchema] = useState(null);
  const [panelOrg, setPanelOrg] = useState('');
  const [panelCategory, setPanelCategory] = useState('');
  const [panelType, setPanelType] = useState('');
  const [panelData, setPanelData] = useState(null);

  const [selectedSiteOrg, setSelectedSiteOrg] = useState(null);
  const [selectedSiteOrgData, setSelectedSiteOrgData] = useState(null);

  const [addOrgOpen, setAddOrgOpen] = useState(false);
  const [newOrgName, setNewOrgName] = useState('');

  const [cloneOpen, setCloneOpen] = useState(false);
  const [cloneInfo, setCloneInfo] = useState({});

  const [deleteConfirm, setDeleteConfirm] = useState(null);

  const [orgDownloadAnchor, setOrgDownloadAnchor] = useState(null);
  const [orgDownloadTarget, setOrgDownloadTarget] = useState(null);

  const loadTree = useCallback(async () => {
    try {
      const [treeData, typesData] = await Promise.all([api.getTree(), api.getTypes()]);
      setTree(treeData);
      setTypes(typesData);
    } catch {
      setToast({ severity: 'error', text: 'Failed to load data. Is the backend running?' });
    }
  }, []);

  useEffect(() => { loadTree(); }, [loadTree]);

  const [syncStatus, setSyncStatus] = useState('idle');
  const [syncProgress, setSyncProgress] = useState(null);
  const [syncLastTime, setSyncLastTime] = useState(null);
  const syncPollRef = useRef(null);

  const handleSync = useCallback(async () => {
    try {
      await api.triggerSync();
      setSyncStatus('running');
      setToast({ severity: 'info', text: 'Sync from Intersight started...' });
      syncPollRef.current = setTimeout(async function poll() {
        try {
          const s = await api.getSyncStatus();
          setSyncStatus(s.status);
          setSyncProgress(s.progress);
          if (s.last_synced) setSyncLastTime(new Date(s.last_synced * 1000));
          if (s.status === 'running') {
            syncPollRef.current = setTimeout(poll, 1500);
          } else {
            loadTree();
            if (s.error) {
              setToast({ severity: 'error', text: `Sync failed: ${s.error}` });
            } else {
              const total = Object.values(s.synced_counts || {}).reduce((a, b) => a + b, 0);
              setToast({ severity: 'success', text: `Sync complete: ${total} resources imported` });
            }
          }
        } catch { /* ignore */ }
      }, 1500);
    } catch (e) {
      setToast({ severity: 'error', text: e.message });
    }
  }, [loadTree]);

  useEffect(() => {
    return () => {
      if (syncPollRef.current) clearTimeout(syncPollRef.current);
    };
  }, []);

  const [unsyncConfirmOpen, setUnsyncConfirmOpen] = useState(false);
  const [unsyncLoading, setUnsyncLoading] = useState(false);

  const handleUnsyncAll = async () => {
    setUnsyncConfirmOpen(false);
    setUnsyncLoading(true);
    try {
      await api.unsyncAll();
      setToast({ severity: 'success', text: 'All synced domain data removed' });
      closePanel();
      setSelectedSiteOrg(null);
      setSelectedSiteOrgData(null);
      await loadTree();
    } catch (e) {
      setToast({ severity: 'error', text: e.message });
    } finally {
      setUnsyncLoading(false);
    }
  };

  const handleLocalImportPreview = async () => {
    if (!localImportPath.trim()) return;
    try {
      const result = await api.importLocalPreview(localImportPath.trim());
      setLocalImportPreview(result);
    } catch (e) {
      setToast({ severity: 'error', text: e.message });
    }
  };

  const handleLocalImportApply = async () => {
    setLocalImporting(true);
    try {
      const result = await api.importLocalApply(localImportPath.trim());
      setToast({ severity: 'success', text: `Imported ${result.imported} resources` });
      setLocalImportOpen(false);
      setLocalImportPreview(null);
      setLocalImportPath('');
      loadTree();
    } catch (e) {
      setToast({ severity: 'error', text: e.message });
    } finally {
      setLocalImporting(false);
    }
  };

  const openResource = async (org, category, type, data) => {
    try {
      const s = await api.getSchema(category, type);
      setPanelSchema(s);
      setPanelOrg(org);
      setPanelCategory(category);
      setPanelType(type);
      setPanelData(data);
      setSelectedSiteOrg(null);
      setSelectedSiteOrgData(null);
    } catch {
      setToast({ severity: 'warning', text: `Schema not available for ${type}` });
    }
  };

  const closePanel = () => {
    setPanelSchema(null);
    setPanelData(null);
    setSelectedSiteOrg(null);
    setSelectedSiteOrgData(null);
  };

  const handleSelect = (org, category, type, data) => openResource(org, category, type, data);
  const handleAdd = (org, category, type) => openResource(org, category, type, null);

  const handleOrgSelect = (org, orgData) => {
    setPanelSchema(null);
    setPanelData(null);
    setSelectedSiteOrg(org);
    setSelectedSiteOrgData(orgData);
  };

  const handleSave = async (data) => {
    try {
      await api.saveResource(panelOrg, panelCategory, panelType, data);
      setToast({ severity: 'success', text: `Saved ${data.name}` });
      loadTree();
    } catch (e) {
      setToast({ severity: 'error', text: e.message });
    }
  };

  const handleDelete = (org, category, type, name) => {
    setDeleteConfirm({ org, category, type, name });
  };

  const confirmDelete = async () => {
    const { org, category, type, name } = deleteConfirm;
    try {
      if (!category) {
        await api.deleteOrg(org);
        setToast({ severity: 'success', text: `Deleted organization ${org}` });
      } else {
        await api.deleteResource(org, category, type, name);
        setToast({ severity: 'success', text: `Deleted ${name}` });
      }
      if (panelOrg === org && panelCategory === category && panelType === type && panelData?.name === name) {
        closePanel();
      }
      loadTree();
    } catch (e) {
      setToast({ severity: 'error', text: e.message });
    }
    setDeleteConfirm(null);
  };

  const handleCloneOpen = (org, category, type, name) => {
    setCloneInfo({ srcOrg: org, category, resourceType: type, srcName: name });
    setCloneOpen(true);
  };

  const handleClone = async (payload) => {
    try {
      await api.cloneResource(payload);
      setToast({ severity: 'success', text: `Cloned ${payload.src_name} as ${payload.dst_name}` });
      loadTree();
    } catch (e) {
      setToast({ severity: 'error', text: e.message });
    }
  };

  const handleAddOrg = async () => {
    if (!newOrgName.trim()) return;
    try {
      await api.createOrg(newOrgName.trim());
      setToast({ severity: 'success', text: `Created organization ${newOrgName}` });
      setAddOrgOpen(false);
      setNewOrgName('');
      loadTree();
    } catch (e) {
      setToast({ severity: 'error', text: e.message });
    }
  };

  const handleOrgDownload = (org, orgData, event) => {
    setOrgDownloadTarget(org);
    setOrgDownloadAnchor(event.currentTarget);
    setSelectedSiteOrgData(orgData);
  };

  const getOrgExportData = (org, rawOrgData) => {
    const raw = rawOrgData || tree?.[org];
    if (!raw) return {};

    const cleaned = {};
    for (const cat of ['pools', 'policies', 'profiles', 'templates']) {
      const catData = raw[cat];
      if (!catData || typeof catData !== 'object') continue;
      cleaned[cat] = {};
      for (const [type, items] of Object.entries(catData)) {
        if (!Array.isArray(items) || items.length === 0) continue;
        cleaned[cat][type] = items.map((item) =>
          item && typeof item === 'object' && item.data ? item.data : item
        );
      }
    }
    return { [org]: cleaned };
  };

  const objectToXml = (obj, rootTag = 'easyimm') => {
    const escape = (s) =>
      String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');

    const convert = (key, value, depth) => {
      const p = '  '.repeat(depth);
      const tag = key.replace(/[^a-zA-Z0-9_.\-]/g, '_');
      if (value === null || value === undefined) return '';
      if (Array.isArray(value)) {
        return value.map((item) => {
          if (typeof item === 'object' && item !== null) {
            const inner = Object.entries(item).map(([k, v]) => convert(k, v, depth + 1)).join('');
            return `${p}<${tag}>\n${inner}${p}</${tag}>\n`;
          }
          return `${p}<${tag}>${escape(item)}</${tag}>\n`;
        }).join('');
      }
      if (typeof value === 'object') {
        const inner = Object.entries(value).map(([k, v]) => convert(k, v, depth + 1)).join('');
        return `${p}<${tag}>\n${inner}${p}</${tag}>\n`;
      }
      return `${p}<${tag}>${escape(value)}</${tag}>\n`;
    };

    let xml = `<?xml version="1.0" encoding="UTF-8"?>\n<${rootTag}>\n`;
    Object.entries(obj).forEach(([k, v]) => { xml += convert(k, v, 1); });
    xml += `</${rootTag}>\n`;
    return xml;
  };

  const triggerFileDownload = (content, filename, mimeType) => {
    const blob = new Blob([content], { type: mimeType });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = filename;
    a.click();
    URL.revokeObjectURL(url);
  };

  const handleOrgDownloadYaml = () => {
    const data = getOrgExportData(orgDownloadTarget, selectedSiteOrgData);
    const yamlStr = yamlDump(data, { lineWidth: 120, noRefs: true, sortKeys: false });
    triggerFileDownload(yamlStr, `${orgDownloadTarget}.ezi.yaml`, 'application/x-yaml');
    setOrgDownloadAnchor(null);
  };

  const handleOrgDownloadXml = () => {
    const data = getOrgExportData(orgDownloadTarget, selectedSiteOrgData);
    const xmlStr = objectToXml(data, 'easyimm');
    triggerFileDownload(xmlStr, `${orgDownloadTarget}.xml`, 'application/xml');
    setOrgDownloadAnchor(null);
  };

  const orgs = tree ? Object.keys(tree) : [];
  const showPanel = !!panelSchema;
  const showSiteDetail = !!selectedSiteOrg;

  return (
    <ThemeProvider theme={theme}>
      <CssBaseline />
      <Box sx={{ display: 'flex', flexDirection: 'column', height: '100vh' }}>
        {/* Header */}
        <AppBar position="static" elevation={0} sx={{ bgcolor: 'background.paper', borderBottom: '1px solid', borderColor: 'divider' }}>
          <Toolbar variant="dense" sx={{ gap: 1 }}>
            <Typography variant="h6" sx={{ fontWeight: 700, color: 'primary.main', mr: 1 }}>
              UCS Toolkit
            </Typography>

            <Tabs
              value={mainTab}
              onChange={(_, v) => setMainTab(v)}
              textColor="inherit"
              sx={{
                flex: 1, minHeight: 40,
                '& .MuiTab-root': { minHeight: 40, textTransform: 'none', fontSize: 13, fontWeight: 600 },
                '& .Mui-selected': { color: 'primary.main' },
              }}
              TabIndicatorProps={{ sx: { bgcolor: 'primary.main' } }}
            >
              <Tab icon={<DeviceHubIcon sx={{ fontSize: 18 }} />} iconPosition="start" label="Easy IMM" />
              <Tab icon={<MemoryIcon sx={{ fontSize: 18 }} />} iconPosition="start" label="Redfish" />
              <Tab icon={<BubbleChartIcon sx={{ fontSize: 18 }} />} iconPosition="start" label="Visualiser" />
            </Tabs>

            {mainTab === 0 && (
              <>
                <Tooltip title={syncStatus === 'running'
                  ? `Syncing${syncProgress ? ': ' + syncProgress : '...'}`
                  : syncLastTime
                    ? `Sync from Intersight (last: ${syncLastTime.toLocaleTimeString()})`
                    : 'Sync from Intersight — pull live configs into the tree'
                }>
                  <span>
                    <IconButton
                      onClick={handleSync}
                      color="inherit"
                      disabled={syncStatus === 'running'}
                    >
                      {syncStatus === 'running'
                        ? <CircularProgress size={20} color="inherit" />
                        : <SyncIcon />
                      }
                    </IconButton>
                  </span>
                </Tooltip>
                {syncStatus === 'running' && syncProgress && (
                  <Chip
                    label={syncProgress}
                    size="small"
                    variant="outlined"
                    sx={{ fontSize: 11, height: 22, mr: 0.5 }}
                  />
                )}
                <Tooltip title="Unsync — remove all synced domain data">
                  <span>
                    <IconButton onClick={() => setUnsyncConfirmOpen(true)} color="inherit" disabled={unsyncLoading}>
                      {unsyncLoading ? <CircularProgress size={20} color="inherit" /> : <SyncDisabledIcon />}
                    </IconButton>
                  </span>
                </Tooltip>
                <Tooltip title="Import from Intersight (browse)">
                  <IconButton onClick={() => setImportOpen(true)} color="inherit">
                    <CloudDownloadIcon />
                  </IconButton>
                </Tooltip>
                <Tooltip title="Import from local Easy IMM workspace">
                  <IconButton onClick={() => setLocalImportOpen(true)} color="inherit">
                    <FolderOpenIcon />
                  </IconButton>
                </Tooltip>
                <Tooltip title="Export full state (YAML / XML)">
                  <IconButton onClick={() => setFullStateConfirmOpen(true)} color="inherit">
                    <DownloadForOfflineIcon />
                  </IconButton>
                </Tooltip>
                <Tooltip title="Refresh">
                  <IconButton onClick={loadTree} color="inherit"><RefreshIcon /></IconButton>
                </Tooltip>
              </>
            )}
            <Tooltip title="Export to CiscoIQ (Doc-as-Code)">
              <IconButton onClick={() => setExportOpen(true)} color="inherit"><FileDownloadIcon /></IconButton>
            </Tooltip>
            <Tooltip title="Settings">
              <IconButton onClick={() => setSettingsOpen(true)} color="inherit"><SettingsIcon /></IconButton>
            </Tooltip>
          </Toolbar>
        </AppBar>

        {/* Tab content */}
        {mainTab === 0 && (
          <>
            {/* Easy IMM: tree (left) + resource panel (right) */}
            <Box sx={{ flex: 1, display: 'flex', overflow: 'hidden' }}>
              <Box sx={{ width: 320, minWidth: 280, borderRight: '1px solid', borderColor: 'divider', overflow: 'auto', bgcolor: 'background.paper' }}>
                <TreeNavigator
                  tree={tree} types={types}
                  onSelect={handleSelect} onAdd={handleAdd}
                  onDelete={handleDelete} onClone={handleCloneOpen}
                  onAddOrg={() => setAddOrgOpen(true)}
                  onDownload={handleOrgDownload}
                  onOrgSelect={handleOrgSelect}
                />
              </Box>

              <Box sx={{ flex: 1, overflow: 'hidden' }}>
                {showPanel ? (
                  <ResourcePanel
                    onClose={closePanel}
                    onSave={handleSave}
                    schema={panelSchema}
                    initialData={panelData}
                    org={panelOrg}
                    category={panelCategory}
                    resourceType={panelType}
                    tree={tree}
                  />
                ) : showSiteDetail ? (
                  <SiteDetailPanel
                    org={selectedSiteOrg}
                    orgData={selectedSiteOrgData}
                    onClose={closePanel}
                    onDownloadYaml={() => {
                      const data = getOrgExportData(selectedSiteOrg, selectedSiteOrgData);
                      const yamlStr = yamlDump(data, { lineWidth: 120, noRefs: true, sortKeys: false });
                      triggerFileDownload(yamlStr, `${selectedSiteOrg}.ezi.yaml`, 'application/x-yaml');
                    }}
                    onDownloadXml={() => {
                      const data = getOrgExportData(selectedSiteOrg, selectedSiteOrgData);
                      const xmlStr = objectToXml(data, 'easyimm');
                      triggerFileDownload(xmlStr, `${selectedSiteOrg}.xml`, 'application/xml');
                    }}
                  />
                ) : (
                  <Box sx={{ height: '100%', display: 'flex', alignItems: 'center', justifyContent: 'center', color: 'text.secondary' }}>
                    <Box sx={{ textAlign: 'center', maxWidth: 400, px: 3 }}>
                      <Typography variant="h6" gutterBottom>Welcome to Easy IMM</Typography>
                      <Typography variant="body2">
                        Select a resource from the tree on the left to edit it, or click the + button to create a new one.
                        Use the Terraform panel below to validate, plan, and apply your configuration.
                      </Typography>
                    </Box>
                  </Box>
                )}
              </Box>
            </Box>
            <TerraformPanel />
          </>
        )}

        {mainTab === 1 && (
          <Box sx={{ flex: 1, overflow: 'hidden' }}>
            <RedfishPanel />
          </Box>
        )}

        {mainTab === 2 && (
          <Box sx={{ flex: 1, overflow: 'hidden' }}>
            <iframe
              src="/visualiser/"
              title="Intersight Visualiser"
              style={{ width: '100%', height: '100%', border: 'none' }}
            />
          </Box>
        )}
      </Box>

      {/* Settings dialog */}
      <SettingsDialog open={settingsOpen} onClose={() => setSettingsOpen(false)} />

      {/* Import dialog */}
      <ImportDialog open={importOpen} onClose={() => setImportOpen(false)} />

      {/* Export dialog */}
      <ExportDialog open={exportOpen} onClose={() => setExportOpen(false)} />

      {/* Clone dialog */}
      <CloneDialog
        open={cloneOpen} onClose={() => setCloneOpen(false)} onClone={handleClone}
        orgs={orgs} {...cloneInfo}
      />

      {/* Add organization dialog */}
      <Dialog open={addOrgOpen} onClose={() => setAddOrgOpen(false)} maxWidth="xs" fullWidth>
        <DialogTitle>Add Organization</DialogTitle>
        <DialogContent>
          <TextField
            fullWidth autoFocus label="Organization Name" margin="dense"
            value={newOrgName} onChange={(e) => setNewOrgName(e.target.value)}
            helperText="Must match your Intersight organization name"
            onKeyDown={(e) => e.key === 'Enter' && handleAddOrg()}
          />
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setAddOrgOpen(false)}>Cancel</Button>
          <Button variant="contained" onClick={handleAddOrg} disabled={!newOrgName.trim()}>Create</Button>
        </DialogActions>
      </Dialog>

      {/* Delete confirmation dialog */}
      <Dialog open={!!deleteConfirm} onClose={() => setDeleteConfirm(null)}>
        <DialogTitle>Confirm Delete</DialogTitle>
        <DialogContent>
          <Typography>
            {deleteConfirm?.category
              ? `Delete "${deleteConfirm.name}" from ${deleteConfirm.org}/${deleteConfirm.category}/${deleteConfirm.type}?`
              : `Delete organization "${deleteConfirm?.org}" and all its resources?`
            }
          </Typography>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setDeleteConfirm(null)}>Cancel</Button>
          <Button variant="contained" color="error" onClick={confirmDelete}>Delete</Button>
        </DialogActions>
      </Dialog>

      {/* Full-state export confirmation */}
      <Dialog open={fullStateConfirmOpen} onClose={() => setFullStateConfirmOpen(false)}>
        <DialogTitle>Export Full State</DialogTitle>
        <DialogContent>
          <Typography>
            Download the entire workspace configuration as a single file. Choose a format:
          </Typography>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setFullStateConfirmOpen(false)}>Cancel</Button>
          <Button
            variant="outlined"
            onClick={() => { setFullStateConfirmOpen(false); api.downloadFullStateXml(); }}
          >
            Download XML
          </Button>
          <Button
            variant="contained"
            onClick={() => { setFullStateConfirmOpen(false); api.downloadFullState(); }}
          >
            Download YAML
          </Button>
        </DialogActions>
      </Dialog>

      {/* Unsync confirmation dialog */}
      <Dialog open={unsyncConfirmOpen} onClose={() => setUnsyncConfirmOpen(false)}>
        <DialogTitle>Remove Synced Data</DialogTitle>
        <DialogContent>
          <Typography>
            This will remove all Intersight synced domain data from your workspace.
            Local configurations will not be affected.
          </Typography>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setUnsyncConfirmOpen(false)}>Cancel</Button>
          <Button variant="contained" color="error" onClick={handleUnsyncAll}>
            Remove All Synced Data
          </Button>
        </DialogActions>
      </Dialog>

      {/* Org-level download format menu */}
      <Menu
        anchorEl={orgDownloadAnchor}
        open={Boolean(orgDownloadAnchor)}
        onClose={() => setOrgDownloadAnchor(null)}
        anchorOrigin={{ vertical: 'bottom', horizontal: 'right' }}
        transformOrigin={{ vertical: 'top', horizontal: 'right' }}
      >
        <MenuItem onClick={handleOrgDownloadYaml}>
          <ListItemIcon><DataObjectIcon fontSize="small" /></ListItemIcon>
          <ListItemText>Download as YAML</ListItemText>
        </MenuItem>
        <MenuItem onClick={handleOrgDownloadXml}>
          <ListItemIcon><CodeIcon fontSize="small" /></ListItemIcon>
          <ListItemText>Download as XML</ListItemText>
        </MenuItem>
      </Menu>

      {/* Import local workspace dialog */}
      <Dialog
        open={localImportOpen}
        onClose={() => { setLocalImportOpen(false); setLocalImportPreview(null); setLocalImportPath(''); }}
        maxWidth="sm" fullWidth
      >
        <DialogTitle>Import from Local Easy IMM Workspace</DialogTitle>
        <DialogContent>
          <Typography variant="body2" sx={{ mb: 2, color: 'text.secondary' }}>
            Enter the path to an existing Easy IMM workspace folder (containing .ezi.yaml files).
            All organizations and resources will be imported into the current workspace.
          </Typography>
          <TextField
            fullWidth autoFocus label="Workspace Path" margin="dense"
            placeholder="/path/to/easy-imm-workspace"
            value={localImportPath}
            onChange={(e) => { setLocalImportPath(e.target.value); setLocalImportPreview(null); }}
            onKeyDown={(e) => e.key === 'Enter' && handleLocalImportPreview()}
          />
          {localImportPreview && (
            <Box sx={{ mt: 2, p: 2, bgcolor: 'background.default', borderRadius: 1, maxHeight: 300, overflow: 'auto' }}>
              <Typography variant="subtitle2" sx={{ mb: 1 }}>
                Preview: {localImportPreview.total} resources across {Object.keys(localImportPreview.orgs).length} org(s)
              </Typography>
              {Object.entries(localImportPreview.orgs).map(([org, types]) => (
                <Box key={org} sx={{ mb: 1 }}>
                  <Typography variant="body2" sx={{ fontWeight: 600 }}>{org}</Typography>
                  {Object.entries(types).map(([type, count]) => (
                    <Typography key={type} variant="caption" sx={{ display: 'block', pl: 2, color: 'text.secondary' }}>
                      {type}: {count}
                    </Typography>
                  ))}
                </Box>
              ))}
            </Box>
          )}
        </DialogContent>
        <DialogActions>
          <Button onClick={() => { setLocalImportOpen(false); setLocalImportPreview(null); setLocalImportPath(''); }}>Cancel</Button>
          {!localImportPreview ? (
            <Button variant="outlined" onClick={handleLocalImportPreview} disabled={!localImportPath.trim()}>
              Preview
            </Button>
          ) : (
            <Button
              variant="contained" onClick={handleLocalImportApply} disabled={localImporting || localImportPreview.total === 0}
              startIcon={localImporting ? <CircularProgress size={16} /> : null}
            >
              {localImporting ? 'Importing...' : `Import ${localImportPreview.total} Resources`}
            </Button>
          )}
        </DialogActions>
      </Dialog>

      {/* Toast notifications */}
      <Snackbar open={!!toast} autoHideDuration={4000} onClose={() => setToast(null)} anchorOrigin={{ vertical: 'bottom', horizontal: 'center' }}>
        {toast && <Alert severity={toast.severity} onClose={() => setToast(null)}>{toast.text}</Alert>}
      </Snackbar>
    </ThemeProvider>
  );
}
