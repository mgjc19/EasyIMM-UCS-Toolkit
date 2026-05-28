import { useState, useEffect } from 'react';
import Dialog from '@mui/material/Dialog';
import DialogTitle from '@mui/material/DialogTitle';
import DialogContent from '@mui/material/DialogContent';
import DialogActions from '@mui/material/DialogActions';
import Button from '@mui/material/Button';
import Box from '@mui/material/Box';
import Typography from '@mui/material/Typography';
import CircularProgress from '@mui/material/CircularProgress';
import Alert from '@mui/material/Alert';
import Chip from '@mui/material/Chip';
import FormControl from '@mui/material/FormControl';
import InputLabel from '@mui/material/InputLabel';
import Select from '@mui/material/Select';
import MenuItem from '@mui/material/MenuItem';
import Accordion from '@mui/material/Accordion';
import AccordionSummary from '@mui/material/AccordionSummary';
import AccordionDetails from '@mui/material/AccordionDetails';
import ExpandMoreIcon from '@mui/icons-material/ExpandMore';
import CloudDownloadIcon from '@mui/icons-material/CloudDownload';
import CheckCircleIcon from '@mui/icons-material/CheckCircle';
import StorageIcon from '@mui/icons-material/Storage';
import PolicyIcon from '@mui/icons-material/Security';
import DnsIcon from '@mui/icons-material/Dns';
import DescriptionIcon from '@mui/icons-material/Description';
import { api } from '../api';

const CATEGORY_ICONS = {
  pools: <StorageIcon fontSize="small" sx={{ color: 'primary.main' }} />,
  policies: <PolicyIcon fontSize="small" sx={{ color: 'warning.main' }} />,
  profiles: <DnsIcon fontSize="small" sx={{ color: 'secondary.main' }} />,
  templates: <DescriptionIcon fontSize="small" sx={{ color: 'info.main' }} />,
};

