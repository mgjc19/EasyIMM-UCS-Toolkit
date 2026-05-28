import { useState, useEffect, useRef, useCallback } from 'react';
import Box from '@mui/material/Box';
import Typography from '@mui/material/Typography';
import TextField from '@mui/material/TextField';
import Button from '@mui/material/Button';
import ButtonGroup from '@mui/material/ButtonGroup';
import IconButton from '@mui/material/IconButton';
import Switch from '@mui/material/Switch';
import FormControlLabel from '@mui/material/FormControlLabel';
import MenuItem from '@mui/material/MenuItem';
import Chip from '@mui/material/Chip';
import Tooltip from '@mui/material/Tooltip';
import Divider from '@mui/material/Divider';
import Alert from '@mui/material/Alert';
import Snackbar from '@mui/material/Snackbar';
import CircularProgress from '@mui/material/CircularProgress';
import Dialog from '@mui/material/Dialog';
import DialogTitle from '@mui/material/DialogTitle';
import DialogContent from '@mui/material/DialogContent';
import DialogActions from '@mui/material/DialogActions';
import Paper from '@mui/material/Paper';
import SaveIcon from '@mui/icons-material/Save';
import AddIcon from '@mui/icons-material/Add';
import DeleteIcon from '@mui/icons-material/Delete';
import MemoryIcon from '@mui/icons-material/Memory';
import DnsIcon from '@mui/icons-material/Dns';
import PowerSettingsNewIcon from '@mui/icons-material/PowerSettingsNew';
import SettingsInputAntennaIcon from '@mui/icons-material/SettingsInputAntenna';
import StorageIcon from '@mui/icons-material/Storage';
import SecurityIcon from '@mui/icons-material/Security';
import NotificationsIcon from '@mui/icons-material/Notifications';
import HighlightIcon from '@mui/icons-material/Highlight';
import RestartAltIcon from '@mui/icons-material/RestartAlt';
import AlbumIcon from '@mui/icons-material/Album';
import ListAltIcon from '@mui/icons-material/ListAlt';
import NetworkCheckIcon from '@mui/icons-material/NetworkCheck';
import ClearIcon from '@mui/icons-material/Clear';
import ExpandLessIcon from '@mui/icons-material/ExpandLess';
import ExpandMoreIcon from '@mui/icons-material/ExpandMore';
import LinkIcon from '@mui/icons-material/Link';
import { api } from '../api';

const RESOURCE_ICONS = {
  bios: <MemoryIcon fontSize="small" />,
  bios_reset: <RestartAltIcon fontSize="small" />,
  boot_order: <ListAltIcon fontSize="small" />,
  power: <PowerSettingsNewIcon fontSize="small" />,
  identify_led: <HighlightIcon fontSize="small" />,
  bmc_settings: <DnsIcon fontSize="small" />,
  bmc_network_protocol: <NetworkCheckIcon fontSize="small" />,
  virtual_media: <AlbumIcon fontSize="small" />,
  secure_boot: <SecurityIcon fontSize="small" />,
  event_subscription: <NotificationsIcon fontSize="small" />,
  log_service: <StorageIcon fontSize="small" />,
};

const RESOURCE_ORDER = [
  'bios', 'bios_reset', 'boot_order', 'power', 'identify_led',
  'bmc_settings', 'bmc_network_protocol', 'virtual_media',
  'secure_boot', 'event_subscription', 'log_service',
];


