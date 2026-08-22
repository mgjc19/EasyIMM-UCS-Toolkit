import { useState, useEffect } from 'react';
import Dialog from '@mui/material/Dialog';
import DialogTitle from '@mui/material/DialogTitle';
import DialogContent from '@mui/material/DialogContent';
import DialogActions from '@mui/material/DialogActions';
import Button from '@mui/material/Button';
import TextField from '@mui/material/TextField';
import Typography from '@mui/material/Typography';
import Alert from '@mui/material/Alert';
import Box from '@mui/material/Box';
import Divider from '@mui/material/Divider';
import CircularProgress from '@mui/material/CircularProgress';
import CheckCircleIcon from '@mui/icons-material/CheckCircle';
import ErrorIcon from '@mui/icons-material/Error';
import DeleteForeverIcon from '@mui/icons-material/DeleteForever';
import { api } from '../api';

const API_KEY_REGEX = /^[\da-f]{24}\/[\da-f]{24}\/[\da-f]{24}$/;

export default function SettingsDialog({ open, onClose }) {
  const [settings, setSettings] = useState({ api_key_id: '', secret_key: '', intersight_fqdn: 'intersight.com' });
  const [saving, setSaving] = useState(false);
  const [testing, setTesting] = useState(false);
  const [clearing, setClearing] = useState(false);
  const [message, setMessage] = useState(null);
  const [keyError, setKeyError] = useState('');

  useEffect(() => {
    if (open) {
      api.getSettings().then(setSettings).catch(() => {});
      setMessage(null);
      setKeyError('');
    }
  }, [open]);

  const validateApiKey = (value) => {
    if (value && !API_KEY_REGEX.test(value)) {
      setKeyError('Format: 24-hex-chars/24-hex-chars/24-hex-chars');
    } else {
      setKeyError('');
    }
  };

  const handleSave = async () => {
    setSaving(true);
    try {
      await api.saveSettings(settings);
      setMessage({ type: 'success', text: 'Settings saved to env.sh' });
    } catch (e) {
      setMessage({ type: 'error', text: e.message });
    }
    setSaving(false);
  };

  const handleTest = async () => {
    setTesting(true);
    setMessage(null);
    try {
      await api.saveSettings(settings);
      const result = await api.testConnection();
      setMessage({
        type: result.ok ? 'success' : 'error',
        text: result.message,
      });
    } catch (e) {
      setMessage({ type: 'error', text: e.message });
    }
    setTesting(false);
  };

  const handleClear = async () => {
    setClearing(true);
    try {
      await api.clearSettings();
      setSettings({ api_key_id: '', secret_key: '', intersight_fqdn: 'intersight.com' });
      setMessage({ type: 'success', text: 'Connection credentials cleared' });
    } catch (e) {
      setMessage({ type: 'error', text: e.message });
    }
    setClearing(false);
  };

  return (
    <Dialog open={open} onClose={onClose} maxWidth="sm" fullWidth>
      <DialogTitle>Intersight Settings</DialogTitle>
      <DialogContent dividers>
        <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
          Configure your Cisco Intersight API credentials. These are saved to env.sh in the EasyIMM root directory.
        </Typography>
        <TextField
          fullWidth label="API Key ID" margin="dense"
          value={settings.api_key_id}
          onChange={(e) => {
            setSettings({ ...settings, api_key_id: e.target.value });
            validateApiKey(e.target.value);
          }}
          error={!!keyError}
          helperText={keyError || 'Format: aabbccdd112233/aabbccdd112233/aabbccdd112233'}
          placeholder="your-api-key-id"
        />
        <TextField
          fullWidth label="Secret Key (PEM file path)" margin="dense"
          value={settings.secret_key}
          onChange={(e) => setSettings({ ...settings, secret_key: e.target.value })}
          helperText="Absolute path to your Intersight secret key PEM file"
          placeholder="/path/to/SecretKey.txt"
        />
        <TextField
          fullWidth label="Intersight FQDN" margin="dense"
          value={settings.intersight_fqdn}
          onChange={(e) => setSettings({ ...settings, intersight_fqdn: e.target.value })}
          helperText="Use intersight.com for SaaS, or your CVA/PVA hostname"
        />

        <Divider sx={{ my: 2 }} />
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
          <Button
            color="error"
            variant="outlined"
            size="small"
            startIcon={clearing ? <CircularProgress size={14} /> : <DeleteForeverIcon />}
            onClick={handleClear}
            disabled={clearing}
          >
            Clear Connection
          </Button>
          <Typography variant="caption" color="text.secondary">
            Remove saved credentials from env.sh
          </Typography>
        </Box>

        {message && (
          <Alert
            severity={message.type}
            sx={{ mt: 2 }}
            icon={message.type === 'success' ? <CheckCircleIcon /> : <ErrorIcon />}
          >
            {message.text}
          </Alert>
        )}
      </DialogContent>
      <DialogActions>
        <Button
          onClick={handleTest}
          disabled={testing || !settings.api_key_id || !settings.secret_key}
          startIcon={testing ? <CircularProgress size={16} /> : null}
        >
          {testing ? 'Testing...' : 'Test Connection'}
        </Button>
        <Box sx={{ flex: 1 }} />
        <Button onClick={onClose}>Close</Button>
        <Button variant="contained" onClick={handleSave} disabled={saving}>
          {saving ? 'Saving...' : 'Save'}
        </Button>
      </DialogActions>
    </Dialog>
  );
}