export default function ImportDialog({ open, onClose }) {
  const [step, setStep] = useState('idle');
  const [orgs, setOrgs] = useState([]);
  const [selectedOrg, setSelectedOrg] = useState('');
  const [resources, setResources] = useState(null);
  const [total, setTotal] = useState(0);
  const [error, setError] = useState(null);
  const [connectionOk, setConnectionOk] = useState(false);

  useEffect(() => {
    if (open) {
      setStep('idle');
      setResources(null);
      setError(null);
      setConnectionOk(false);
      setSelectedOrg('');
    }
  }, [open]);

  const handleConnect = async () => {
    setStep('connecting');
    setError(null);
    try {
      const result = await api.importTestConnection();
      if (result.ok) {
        setConnectionOk(true);
        const orgList = await api.importListOrgs();
        setOrgs(orgList);
        setStep('connected');
      } else {
        setError(result.error || 'Connection failed');
        setStep('idle');
      }
    } catch (e) {
      setError(e.message);
      setStep('idle');
    }
  };

  const handleFetch = async () => {
    setStep('fetching');
    setError(null);
    try {
      const result = await api.importListResources(selectedOrg || null);
      setResources(result.resources);
      setTotal(result.total);
      setStep('done');
    } catch (e) {
      setError(e.message);
      setStep('connected');
    }
  };

  return (
    <Dialog open={open} onClose={onClose} maxWidth="md" fullWidth>
      <DialogTitle sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
        <CloudDownloadIcon color="primary" />
        Import from Intersight
      </DialogTitle>
      <DialogContent dividers>
        <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
          Browse existing resources on your Intersight domain. This reads from the live API using
          your configured credentials (Settings).
        </Typography>

        {error && <Alert severity="error" sx={{ mb: 2 }}>{error}</Alert>}

        {!connectionOk && (
          <Box sx={{ textAlign: 'center', py: 3 }}>
            <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
              Connect to your Intersight domain to browse existing configurations.
            </Typography>
            <Button
              variant="contained"
              startIcon={step === 'connecting' ? <CircularProgress size={16} /> : <CloudDownloadIcon />}
              onClick={handleConnect}
              disabled={step === 'connecting'}
            >
              {step === 'connecting' ? 'Connecting...' : 'Connect to Intersight'}
            </Button>
          </Box>
        )}

        {connectionOk && step === 'connected' && (
          <Box>
            <Alert severity="success" icon={<CheckCircleIcon />} sx={{ mb: 2 }}>
              Connected to Intersight ({orgs.length} organization{orgs.length !== 1 ? 's' : ''} found)
            </Alert>
            <Box sx={{ display: 'flex', gap: 2, alignItems: 'flex-end', mb: 2 }}>
              <FormControl sx={{ minWidth: 200 }} size="small">
                <InputLabel>Filter by Organization</InputLabel>
                <Select
                  value={selectedOrg}
                  onChange={(e) => setSelectedOrg(e.target.value)}
                  label="Filter by Organization"
                >
                  <MenuItem value="">All Organizations</MenuItem>
                  {orgs.map((o) => (
                    <MenuItem key={o.moid} value={o.name}>{o.name}</MenuItem>
                  ))}
                </Select>
              </FormControl>
              <Button
                variant="contained"
                startIcon={<CloudDownloadIcon />}
                onClick={handleFetch}
              >
                Fetch Resources
              </Button>
            </Box>
          </Box>
        )}

        {step === 'fetching' && (
          <Box sx={{ textAlign: 'center', py: 4 }}>
            <CircularProgress sx={{ mb: 2 }} />
            <Typography color="text.secondary">Fetching resources from Intersight...</Typography>
            <Typography variant="caption" color="text.secondary">This may take 30-60 seconds for large domains</Typography>
          </Box>
        )}

        {step === 'done' && resources && (
          <Box>
            <Alert severity="info" sx={{ mb: 2 }}>
              Found {total} resource{total !== 1 ? 's' : ''} across {Object.keys(resources).length} categories
              {selectedOrg && ` (filtered to "${selectedOrg}")`}
            </Alert>
            {Object.entries(resources).map(([category, types]) => (
              <Accordion key={category} defaultExpanded disableGutters>
                <AccordionSummary expandIcon={<ExpandMoreIcon />}>
                  <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                    {CATEGORY_ICONS[category]}
                    <Typography variant="subtitle2" sx={{ fontWeight: 700, textTransform: 'capitalize' }}>
                      {category}
                    </Typography>
                    <Chip
                      label={Object.values(types).reduce((s, arr) => s + arr.length, 0)}
                      size="small" color="primary" variant="outlined"
                    />
                  </Box>
                </AccordionSummary>
                <AccordionDetails sx={{ pt: 0 }}>
                  {Object.entries(types).map(([rtype, items]) => (
                    <Box key={rtype} sx={{ mb: 1.5 }}>
                      <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 0.5 }}>
                        <Typography variant="body2" sx={{ fontWeight: 600 }}>
                          {rtype.replace(/_/g, ' ')}
                        </Typography>
                        <Chip label={items.length} size="small" />
                      </Box>
                      {items.map((item) => (
                        <Box
                          key={item.moid}
                          sx={{
                            display: 'flex', alignItems: 'center', gap: 1,
                            pl: 2, py: 0.4,
                            '&:hover': { bgcolor: 'action.hover' },
                            borderRadius: 1,
                          }}
                        >
                          <Typography variant="body2" sx={{ flex: 1 }}>
                            {item.name}
                          </Typography>
                          {item.organization && item.organization !== 'default' && (
                            <Chip label={item.organization} size="small" variant="outlined" sx={{ fontSize: 10 }} />
                          )}
                          {item.description && (
                            <Typography variant="caption" color="text.secondary" sx={{ maxWidth: 200, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                              {item.description}
                            </Typography>
                          )}
                        </Box>
                      ))}
                    </Box>
                  ))}
                </AccordionDetails>
              </Accordion>
            ))}
          </Box>
        )}
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose}>Close</Button>
        {step === 'done' && (
          <Button variant="outlined" startIcon={<CloudDownloadIcon />} onClick={handleFetch}>
            Refresh
          </Button>
        )}
      </DialogActions>
    </Dialog>
  );
}