function FieldInput({ field, value, onChange }) {
  const handleChange = (val) => onChange(field.name, val);

  if (field.type === 'boolean') {
    return (
      <FormControlLabel
        control={<Switch checked={!!value} onChange={(e) => handleChange(e.target.checked)} />}
        label={<Box>
          <Typography variant="body2">{field.label}</Typography>
          {field.description && <Typography variant="caption" color="text.secondary">{field.description}</Typography>}
        </Box>}
        sx={{ my: 0.5, ml: 0 }}
      />
    );
  }

  if (field.type === 'select') {
    return (
      <TextField
        select fullWidth label={field.label}
        value={value ?? field.default ?? ''}
        onChange={(e) => handleChange(e.target.value)}
        helperText={field.description} margin="dense"
      >
        {(field.options || []).map((opt) => (
          <MenuItem key={opt} value={opt}>{opt || '(none)'}</MenuItem>
        ))}
      </TextField>
    );
  }

  if (field.type === 'integer') {
    return (
      <TextField
        fullWidth type="number" label={field.label}
        value={value ?? field.default ?? ''}
        onChange={(e) => handleChange(parseInt(e.target.value) || 0)}
        helperText={field.description} margin="dense"
      />
    );
  }

  if (field.type === 'string_list') {
    const items = Array.isArray(value) ? value : (field.default || []);
    return (
      <Box sx={{ my: 1 }}>
        <Box sx={{ display: 'flex', alignItems: 'center', mb: 0.5 }}>
          <Typography variant="body2" sx={{ fontWeight: 600, flex: 1 }}>{field.label}</Typography>
          <IconButton size="small" onClick={() => handleChange([...items, ''])} color="secondary">
            <AddIcon fontSize="small" />
          </IconButton>
        </Box>
        {items.map((item, idx) => (
          <Box key={idx} sx={{ display: 'flex', gap: 1, mb: 0.5 }}>
            <TextField
              fullWidth size="small" value={item}
              onChange={(e) => {
                const updated = [...items];
                updated[idx] = e.target.value;
                handleChange(updated);
              }}
            />
            <IconButton size="small" onClick={() => handleChange(items.filter((_, i) => i !== idx))} color="error">
              <DeleteIcon sx={{ fontSize: 14 }} />
            </IconButton>
          </Box>
        ))}
        {field.description && <Typography variant="caption" color="text.secondary">{field.description}</Typography>}
      </Box>
    );
  }

  if (field.type === 'map') {
    const obj = (typeof value === 'object' && value && !Array.isArray(value)) ? value : {};
    const entries = Object.entries(obj);
    return (
      <Box sx={{ my: 1 }}>
        <Box sx={{ display: 'flex', alignItems: 'center', mb: 0.5 }}>
          <Typography variant="body2" sx={{ fontWeight: 600, flex: 1 }}>{field.label}</Typography>
          <IconButton size="small" onClick={() => handleChange({ ...obj, '': '' })} color="secondary">
            <AddIcon fontSize="small" />
          </IconButton>
        </Box>
        {field.description && <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mb: 0.5 }}>{field.description}</Typography>}
        {entries.map(([k, v], idx) => (
          <Box key={idx} sx={{ display: 'flex', gap: 1, mb: 0.5 }}>
            <TextField
              size="small" placeholder="Attribute" value={k} sx={{ flex: 1 }}
              onChange={(e) => {
                const newObj = {};
                entries.forEach(([ek, ev], i) => {
                  newObj[i === idx ? e.target.value : ek] = ev;
                });
                handleChange(newObj);
              }}
            />
            <TextField
              size="small" placeholder="Value" value={v} sx={{ flex: 1 }}
              onChange={(e) => {
                handleChange({ ...obj, [k]: e.target.value });
              }}
            />
            <IconButton size="small" color="error" onClick={() => {
              const newObj = { ...obj };
              delete newObj[k];
              handleChange(newObj);
            }}>
              <DeleteIcon sx={{ fontSize: 14 }} />
            </IconButton>
          </Box>
        ))}
        {entries.length === 0 && (
          <Typography variant="caption" color="text.secondary" sx={{ fontStyle: 'italic' }}>
            No attributes set. Click + to add.
          </Typography>
        )}
      </Box>
    );
  }

  if (field.type === 'boot_devices') {
    const items = Array.isArray(value) ? value : (field.default || []);
    return (
      <Box sx={{ my: 1 }}>
        <Box sx={{ display: 'flex', alignItems: 'center', mb: 0.5 }}>
          <Typography variant="body2" sx={{ fontWeight: 600, flex: 1 }}>{field.label}</Typography>
          <IconButton size="small" onClick={() => handleChange([...items, { alias: '', id: '' }])} color="secondary">
            <AddIcon fontSize="small" />
          </IconButton>
        </Box>
        {field.description && <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mb: 0.5 }}>{field.description}</Typography>}
        {items.map((item, idx) => (
          <Box key={idx} sx={{ display: 'flex', gap: 1, mb: 0.5, alignItems: 'center' }}>
            <Chip label={`#${idx + 1}`} size="small" variant="outlined" />
            <TextField
              size="small" placeholder="Alias (e.g. pxe-ocp1)" value={item.alias || ''} sx={{ flex: 1 }}
              onChange={(e) => {
                const updated = [...items];
                updated[idx] = { ...updated[idx], alias: e.target.value };
                handleChange(updated);
              }}
            />
            <TextField
              size="small" placeholder="Boot ID (e.g. Boot0004)" value={item.id || ''} sx={{ flex: 1 }}
              onChange={(e) => {
                const updated = [...items];
                updated[idx] = { ...updated[idx], id: e.target.value };
                handleChange(updated);
              }}
            />
            <IconButton size="small" color="error" onClick={() => handleChange(items.filter((_, i) => i !== idx))}>
              <DeleteIcon sx={{ fontSize: 14 }} />
            </IconButton>
          </Box>
        ))}
      </Box>
    );
  }

  return (
    <TextField
      fullWidth label={field.label}
      value={value ?? field.default ?? ''}
      onChange={(e) => handleChange(e.target.value)}
      helperText={field.description} margin="dense"
    />
  );
}


