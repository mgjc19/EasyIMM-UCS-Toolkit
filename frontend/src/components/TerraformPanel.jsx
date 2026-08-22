import { useState, useRef, useEffect, useMemo } from 'react';
import Box from '@mui/material/Box';
import Button from '@mui/material/Button';
import ButtonGroup from '@mui/material/ButtonGroup';
import Typography from '@mui/material/Typography';
import Chip from '@mui/material/Chip';
import IconButton from '@mui/material/IconButton';
import Alert from '@mui/material/Alert';
import AlertTitle from '@mui/material/AlertTitle';
import ClearIcon from '@mui/icons-material/Clear';
import ExpandLessIcon from '@mui/icons-material/ExpandLess';
import ExpandMoreIcon from '@mui/icons-material/ExpandMore';
import CheckCircleIcon from '@mui/icons-material/CheckCircle';
import Tooltip from '@mui/material/Tooltip';
import Dialog from '@mui/material/Dialog';
import DialogTitle from '@mui/material/DialogTitle';
import DialogContent from '@mui/material/DialogContent';
import DialogActions from '@mui/material/DialogActions';
import { api } from '../api';

function colorize(line) {
  if (line.includes('Error') || line.includes('error')) return 'error.main';
  if (/^\s*\+/.test(line) || (line.includes('Plan:') && line.includes('to add'))) return 'success.main';
  if (/^\s*-/.test(line) || line.includes('to destroy')) return 'error.main';
  if (/^\s*~/.test(line) || line.includes('to change')) return 'warning.main';
  return 'text.primary';
}

const SEARCH_ERR_RE = /SearchSearchItem data source did not return any results/;
const ISX_POLICY_RE = /intersight_search_search_item\.policies\["([^"]+)"\]/;
const MODULE_RE = /module\.(\w+)\["([^"]+)"\]/;

function parseErrorSummary(lines) {
  const errors = [];
  const fullText = lines.join('');

  if (SEARCH_ERR_RE.test(fullText)) {
    const blocks = fullText.split(/Error:/g).slice(1);
    const seen = new Set();
    for (const block of blocks) {
      if (SEARCH_ERR_RE.test(block)) {
        const m = block.match(ISX_POLICY_RE);
        const policyType = m ? m[1] : 'unknown';
        if (seen.has(policyType)) continue;
        seen.add(policyType);
        const moduleMatch = block.match(MODULE_RE);
        const callerModule = moduleMatch ? moduleMatch[1] : null;
        const callerName = moduleMatch ? moduleMatch[2] : null;
        const callerInfo = callerModule ? ` (referenced by ${callerModule} "${callerName}")` : '';
        errors.push({
          type: 'missing_policy',
          policyType,
          message: `"${policyType}" policy not found on Intersight${callerInfo}. Deploy "${policyType}" policies to Intersight first, then re-run plan.`,
        });
      }
    }
  }

  const missingAttr = [...fullText.matchAll(/Unsupported attribute[\s\S]*?This object does not have an attribute named "([^"]+)"/g)];
  for (const m of missingAttr) {
    errors.push({
      type: 'missing_attribute',
      attribute: m[1],
      message: `A resource is missing the required attribute "${m[1]}". Check that all required fields are filled in.`,
    });
  }

  const invalidIdx = [...fullText.matchAll(/Invalid index[\s\S]*?The given key does not identify an element/g)];
  if (invalidIdx.length > 0) {
    errors.push({
      type: 'invalid_index',
      message: `An organization or resource key was not recognized. Check for MOID-based org names or typos in organization names.`,
    });
  }

  return errors;
}

