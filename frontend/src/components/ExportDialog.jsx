import { useState, useEffect } from 'react';
import Dialog from '@mui/material/Dialog';
import DialogTitle from '@mui/material/DialogTitle';
import DialogContent from '@mui/material/DialogContent';
import DialogActions from '@mui/material/DialogActions';
import Button from '@mui/material/Button';
import Box from '@mui/material/Box';
import Typography from '@mui/material/Typography';
import CircularProgress from '@mui/material/CircularProgress';
import Tabs from '@mui/material/Tabs';
import Tab from '@mui/material/Tab';
import Chip from '@mui/material/Chip';
import DownloadIcon from '@mui/icons-material/Download';
import PreviewIcon from '@mui/icons-material/Preview';
import DescriptionIcon from '@mui/icons-material/Description';
import { api } from '../api';

function YamlPreview({ content }) {
  if (!content) return null;

  const yamlStr = typeof content === 'string' ? content : JSON.stringify(content, null, 2);

  return (
    <Box
      component="pre"
      sx={{
        bgcolor: '#0d1117',
        color: '#c9d1d9',
        p: 2,
        borderRadius: 1,
        fontSize: 11,
        fontFamily: '"JetBrains Mono", "Fira Code", monospace',
        overflow: 'auto',
        maxHeight: 400,
        whiteSpace: 'pre-wrap',
        border: '1px solid',
        borderColor: 'divider',
        m: 0,
      }}
    >
      {yamlStr}
    </Box>
  );
}

export default function ExportDialog({ open, onClose }) {
  const [tab, setTab] = useState(0);
  const [sharedPreview, setSharedPreview] = useState(null);
  const [ucsPreview, setUcsPreview] = useState(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (open) {
      setSharedPreview(null);
      setUcsPreview(null);
    }
  }, [open]);

  const handlePreview = async (which) => {
    setLoading(true);
    try {
      if (which === 'shared' || which === 'both') {
        const data = await api.previewTechShared();
        setSharedPreview(data);
      }
      if (which === 'ucs' || which === 'both') {
        const data = await api.previewTechUcs();
        setUcsPreview(data);
      }
    } catch (e) {
      console.error('Preview failed:', e);
    }
    setLoading(false);
  };

  const countKeys = (obj) => {
    if (!obj) return 0;
    let count = 0;
    const walk = (o) => {
      if (Array.isArray(o)) {
        count += o.length;
        o.forEach(walk);
      } else if (typeof o === 'object' && o) {
        Object.values(o).forEach(walk);
      }
    };
    walk(obj);
    return count;
  };

  return (
    <Dialog open={open} onClose={onClose} maxWidth="md" fullWidth>
      <DialogTitle sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
        <DescriptionIcon color="primary" />
        Export to CiscoIQ Document-as-Code
      </DialogTitle>
      <DialogContent dividers>
        <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
          Export your configuration as CiscoIQ-compatible YAML files. These can be imported
          into the CiscoIQ platform for documentation generation. Both Easy IMM and Redfish
          configurations are included.
        </Typography>

        <Tabs value={tab} onChange={(_, v) => setTab(v)} sx={{ mb: 2 }}>
          <Tab label="data.tech-shared.yaml" sx={{ textTransform: 'none' }} />
          <Tab label="data.tech-ucs.yaml" sx={{ textTransform: 'none' }} />
        </Tabs>

        {tab === 0 && (
          <Box>
            <Box sx={{ display: 'flex', gap: 1, mb: 2 }}>
              <Button
                variant="outlined" size="small"
                startIcon={loading ? <CircularProgress size={14} /> : <PreviewIcon />}
                onClick={() => handlePreview('shared')}
                disabled={loading}
              >
                Preview
              </Button>
              <Button
                variant="contained" size="small"
                startIcon={<DownloadIcon />}
                onClick={() => api.downloadTechShared()}
              >
                Download tech-shared.yaml
              </Button>
              {sharedPreview && (
                <Chip label={`${countKeys(sharedPreview)} elements`} size="small" variant="outlined" />
              )}
            </Box>
            <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mb: 1 }}>
              Contains: Hardware inventory (FIs, chassis, servers, Redfish BMCs), cabling layout, naming conventions
            </Typography>
            {sharedPreview && <YamlPreview content={sharedPreview} />}
          </Box>
        )}

        {tab === 1 && (
          <Box>
            <Box sx={{ display: 'flex', gap: 1, mb: 2 }}>
              <Button
                variant="outlined" size="small"
                startIcon={loading ? <CircularProgress size={14} /> : <PreviewIcon />}
                onClick={() => handlePreview('ucs')}
                disabled={loading}
              >
                Preview
              </Button>
              <Button
                variant="contained" size="small"
                startIcon={<DownloadIcon />}
                onClick={() => api.downloadTechUcs()}
              >
                Download tech-ucs.yaml
              </Button>
              {ucsPreview && (
                <Chip label={`${countKeys(ucsPreview)} elements`} size="small" variant="outlined" />
              )}
            </Box>
            <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mb: 1 }}>
              Contains: Pools, policies, profiles, templates, network/SAN config, administration, Intersight settings
            </Typography>
            {ucsPreview && <YamlPreview content={ucsPreview} />}
          </Box>
        )}
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose}>Close</Button>
        <Button
          variant="contained" color="secondary"
          startIcon={<DownloadIcon />}
          onClick={() => { api.downloadTechShared(); api.downloadTechUcs(); }}
        >
          Download Both
        </Button>
      </DialogActions>
    </Dialog>
  );
}