function ServerConnection({ server, onSave }) {
  const [form, setForm] = useState({ endpoint: '', username: 'admin', password: '', insecure: true });
  const [saving, setSaving] = useState(false);
  const [msg, setMsg] = useState(null);

  useEffect(() => {
    if (server) {
      setForm({
        endpoint: server.endpoint || '',
        username: server.username || 'admin',
        password: server.has_password ? '****' : '',
        insecure: server.insecure ?? true,
      });
    }
  }, [server]);

  const handleSave = async () => {
    setSaving(true);
    try {
      const payload = { ...form };
      if (payload.password === '****') delete payload.password;
      await api.saveRedfishServer(payload);
      setMsg({ type: 'success', text: 'Server connection saved' });
      if (onSave) onSave();
    } catch (e) {
      setMsg({ type: 'error', text: e.message });
    }
    setSaving(false);
  };

  return (
    <Box sx={{ p: 2 }}>
      <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 1.5 }}>
        <LinkIcon sx={{ color: 'primary.main' }} />
        <Typography variant="subtitle2" sx={{ fontWeight: 700 }}>BMC Connection</Typography>
      </Box>
      <TextField
        fullWidth label="BMC Endpoint" margin="dense" placeholder="https://10.0.0.1"
        value={form.endpoint} onChange={(e) => setForm({ ...form, endpoint: e.target.value })}
        helperText="Redfish endpoint URL (e.g. https://bmc-ip-address)"
      />
      <TextField
        fullWidth label="Username" margin="dense"
        value={form.username} onChange={(e) => setForm({ ...form, username: e.target.value })}
      />
      <TextField
        fullWidth label="Password" margin="dense" type="password"
        value={form.password}
        onChange={(e) => setForm({ ...form, password: e.target.value })}
        onFocus={() => { if (form.password === '****') setForm({ ...form, password: '' }); }}
      />
      <FormControlLabel
        control={<Switch checked={form.insecure} onChange={(e) => setForm({ ...form, insecure: e.target.checked })} />}
        label="Skip TLS verification" sx={{ mt: 0.5 }}
      />
      {msg && <Alert severity={msg.type} sx={{ mt: 1 }} onClose={() => setMsg(null)}>{msg.text}</Alert>}
      <Button
        fullWidth variant="contained" sx={{ mt: 1.5 }}
        onClick={handleSave} disabled={saving || !form.endpoint}
        startIcon={saving ? <CircularProgress size={16} /> : <SaveIcon />}
      >
        {saving ? 'Saving...' : 'Save Connection'}
      </Button>
    </Box>
  );
}


