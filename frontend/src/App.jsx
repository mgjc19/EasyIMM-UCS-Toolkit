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
import SyncIcon from '@mui/icons-material/Sync';
import SyncDisabledIcon from '@mui/icons-material/SyncDisabled';
import CircularProgress from '@mui/material/CircularProgress';
import Chip from '@mui/material/Chip';
import Menu from '@mui/material/Menu';
import MenuItem from '@mui/material/MenuItem';
import ListItemIcon from '@mui/material/ListItemIcon';
import ListItemText from '@mui/material/ListItemText';
import FolderIcon from '@mui/icons-material/Folder';
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

export default function App() {
  const [mainTab, setMainTab] = useState(0);
  const [tree, setTree] = useState(null);
  const [types, setTypes] = useState(null);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [importOpen, setImportOpen] = useState(false);
  const [exportOpen, setExportOpen] = useState(false);
  const [toast, setToast] = useState(null);

  const [panelSchema, setPanelSchema] = useState(null);
  const [panelOrg, setPanelOrg] = useState('');
  const [panelCategory, setPanelCategory] = useState('');
  const [panelType, setPanelType] = useState('');
  const [panelData, setPanelData] = useState(null);

  const [addOrgOpen, setAddOrgOpen] = useState(false);
  const [newOrgName, setNewOrgName] = useState('');

  const [cloneOpen, setCloneOpen] = useState(false);
  const [cloneInfo, setCloneInfo] = useState({});

  const [deleteConfirm, setDeleteConfirm] = useState(null);

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

  const [unsyncAnchor, setUnsyncAnchor] = useState(null);
  const [syncedDomains, setSyncedDomains] = useState([]);

  const handleUnsyncOpen = async (event) => {
    try {
      const domains = await api.listSyncedDomains();
      setSyncedDomains(domains);
      setUnsyncAnchor(event.currentTarget);
    } catch (e) {
      setToast({ severity: 'error', text: e.message });
    }
  };

  const handleUnsync = async (domainName) => {
    setUnsyncAnchor(null);
    try {
      await api.unsyncDomain(domainName);
      setToast({ severity: 'success', text: `Unsynced domain: ${domainName}` });
      loadTree();
    } catch (e) {
      setToast({ severity: 'error', text: e.message });
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
    } catch {
      setToast({ severity: 'warning', text: `Schema not available for ${type}` });
    }
  };

  const closePanel = () => {
    setPanelSchema(null);
    setPanelData(null);
  };

  const handleSelect = (org, category, type, data) => openResource(org, category, type, data);
  const handleAdd = (org, category, type) => openResource(org, category, type, null);

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

  const orgs = tree ? Object.keys(tree) : [];
  const showPanel = !!panelSchema;

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
                <Tooltip title="Unsync — remove synced domain data">
                  <IconButton onClick={handleUnsyncOpen} color="inherit">
                    <SyncDisabledIcon />
                  </IconButton>
                </Tooltip>
                <Menu
                  anchorEl={unsyncAnchor}
                  open={Boolean(unsyncAnchor)}
                  onClose={() => setUnsyncAnchor(null)}
                >
                  {syncedDomains.length === 0 ? (
                    <MenuItem disabled>
                      <ListItemText primary="No synced domains" />
                    </MenuItem>
                  ) : syncedDomains.map((d) => (
                    <MenuItem key={d.name} onClick={() => handleUnsync(d.name)}>
                      <ListItemIcon><FolderIcon fontSize="small" /></ListItemIcon>
                      <ListItemText
                        primary={d.name}
                        secondary={`${d.resource_files} file${d.resource_files !== 1 ? 's' : ''}`}
                      />
                      <SyncDisabledIcon fontSize="small" sx={{ ml: 2, color: 'error.main' }} />
                    </MenuItem>
                  ))}
                </Menu>
                <Tooltip title="Import from Intersight (browse)">
                  <IconButton onClick={() => setImportOpen(true)} color="inherit">
                    <CloudDownloadIcon />
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

      {/* Toast notifications */}
      <Snackbar open={!!toast} autoHideDuration={4000} onClose={() => setToast(null)} anchorOrigin={{ vertical: 'bottom', horizontal: 'center' }}>
        {toast && <Alert severity={toast.severity} onClose={() => setToast(null)}>{toast.text}</Alert>}
      </Snackbar>
    </ThemeProvider>
  );
}