export default function TerraformPanel() {
  const [output, setOutput] = useState([]);
  const [running, setRunning] = useState(false);
  const [currentAction, setCurrentAction] = useState(null);
  const [lastStatus, setLastStatus] = useState(null);
  const [expanded, setExpanded] = useState(true);
  const [confirmDestroy, setConfirmDestroy] = useState(false);
  const [preflightResult, setPreflightResult] = useState(null);
  const [preflightLoading, setPreflightLoading] = useState(false);
  const [preflightWarningAction, setPreflightWarningAction] = useState(null);
  const logRef = useRef(null);
  const wsRef = useRef(null);

  useEffect(() => {
    if (logRef.current) {
      logRef.current.scrollTop = logRef.current.scrollHeight;
    }
  }, [output]);

  const errorSummary = useMemo(() => {
    if (lastStatus !== 'error' || output.length === 0) return [];
    return parseErrorSummary(output);
  }, [output, lastStatus]);

  const runAction = (action, targets = null) => {
    setOutput([]);
    setRunning(true);
    setCurrentAction(action);
    setLastStatus(null);
    setPreflightResult(null);
    setExpanded(true);

    const proto = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const ws = new WebSocket(`${proto}//${window.location.host}/ws/terraform`);
    wsRef.current = ws;

    ws.onopen = () => {
      const payload = { action };
      if (targets) payload.targets = targets;
      ws.send(JSON.stringify(payload));
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

  const runPreflight = async () => {
    setPreflightLoading(true);
    setPreflightResult(null);
    try {
      const result = await api.validateConfig();
      setPreflightResult(result);
      setExpanded(true);
      return result;
    } catch (e) {
      setPreflightResult({ ok: false, summary: e.message, issues: [], total: 0 });
      return null;
    } finally {
      setPreflightLoading(false);
    }
  };

  const handleWithPreflight = (action) => async () => {
    const result = await runPreflight();
    if (!result) return;
    if (!result.ok) {
      setPreflightWarningAction(action);
    } else if (result.deploy_order?.length > 0) {
      setPreflightWarningAction(action);
    } else {
      runAction(action);
    }
  };

  const handleDestroy = () => {
    setConfirmDestroy(false);
    runAction('destroy');
  };

  const proceedDespiteWarnings = () => {
    const action = preflightWarningAction;
    setPreflightWarningAction(null);
    if (action) runAction(action);
  };

  return (
    <Box sx={{ borderTop: '1px solid', borderColor: 'divider', bgcolor: 'background.paper' }}>
      <Box sx={{ display: 'flex', alignItems: 'center', px: 2, py: 0.5, gap: 1, flexWrap: 'wrap' }}>
        <Typography variant="subtitle2" sx={{ fontWeight: 700, mr: 1 }}>Terraform</Typography>
        <ButtonGroup size="small" disabled={running || preflightLoading}>
          <Button onClick={handleWithPreflight('validate')}>Validate</Button>
          <Button onClick={handleWithPreflight('plan')} color="primary">Plan</Button>
          <Button onClick={handleWithPreflight('apply_plan')} color="success">Apply</Button>
          <Button onClick={() => setConfirmDestroy(true)} color="error">Destroy</Button>
        </ButtonGroup>
        <Button
          size="small"
          onClick={() => runAction('init')}
          disabled={running || preflightLoading}
          sx={{ ml: 0.5 }}
        >
          Init
        </Button>
        <Button
          size="small"
          onClick={runPreflight}
          disabled={running || preflightLoading}
          variant="outlined"
          startIcon={preflightLoading ? null : <CheckCircleIcon sx={{ fontSize: 14 }} />}
        >
          {preflightLoading ? 'Checking...' : 'Check Config'}
        </Button>
        <Button size="small" onClick={() => runAction('state_list')} disabled={running || preflightLoading}>
          Status
        </Button>
        <Box sx={{ flex: 1 }} />
        {running && <Chip label={`Running: ${currentAction}`} size="small" color="warning" />}
        {lastStatus === 'success' && <Chip label="Success" size="small" color="success" />}
        {lastStatus === 'error' && <Chip label="Failed" size="small" color="error" />}
        <Tooltip title="Clear">
          <IconButton size="small" onClick={() => { setOutput([]); setLastStatus(null); setPreflightResult(null); }}>
            <ClearIcon fontSize="small" />
          </IconButton>
        </Tooltip>
        <IconButton size="small" onClick={() => setExpanded(!expanded)}>
          {expanded ? <ExpandMoreIcon fontSize="small" /> : <ExpandLessIcon fontSize="small" />}
        </IconButton>
      </Box>

      {expanded && (
        <>
          {/* Pre-flight result banner */}
          {preflightResult && !running && (
            <Box sx={{ px: 2, pt: 1, display: 'flex', flexDirection: 'column', gap: 1 }}>
              {preflightResult.ok && !(preflightResult.deploy_order?.length) && (
                <Alert severity="success" sx={{ py: 0.5 }}>
                  {preflightResult.summary}
                </Alert>
              )}
              {preflightResult.ok && preflightResult.deploy_order?.length > 0 && (
                <Alert severity="info" sx={{ py: 0.5 }}>
                  <AlertTitle sx={{ fontSize: 13, fontWeight: 700 }}>
                    Deployment Order Required
                  </AlertTitle>
                  <Typography variant="caption" sx={{ display: 'block', mb: 0.5 }}>
                    {preflightResult.summary}
                  </Typography>
                  {preflightResult.deploy_order.map((w, i) => (
                    <Typography key={i} variant="caption" sx={{ display: 'block', pl: 1, color: 'text.secondary' }}>
                      &bull; {w.message}
                    </Typography>
                  ))}
                  <Typography variant="caption" sx={{ display: 'block', mt: 1, color: 'info.main', fontWeight: 600 }}>
                    Tip: Use same-org references (e.g. "mcast" not "mcast (common)") so all policies
                    deploy in a single pass. Cross-org references require the target org to be deployed first.
                  </Typography>
                </Alert>
              )}
              {!preflightResult.ok && (
                <Alert severity="warning" sx={{ py: 0.5 }}>
                  <AlertTitle sx={{ fontSize: 13, fontWeight: 700 }}>
                    Config Check: {preflightResult.total} issue(s) found
                  </AlertTitle>
                  <Typography variant="caption" sx={{ display: 'block', mb: 0.5 }}>
                    {preflightResult.summary}
                  </Typography>
                  {preflightResult.issues?.slice(0, 8).map((issue, i) => (
                    <Typography key={i} variant="caption" sx={{ display: 'block', pl: 1, color: 'text.secondary' }}>
                      &bull; {issue.message}
                    </Typography>
                  ))}
                  {preflightResult.total > 8 && (
                    <Typography variant="caption" sx={{ display: 'block', pl: 1, mt: 0.5, fontStyle: 'italic' }}>
                      ...and {preflightResult.total - 8} more
                    </Typography>
                  )}
                </Alert>
              )}
            </Box>
          )}

          {/* Terraform error summary banner */}
          {errorSummary.length > 0 && (
            <Box sx={{ px: 2, pt: 1 }}>
              <Alert severity="error" sx={{ py: 0.5 }}>
                <AlertTitle sx={{ fontSize: 13, fontWeight: 700 }}>
                  Terraform Error Summary
                </AlertTitle>
                {errorSummary.map((err, i) => (
                  <Typography key={i} variant="caption" sx={{ display: 'block', mb: 0.3 }}>
                    &bull; {err.message}
                  </Typography>
                ))}
              </Alert>
            </Box>
          )}

          {/* Raw log output */}
          <Box
            ref={logRef}
            sx={{
              height: 250, overflow: 'auto', px: 2, py: 1,
              fontFamily: '"JetBrains Mono", "Fira Code", monospace',
              fontSize: 12, lineHeight: 1.6,
              bgcolor: '#0d1117',
            }}
          >
            {output.length === 0 && !preflightResult && (
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
        </>
      )}

      {/* Pre-flight warning dialog */}
      <Dialog open={!!preflightWarningAction} onClose={() => setPreflightWarningAction(null)} maxWidth="sm" fullWidth>
        <DialogTitle>
          {preflightResult?.total > 0 ? 'Config Issues Detected' : 'Deployment Order Required'}
        </DialogTitle>
        <DialogContent>
          {preflightResult?.total > 0 ? (
            <>
              <Typography variant="body2" sx={{ mb: 1.5 }}>
                The config check found <b>{preflightResult.total} issue(s)</b>.
                Terraform will likely fail until these are resolved.
              </Typography>
              {preflightResult.issues?.slice(0, 5).map((issue, i) => (
                <Typography key={i} variant="caption" sx={{ display: 'block', pl: 1, mb: 0.3, color: 'text.secondary' }}>
                  &bull; {issue.message}
                </Typography>
              ))}
              {preflightResult.total > 5 && (
                <Typography variant="caption" sx={{ display: 'block', pl: 1, mt: 0.5, fontStyle: 'italic' }}>
                  ...and {preflightResult.total - 5} more
                </Typography>
              )}
            </>
          ) : (
            <>
              <Typography variant="body2" sx={{ mb: 1.5 }}>
                Some policies reference other policies that must be <b>deployed to Intersight first</b>.
                Running plan/apply now will fail because Terraform looks up referenced policies on Intersight.
              </Typography>
              {preflightResult?.deploy_order?.slice(0, 5).map((w, i) => (
                <Typography key={i} variant="caption" sx={{ display: 'block', pl: 1, mb: 0.3, color: 'text.secondary' }}>
                  &bull; Deploy <b>{w.to_type}</b> first (needed by {w.from_type})
                </Typography>
              ))}
              <Typography variant="body2" sx={{ mt: 1.5, fontWeight: 600 }}>
                Tip: Change cross-org references to same-org so everything deploys in one pass.
              </Typography>
            </>
          )}
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setPreflightWarningAction(null)}>Cancel</Button>
          <Button variant="outlined" color="warning" onClick={proceedDespiteWarnings}>
            {preflightWarningAction === 'plan' ? 'Plan Anyway' : 'Proceed Anyway'}
          </Button>
        </DialogActions>
      </Dialog>

      {/* Destroy confirmation dialog */}
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