function ResourceForm({ resourceKey, schema, onSaveToast }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    setLoading(true);
    api.getRedfishConfig(resourceKey).then((cfg) => {
      setData(cfg);
      setLoading(false);
    }).catch(() => setLoading(false));
  }, [resourceKey]);

  const handleFieldChange = (name, value) => {
    setData((prev) => ({ ...prev, [name]: value }));
  };

  const handleSave = async () => {
    setSaving(true);
    try {
      await api.saveRedfishConfig(resourceKey, data);
      onSaveToast({ severity: 'success', text: `Saved ${schema.label} configuration` });
    } catch (e) {
      onSaveToast({ severity: 'error', text: e.message });
    }
    setSaving(false);
  };

  if (loading || !data) {
    return (
      <Box sx={{ p: 4, textAlign: 'center' }}>
        <CircularProgress size={24} />
      </Box>
    );
  }

  const enabled = !!data._enabled;

  return (
    <Box sx={{ display: 'flex', flexDirection: 'column', height: '100%' }}>
      <Box sx={{
        display: 'flex', alignItems: 'center', gap: 1,
        px: 2.5, py: 1.5,
        borderBottom: '1px solid', borderColor: 'divider',
        bgcolor: 'background.paper',
      }}>
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, color: 'primary.main' }}>
          {RESOURCE_ICONS[resourceKey]}
        </Box>
        <Box sx={{ flex: 1 }}>
          <Typography variant="subtitle1" sx={{ fontWeight: 700 }}>{schema.label}</Typography>
          <Typography variant="caption" color="text.secondary">{schema.description}</Typography>
        </Box>
        <FormControlLabel
          control={
            <Switch
              checked={enabled}
              onChange={(e) => handleFieldChange('_enabled', e.target.checked)}
              color="secondary"
            />
          }
          label={<Chip label={enabled ? 'Enabled' : 'Disabled'} size="small" color={enabled ? 'secondary' : 'default'} variant={enabled ? 'filled' : 'outlined'} />}
        />
        <Button
          variant="contained" size="small"
          startIcon={<SaveIcon />}
          onClick={handleSave}
          disabled={saving}
        >
          Save
        </Button>
      </Box>

      <Box sx={{ flex: 1, overflow: 'auto', px: 2.5, py: 2, opacity: enabled ? 1 : 0.5 }}>
        {!enabled && (
          <Alert severity="info" sx={{ mb: 2 }}>
            This resource is disabled and will not be included in the Terraform plan.
            Toggle the switch above to enable it.
          </Alert>
        )}
        <Typography variant="overline" color="text.secondary" sx={{ display: 'block', mb: 0.5 }}>
          Terraform resource: <code style={{ color: '#00bceb' }}>{schema.resource_type}</code>
        </Typography>
        <Divider sx={{ mb: 1.5 }} />
        {schema.fields.map((field) => (
          <FieldInput
            key={field.name}
            field={field}
            value={data[field.name]}
            onChange={handleFieldChange}
          />
        ))}
      </Box>
    </Box>
  );
}


function colorize(line) {
  if (line.includes('Error') || line.includes('error')) return 'error.main';
  if (/^\s*\+/.test(line) || (line.includes('Plan:') && line.includes('to add'))) return 'success.main';
  if (/^\s*-/.test(line) || line.includes('to destroy')) return 'error.main';
  if (/^\s*~/.test(line) || line.includes('to change')) return 'warning.main';
  return 'text.primary';
}

