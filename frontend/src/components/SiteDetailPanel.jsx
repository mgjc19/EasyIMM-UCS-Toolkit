import { useState } from 'react';
import Box from '@mui/material/Box';
import Typography from '@mui/material/Typography';
import Chip from '@mui/material/Chip';
import Divider from '@mui/material/Divider';
import IconButton from '@mui/material/IconButton';
import Button from '@mui/material/Button';
import CloseIcon from '@mui/icons-material/Close';
import StorageIcon from '@mui/icons-material/Storage';
import SecurityIcon from '@mui/icons-material/Security';
import DnsIcon from '@mui/icons-material/Dns';
import DescriptionIcon from '@mui/icons-material/Description';
import FolderIcon from '@mui/icons-material/Folder';
import FileDownloadIcon from '@mui/icons-material/FileDownload';
import Menu from '@mui/material/Menu';
import MenuItem from '@mui/material/MenuItem';
import ListItemIcon from '@mui/material/ListItemIcon';
import ListItemText from '@mui/material/ListItemText';
import CodeIcon from '@mui/icons-material/Code';
import DataObjectIcon from '@mui/icons-material/DataObject';

const CATEGORY_META = {
  pools: { label: 'Pools', icon: <StorageIcon fontSize="small" color="primary" />, color: 'primary' },
  policies: { label: 'Policies', icon: <SecurityIcon fontSize="small" color="secondary" />, color: 'secondary' },
  profiles: { label: 'Profiles', icon: <DnsIcon fontSize="small" color="success" />, color: 'success' },
  templates: { label: 'Templates', icon: <DescriptionIcon fontSize="small" color="warning" />, color: 'warning' },
};

const FRIENDLY = {
  ip: 'IP', iqn: 'IQN', mac: 'MAC', resource: 'Resource', uuid: 'UUID', wwnn: 'WWNN', wwpn: 'WWPN',
  adapter_configuration: 'Adapter Config', bios: 'BIOS', boot_order: 'Boot Order',
  certificate_management: 'Certificate Mgmt', device_connector: 'Device Connector',
  drive_security: 'Drive Security', ethernet_adapter: 'Ethernet Adapter',
  ethernet_network: 'Ethernet Network', ethernet_network_control: 'Ethernet Net Control',
  ethernet_network_group: 'Ethernet Net Group', ethernet_qos: 'Ethernet QoS',
  fc_zone: 'FC Zone', fibre_channel_adapter: 'FC Adapter',
  fibre_channel_network: 'FC Network', fibre_channel_qos: 'FC QoS',
  firmware: 'Firmware', firmware_authenticate: 'Firmware Auth',
  flow_control: 'Flow Control', imc_access: 'IMC Access', ipmi_over_lan: 'IPMI Over LAN',
  iscsi_adapter: 'iSCSI Adapter', iscsi_boot: 'iSCSI Boot',
  iscsi_static_target: 'iSCSI Target', lan_connectivity: 'LAN Connectivity',
  ldap: 'LDAP', link_aggregation: 'Link Aggregation', link_control: 'Link Control',
  local_user: 'Local User', mac_sec: 'MACsec', memory: 'Memory', multicast: 'Multicast',
  network_connectivity: 'DNS', ntp: 'NTP', persistent_memory: 'Persistent Memory',
  port: 'Port', power: 'Power', san_connectivity: 'SAN Connectivity', scrub: 'Scrub',
  sd_card: 'SD Card', serial_over_lan: 'Serial Over LAN',
  server_pool_qualification: 'Server Pool Qual', smtp: 'SMTP', snmp: 'SNMP', ssh: 'SSH',
  storage: 'Storage', switch_control: 'Switch Control', syslog: 'Syslog',
  system_qos: 'System QoS', thermal: 'Thermal', vhba_template: 'vHBA Template',
  virtual_kvm: 'Virtual KVM', virtual_media: 'Virtual Media', vlan: 'VLAN',
  vnic_template: 'vNIC Template', vsan: 'VSAN',
  chassis: 'Chassis', domain: 'Domain', server: 'Server',
};

function friendlyName(type) {
  return FRIENDLY[type] || type.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase());
}

function extractResources(orgData) {
  const categories = ['pools', 'policies', 'profiles', 'templates'];
  const results = [];

  for (const cat of categories) {
    const catData = orgData?.[cat];
    if (!catData || typeof catData !== 'object') {
      results.push({ cat, types: [], total: 0 });
      continue;
    }

    const types = [];
    for (const [type, items] of Object.entries(catData)) {
      if (!Array.isArray(items) || items.length === 0) continue;
      const names = items.map((item) => {
        if (typeof item === 'string') return item;
        if (typeof item === 'object' && item !== null) {
          return item.name || item.data?.name || '(unnamed)';
        }
        return '(unnamed)';
      });
      types.push({ type, count: items.length, names });
    }

    const total = types.reduce((n, t) => n + t.count, 0);
    results.push({ cat, types, total });
  }

  return results;
}

