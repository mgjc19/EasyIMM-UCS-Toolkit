import { useState, useEffect } from 'react';
import Dialog from '@mui/material/Dialog';
import DialogTitle from '@mui/material/DialogTitle';
import DialogContent from '@mui/material/DialogContent';
import DialogActions from '@mui/material/DialogActions';
import Button from '@mui/material/Button';
import TextField from '@mui/material/TextField';
import MenuItem from '@mui/material/MenuItem';
import Typography from '@mui/material/Typography';

export default function CloneDialog({ open, onClose, onClone, orgs, srcOrg, category, resourceType, srcName }) {
  const [dstOrg, setDstOrg] = useState('');
  const [dstName, setDstName] = useState('');

  useEffect(() => {
    if (open) {
      setDstOrg(srcOrg || '');
      setDstName(srcName ? `${srcName}-copy` : '');
    }
  }, [open, srcOrg, srcName]);

  const handleClone = () => {
    onClone({
      src_org: srcOrg,
      dst_org: dstOrg,
      category,
      resource_type: resourceType,
      src_name: srcName,
      dst_name: dstName,
    });
    onClose();
  };

  return (
    <Dialog open={open} onClose={onClose} maxWidth="xs" fullWidth>
      <DialogTitle>Clone Resource</DialogTitle>
      <DialogContent dividers>
        <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
          Clone "{srcName}" from {srcOrg}/{category}/{resourceType}
        </Typography>
        <TextField
          select fullWidth label="Destination Organization" margin="dense"
          value={dstOrg} onChange={(e) => setDstOrg(e.target.value)}
        >
          {(orgs || []).map((o) => <MenuItem key={o} value={o}>{o}</MenuItem>)}
        </TextField>
        <TextField
          fullWidth label="New Name" margin="dense"
          value={dstName} onChange={(e) => setDstName(e.target.value)}
        />
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose}>Cancel</Button>
        <Button variant="contained" onClick={handleClone} disabled={!dstName || !dstOrg}>Clone</Button>
      </DialogActions>
    </Dialog>
  );
}