function RedfishTerraformPanel() {
  const [output, setOutput] = useState([]);
  const [running, setRunning] = useState(false);
  const [currentAction, setCurrentAction] = useState(null);
  const [lastStatus, setLastStatus] = useState(null);
  const [expanded, setExpanded] = useState(true);
  const [confirmDestroy, setConfirmDestroy] = useState(false);
  const [generating, setGenerating] = useState(false);
  const logRef = useRef(null);
  const wsRef = useRef(null);

  useEffect(() => {
    if (logRef.current) logRef.current.scrollTop = logRef.current.scrollHeight;
  }, [output]);

  const handleGenerate = async () => {
    setGenerating(true);
    setOutput([]);
    setLastStatus(null);
    setExpanded(true);
    try {
      const result = await api.generateRedfishTf();
      const files = result.files_written || [];
      const enabled = result.enabled_resources || [];
      setOutput([
        `Generated Terraform files for ${enabled.length} resource(s):\n`,
        ...enabled.map((r) => `  + ${r}\n`),
        `\nFiles written:\n`,
        ...files.map((f) => `  ${f}\n`),
        `\nRun Init > Plan > Apply to deploy.\n`,
      ]);
      setLastStatus('success');
    } catch (e) {
      setOutput([`Error generating TF files: ${e.message}\n`]);
      setLastStatus('error');
    }
    setGenerating(false);
  };

  const runAction = (action) => {
    setOutput([]);
    setRunning(true);
    setCurrentAction(action);
    setLastStatus(null);
    setExpanded(true);

    const proto = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const ws = new WebSocket(`${proto}//${window.location.host}/ws/redfish/terraform`);
    wsRef.current = ws;

    ws.onopen = () => ws.send(JSON.stringify({ action }));
    ws.onmessage = (event) => {
      const msg = JSON.parse(event.data);
      if (msg.type === 'output') {
        setOutput((prev) => [...prev, msg.data]);
      } else if (msg.type === 'done') {
        setRunning(false);
        setLastStatus(msg.success ? 'success' : 'error');
        ws.close();
      } else if (msg.type === 'error') {
        setOutput((prev) => [...prev, `Error: ${msg.data}\n`]);
        setRunning(false);
        setLastStatus('error');
      }
    };
    ws.onerror = () => {
      setOutput((prev) => [...prev, 'WebSocket connection failed.\n']);
      setRunning(false);
      setLastStatus('error');
    };
    ws.onclose = () => setRunning(false);
  };

  const busy = running || generating;

  return (
    <Box sx={{ borderTop: '1px solid', borderColor: 'divider', bgcolor: 'background.paper' }}>
      <Box sx={{ display: 'flex', alignItems: 'center', px: 2, py: 0.5, gap: 1, flexWrap: 'wrap' }}>
        <Typography variant="subtitle2" sx={{ fontWeight: 700, mr: 1 }}>Redfish Terraform</Typography>
        <Button size="small" variant="outlined" color="secondary" onClick={handleGenerate} disabled={busy} sx={{ mr: 0.5 }}>
          {generating ? 'Generating...' : 'Generate TF'}
        </Button>
        <ButtonGroup size="small" disabled={busy}>
          <Button onClick={() => runAction('init')}>Init</Button>
          <Button onClick={() => runAction('validate')}>Validate</Button>
          <Button onClick={() => runAction('plan')} color="primary">Plan</Button>
          <Button onClick={() => runAction('apply')} color="success">Apply</Button>
          <Button onClick={() => setConfirmDestroy(true)} color="error">Destroy</Button>
        </ButtonGroup>
        <Button size="small" onClick={() => runAction('state_list')} disabled={busy}>Status</Button>
        <Box sx={{ flex: 1 }} />
        {running && <Chip label={`Running: ${currentAction}`} size="small" color="warning" />}
        {generating && <Chip label="Generating..." size="small" color="info" />}
        {lastStatus === 'success' && <Chip label="Success" size="small" color="success" />}
        {lastStatus === 'error' && <Chip label="Failed" size="small" color="error" />}
        <Tooltip title="Clear">
          <IconButton size="small" onClick={() => { setOutput([]); setLastStatus(null); }}>
            <ClearIcon fontSize="small" />
          </IconButton>
        </Tooltip>
        <IconButton size="small" onClick={() => setExpanded(!expanded)}>
          {expanded ? <ExpandMoreIcon fontSize="small" /> : <ExpandLessIcon fontSize="small" />}
        </IconButton>
      </Box>
      {expanded && (
        <Box ref={logRef} sx={{
          height: 220, overflow: 'auto', px: 2, py: 1,
          fontFamily: '"JetBrains Mono", "Fira Code", monospace',
          fontSize: 12, lineHeight: 1.6, bgcolor: '#0d1117',
        }}>
          {output.length === 0 && (
            <Typography variant="body2" color="text.secondary" sx={{ fontStyle: 'italic' }}>
              Configure resources above, then click Generate TF &gt; Init &gt; Plan to preview changes...
            </Typography>
          )}
          {output.map((line, i) => (
            <Box key={i} component="span" sx={{ color: colorize(line), display: 'block', whiteSpace: 'pre-wrap' }}>{line}</Box>
          ))}
        </Box>
      )}
      <Dialog open={confirmDestroy} onClose={() => setConfirmDestroy(false)}>
        <DialogTitle>Confirm Destroy</DialogTitle>
        <DialogContent>
          <Typography>
            This will destroy ALL Redfish-managed resources on this server. Are you sure?
          </Typography>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setConfirmDestroy(false)}>Cancel</Button>
          <Button variant="contained" color="error" onClick={() => { setConfirmDestroy(false); runAction('destroy'); }}>Destroy</Button>
        </DialogActions>
      </Dialog>
    </Box>
  );
}