export default function SiteDetailPanel({ org, orgData, onClose, onDownloadYaml, onDownloadXml }) {
  const [dlAnchor, setDlAnchor] = useState(null);

  if (!orgData) return null;

  const stats = extractResources(orgData);
  const totalResources = stats.reduce((n, s) => n + s.total, 0);

  return (
    <Box sx={{ display: 'flex', flexDirection: 'column', height: '100%' }}>
      <Box sx={{
        display: 'flex', alignItems: 'center', gap: 1,
        px: 2.5, py: 1.5,
        borderBottom: '1px solid', borderColor: 'divider',
        bgcolor: 'background.paper',
      }}>
        <FolderIcon color="primary" />
        <Box sx={{ flex: 1 }}>
          <Typography variant="subtitle1" sx={{ fontWeight: 700 }}>{org}</Typography>
          <Typography variant="caption" color="text.secondary">
            Site / Domain Overview
          </Typography>
        </Box>
        <Chip label={`${totalResources} resource${totalResources !== 1 ? 's' : ''}`} size="small" color="primary" variant="outlined" />
        <IconButton size="small" onClick={(e) => setDlAnchor(e.currentTarget)}>
          <FileDownloadIcon fontSize="small" />
        </IconButton>
        <Menu
          anchorEl={dlAnchor}
          open={Boolean(dlAnchor)}
          onClose={() => setDlAnchor(null)}
          anchorOrigin={{ vertical: 'bottom', horizontal: 'right' }}
          transformOrigin={{ vertical: 'top', horizontal: 'right' }}
        >
          <MenuItem onClick={() => { setDlAnchor(null); onDownloadYaml?.(); }}>
            <ListItemIcon><DataObjectIcon fontSize="small" /></ListItemIcon>
            <ListItemText>Download as YAML</ListItemText>
          </MenuItem>
          <MenuItem onClick={() => { setDlAnchor(null); onDownloadXml?.(); }}>
            <ListItemIcon><CodeIcon fontSize="small" /></ListItemIcon>
            <ListItemText>Download as XML</ListItemText>
          </MenuItem>
        </Menu>
        <IconButton size="small" onClick={onClose}>
          <CloseIcon fontSize="small" />
        </IconButton>
      </Box>

      <Box sx={{ flex: 1, overflow: 'auto', px: 2.5, py: 2 }}>
        {/* Summary cards */}
        <Box sx={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(140px, 1fr))', gap: 1.5, mb: 3 }}>
          {stats.map(({ cat, total }) => {
            const meta = CATEGORY_META[cat];
            return (
              <Box
                key={cat}
                sx={{
                  p: 1.5, borderRadius: 1.5,
                  border: '1px solid', borderColor: 'divider',
                  display: 'flex', alignItems: 'center', gap: 1,
                }}
              >
                {meta.icon}
                <Box>
                  <Typography variant="h6" sx={{ lineHeight: 1, fontWeight: 700 }}>{total}</Typography>
                  <Typography variant="caption" color="text.secondary">{meta.label}</Typography>
                </Box>
              </Box>
            );
          })}
        </Box>

        <Divider sx={{ mb: 2 }} />

        {/* Detailed breakdown per category */}
        {stats.filter((s) => s.total > 0).map(({ cat, types }) => {
          const meta = CATEGORY_META[cat];
          return (
            <Box key={cat} sx={{ mb: 2.5 }}>
              <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 1 }}>
                {meta.icon}
                <Typography variant="subtitle2" sx={{ fontWeight: 700 }}>{meta.label}</Typography>
                <Chip label={types.reduce((n, t) => n + t.count, 0)} size="small" variant="outlined" />
              </Box>
              <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 0.8, pl: 3.5 }}>
                {types.map(({ type, count, names }) => (
                  <Chip
                    key={type}
                    label={`${friendlyName(type)} (${count})`}
                    size="small"
                    variant="outlined"
                    color={meta.color}
                    title={names.join(', ')}
                  />
                ))}
              </Box>
            </Box>
          );
        })}

        {totalResources === 0 && (
          <Box sx={{ textAlign: 'center', py: 4, color: 'text.secondary' }}>
            <Typography variant="body2">
              This site has no resources yet. Use the <b>+</b> buttons in the tree to add pools, policies, profiles, or templates.
            </Typography>
          </Box>
        )}

        {/* Resource name listing */}
        {totalResources > 0 && (
          <>
            <Divider sx={{ my: 2 }} />
            <Typography variant="subtitle2" sx={{ fontWeight: 700, mb: 1 }}>All Resources</Typography>
            <Box
              component="table"
              sx={{
                width: '100%', borderCollapse: 'collapse',
                '& th, & td': { px: 1.5, py: 0.6, textAlign: 'left', fontSize: 12 },
                '& th': { fontWeight: 700, borderBottom: '2px solid', borderColor: 'divider' },
                '& td': { borderBottom: '1px solid', borderColor: 'divider' },
              }}
            >
              <thead>
                <tr>
                  <th>Category</th>
                  <th>Type</th>
                  <th>Name</th>
                </tr>
              </thead>
              <tbody>
                {stats.flatMap(({ cat, types }) =>
                  types.flatMap(({ type, names }) =>
                    names.map((name, idx) => (
                      <tr key={`${cat}-${type}-${idx}`}>
                        <td>{CATEGORY_META[cat]?.label || cat}</td>
                        <td>{friendlyName(type)}</td>
                        <td><code>{name}</code></td>
                      </tr>
                    ))
                  )
                )}
              </tbody>
            </Box>
          </>
        )}
      </Box>
    </Box>
  );
}
