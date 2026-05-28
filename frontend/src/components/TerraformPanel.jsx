import { useState, useRef, useEffect } from 'react';
import Box from '@mui/material/Box';
import Button from '@mui/material/Button';
import ButtonGroup from '@mui/material/ButtonGroup';
import Typography from '@mui/material/Typography';
import Chip from '@mui/material/Chip';
import IconButton from '@mui/material/IconButton';
import ClearIcon from '@mui/icons-material/Clear';
import ExpandLessIcon from '@mui/icons-material/ExpandLess';
import ExpandMoreIcon from '@mui/icons-material/ExpandMore';
import Tooltip from '@mui/material/Tooltip';
import Dialog from '@mui/material/Dialog';
import DialogTitle from '@mui/material/DialogTitle';
import DialogContent from '@mui/material/DialogContent';
import DialogActions from '@mui/material/DialogActions';

function colorize(line) {
  if (line.includes('Error') || line.includes('error')) return 'error.main';
  if (/^\s*\+/.test(line) || (line.includes('Plan:') && line.includes('to add'))) return 'success.main';
  if (/^\s*-/.test(line) || line.includes('to destroy')) return 'error.main';
  if (/^\s*~/.test(line) || line.includes('to change')) return 'warning.main';
  return 'text.primary';
}

export default function TerraformPanel() {
  const [output, setOutput] = useState([]);
  const [running, setRunning] = useState(false);
  const [currentAction, setCurrentAction] = useState(null);
  const [lastStatus, setLastStatus] = useState(null);
  const [expanded, setExpanded] = useState(true);
  const [confirmDestroy, setConfirmDestroy] = useState(false);
  const logRef = useRef(null);
  const wsRef = useRef(null);

  useEffect(() => {
    if (logRef.current) {
      logRef.current.scrollTop = logRef.current.scrollHeight;
    }
  }, [output]);

  const runAction = (action) => {
    setOutput([]);
    setRunning(true);
    setCurrentAction(action);
    setLastStatus(null);
    setExpanded(true);

    const proto = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const ws = new WebSocket(`${proto}//${window.location.host}/ws/terraform`);
    wsRef.current = ws;

    ws.onopen = () => {
      ws.send(JSON.stringify({ action }));
    };

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
      setOutput((prev) => [...prev, 'WebSocket connection failed. Is the backend running?\n']);
      setRunning(false);
      setLastStatus('error');
    };

    ws.onclose = () => {
      setRunning(false);
    };
  };

  const handleDestroy = () => {
    setConfirmDestroy(false);
    runAction('destroy');
  };

  return (
    <Box sx={{ borderTop: '1px solid', borderColor: 'divider', bgcolor: 'background.paper' }}>
      <Box sx={{ display: 'flex', alignItems: 'center', px: 2, py: 0.5, gap: 1, flexWrap: 'wrap' }}>
        <Typography variant="subtitle2" sx={{ fontWeight: 700, mr: 1 }}>Terraform</Typography>
        <ButtonGroup size="small" disabled={running}>
          <Button onClick={() => runAction('validate')}>Validate</Button>
          <Button onClick={() => runAction('plan')} color="primary">Plan</Button>
          <Button onClick={() => runAction('apply')} color="success">Apply</Button>
          <Button onClick={() => setConfirmDestroy(true)} color="error">Destroy</Button>
        </ButtonGroup>
        <Button size="small" onClick={() => runAction('init')} disabled={running} sx={{ ml: 0.5 }}>
          Init
        </Button>
        <Button size="small" onClick={() => runAction('state_list')} disabled={running}>
          Status
        </Button>
        <Box sx={{ flex: 1 }} />
        {running && <Chip label={`Running: ${currentAction}`} size="small" color="warning" />}
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
        <Box
          ref={logRef}
          sx={{
            height: 250, overflow: 'auto', px: 2, py: 1,
            fontFamily: '"JetBrains Mono", "Fira Code", monospace',
            fontSize: 12, lineHeight: 1.6,
            bgcolor: '#0d1117',
          }}
        >
          {output.length === 0 && (
            <Typography variant="body2" color="text.secondary" sx={{ fontStyle: 'italic' }}>
              Click a button above to run a Terraform command...
            </Typography>
          )}
          {output.map((line, i) => (
            <Box key={i} component="span" sx={{ color: colorize(line), display: 'block', whiteSpace: 'pre-wrap' }}>
              {line}
            </Box>
          ))}
        </Box>
      )}

      <Dialog open={confirmDestroy} onClose={() => setConfirmDestroy(false)}>
        <DialogTitle>Confirm Destroy</DialogTitle>
        <DialogContent>
          <Typography>
            This will destroy ALL managed Intersight resources. This action cannot be undone. Are you sure?
          </Typography>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setConfirmDestroy(false)}>Cancel</Button>
          <Button variant="contained" color="error" onClick={handleDestroy}>Destroy</Button>
        </DialogActions>
      </Dialog>
    </Box>
  );
}