export default function RedfishPanel() {
  const [schemas, setSchemas] = useState(null);
  const [server, setServer] = useState(null);
  const [configs, setConfigs] = useState(null);
  const [selectedResource, setSelectedResource] = useState(null);
  const [toast, setToast] = useState(null);
  const [loading, setLoading] = useState(true);

  const loadData = useCallback(async () => {
    setLoading(true);
    try {
      const [schemaData, serverData, configData] = await Promise.all([
        api.getRedfishSchemas(),
        api.getRedfishServer(),
        api.getRedfishConfigs(),
      ]);
      setSchemas(schemaData);
      setServer(serverData);
      setConfigs(configData);
    } catch (e) {
      setToast({ severity: 'error', text: 'Failed to load Redfish config: ' + e.message });
    }
    setLoading(false);
  }, []);

  useEffect(() => { loadData(); }, [loadData]);

  if (loading) {
    return (
      <Box sx={{ height: '100%', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
        <CircularProgress />
      </Box>
    );
  }

  const enabledSet = new Set(
    configs ? Object.entries(configs).filter(([, v]) => v._enabled).map(([k]) => k) : []
  );

  return (
    <Box sx={{ display: 'flex', flexDirection: 'column', height: '100%' }}>
      <Box sx={{ flex: 1, display: 'flex', overflow: 'hidden' }}>
        {/* Left sidebar: server + resource list */}
        <Box sx={{
          width: 300, minWidth: 260,
          borderRight: '1px solid', borderColor: 'divider',
          overflow: 'auto', bgcolor: 'background.paper',
          display: 'flex', flexDirection: 'column',
        }}>
          <ServerConnection server={server} onSave={loadData} />
          <Divider />

          <Box sx={{ px: 2, pt: 1.5, pb: 0.5 }}>
            <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
              <SettingsInputAntennaIcon sx={{ color: 'secondary.main', fontSize: 18 }} />
              <Typography variant="subtitle2" sx={{ fontWeight: 700, textTransform: 'uppercase', letterSpacing: 1 }}>
                Resources
              </Typography>
              <Box sx={{ flex: 1 }} />
              <Chip
                label={`${enabledSet.size} active`}
                size="small"
                color={enabledSet.size > 0 ? 'secondary' : 'default'}
                variant="outlined"
              />
            </Box>
          </Box>

          <Box sx={{ flex: 1, overflow: 'auto', pb: 1 }}>
            {RESOURCE_ORDER.map((key) => {
              if (!schemas || !schemas[key]) return null;
              const s = schemas[key];
              const isSelected = selectedResource === key;
              const isEnabled = enabledSet.has(key);

              return (
                <Box
                  key={key}
                  onClick={() => setSelectedResource(key)}
                  sx={{
                    display: 'flex', alignItems: 'center', gap: 1,
                    px: 2, py: 0.8, mx: 1, my: 0.3,
                    cursor: 'pointer',
                    borderRadius: 1,
                    bgcolor: isSelected ? 'rgba(0,188,235,0.08)' : 'transparent',
                    border: isSelected ? '1px solid' : '1px solid transparent',
                    borderColor: isSelected ? 'primary.main' : 'transparent',
                    '&:hover': { bgcolor: isSelected ? 'rgba(0,188,235,0.12)' : 'action.hover' },
                    transition: 'all 0.15s',
                  }}
                >
                  <Box sx={{ color: isEnabled ? 'secondary.main' : 'text.disabled', display: 'flex' }}>
                    {RESOURCE_ICONS[key] || <MemoryIcon fontSize="small" />}
                  </Box>
                  <Typography
                    variant="body2"
                    sx={{
                      flex: 1,
                      fontWeight: isSelected ? 600 : 400,
                      color: isEnabled ? 'text.primary' : 'text.secondary',
                    }}
                  >
                    {s.label}
                  </Typography>
                  {isEnabled && (
                    <Box sx={{ width: 6, height: 6, borderRadius: '50%', bgcolor: 'secondary.main' }} />
                  )}
                </Box>
              );
            })}
          </Box>
        </Box>

        {/* Right pane: resource form or welcome */}
        <Box sx={{ flex: 1, overflow: 'hidden' }}>
          {selectedResource && schemas?.[selectedResource] ? (
            <ResourceForm
              key={selectedResource}
              resourceKey={selectedResource}
              schema={schemas[selectedResource]}
              onSaveToast={setToast}
            />
          ) : (
            <Box sx={{ height: '100%', display: 'flex', alignItems: 'center', justifyContent: 'center', color: 'text.secondary' }}>
              <Box sx={{ textAlign: 'center', maxWidth: 420, px: 3 }}>
                <SettingsInputAntennaIcon sx={{ fontSize: 48, color: 'primary.main', mb: 2, opacity: 0.5 }} />
                <Typography variant="h6" gutterBottom>Redfish Server Configuration</Typography>
                <Typography variant="body2">
                  Configure your BMC connection on the left, then select a resource type to configure.
                  Enable the resources you want to manage, set their values, and use Terraform below to plan and apply.
                </Typography>
                <Paper sx={{ p: 2, mt: 3, bgcolor: 'rgba(0,188,235,0.04)', border: '1px solid', borderColor: 'rgba(0,188,235,0.15)' }}>
                  <Typography variant="caption" color="text.secondary">
                    Supported: BIOS, Boot Order, Power, BMC Settings, BMC Network, Virtual Media,
                    Secure Boot, LED, Event Subscriptions, Log Service
                  </Typography>
                </Paper>
              </Box>
            </Box>
          )}
        </Box>
      </Box>

      {/* Terraform panel */}
      <RedfishTerraformPanel />

      {/* Toast */}
      <Snackbar open={!!toast} autoHideDuration={4000} onClose={() => setToast(null)} anchorOrigin={{ vertical: 'bottom', horizontal: 'center' }}>
        {toast && <Alert severity={toast.severity} onClose={() => setToast(null)}>{toast.text}</Alert>}
      </Snackbar>
    </Box>
  );
}
