import { useState } from 'react';
import Box from '@mui/material/Box';
import Typography from '@mui/material/Typography';
import IconButton from '@mui/material/IconButton';
import Collapse from '@mui/material/Collapse';
import Tooltip from '@mui/material/Tooltip';
import AddIcon from '@mui/icons-material/Add';
import ExpandMoreIcon from '@mui/icons-material/ExpandMore';
import ChevronRightIcon from '@mui/icons-material/ChevronRight';
import FolderIcon from '@mui/icons-material/Folder';
import AccountTreeIcon from '@mui/icons-material/AccountTree';
import StorageIcon from '@mui/icons-material/Storage';
import PolicyIcon from '@mui/icons-material/Security';
import DnsIcon from '@mui/icons-material/Dns';
import ContentCopyIcon from '@mui/icons-material/ContentCopy';
import DeleteIcon from '@mui/icons-material/Delete';
import DescriptionIcon from '@mui/icons-material/Description';
import CloudIcon from '@mui/icons-material/Cloud';
import LanIcon from '@mui/icons-material/Lan';

const CATEGORY_ICONS = {
  pools: <StorageIcon fontSize="small" />,
  policies: <PolicyIcon fontSize="small" />,
  profiles: <DnsIcon fontSize="small" />,
  templates: <DescriptionIcon fontSize="small" />,
};

const CATEGORY_ORDER = ['pools', 'policies', 'profiles', 'templates'];

function TreeItem({ label, icon, depth = 0, children, count, onAdd, onClick, onDelete, onClone, expandedByDefault = false }) {
  const [open, setOpen] = useState(expandedByDefault);
  const hasChildren = Boolean(children);
  const pl = depth * 2;

  return (
    <Box>
      <Box
        sx={{
          display: 'flex', alignItems: 'center', pl, pr: 1, py: 0.3,
          cursor: hasChildren || onClick ? 'pointer' : 'default',
          '&:hover': { bgcolor: 'action.hover' },
          borderRadius: 1,
        }}
        onClick={() => {
          if (onClick) onClick();
          else if (hasChildren) setOpen(!open);
        }}
      >
        {hasChildren ? (
          <IconButton size="small" onClick={(e) => { e.stopPropagation(); setOpen(!open); }} sx={{ p: 0.3 }}>
            {open ? <ExpandMoreIcon fontSize="small" /> : <ChevronRightIcon fontSize="small" />}
          </IconButton>
        ) : (
          <Box sx={{ width: 24 }} />
        )}
        {icon && <Box sx={{ mr: 0.8, display: 'flex', color: 'primary.main' }}>{icon}</Box>}
        <Typography variant="body2" sx={{ flex: 1, fontWeight: depth <= 1 ? 600 : 400 }}>
          {label}
          {count !== undefined && <Typography component="span" variant="caption" sx={{ ml: 0.5, color: 'text.secondary' }}>({count})</Typography>}
        </Typography>
        {onClone && (
          <Tooltip title="Clone">
            <IconButton size="small" onClick={(e) => { e.stopPropagation(); onClone(); }} sx={{ opacity: 0.5, '&:hover': { opacity: 1 } }}>
              <ContentCopyIcon sx={{ fontSize: 14 }} />
            </IconButton>
          </Tooltip>
        )}
        {onDelete && (
          <Tooltip title="Delete">
            <IconButton size="small" onClick={(e) => { e.stopPropagation(); onDelete(); }} sx={{ opacity: 0.5, '&:hover': { opacity: 1, color: 'error.main' } }}>
              <DeleteIcon sx={{ fontSize: 14 }} />
            </IconButton>
          </Tooltip>
        )}
        {onAdd && (
          <Tooltip title="Add">
            <IconButton size="small" onClick={(e) => { e.stopPropagation(); onAdd(); }} sx={{ opacity: 0.6, '&:hover': { opacity: 1, color: 'secondary.main' } }}>
              <AddIcon sx={{ fontSize: 16 }} />
            </IconButton>
          </Tooltip>
        )}
      </Box>
      {hasChildren && <Collapse in={open}>{children}</Collapse>}
    </Box>
  );
}

const FRIENDLY = {
  ip: 'IP', iqn: 'IQN', mac: 'MAC', resource: 'Resource', uuid: 'UUID', wwnn: 'WWNN', wwpn: 'WWPN',
  adapter_configuration: 'Adapter Config', bios: 'BIOS', boot_order: 'Boot Order',
  certificate_management: 'Certificate Mgmt', device_connector: 'Device Connector',
  drive_security: 'Drive Security', ethernet_adapter: 'Eth Adapter', ethernet_network: 'Eth Network',
  ethernet_network_control: 'Eth Net Control', ethernet_network_group: 'Eth Net Group',
  ethernet_qos: 'Eth QoS', fc_zone: 'FC Zone', fibre_channel_adapter: 'FC Adapter',
  fibre_channel_network: 'FC Network', fibre_channel_qos: 'FC QoS', firmware: 'Firmware',
  firmware_authenticate: 'Firmware Auth', flow_control: 'Flow Control', imc_access: 'IMC Access',
  ipmi_over_lan: 'IPMI/LAN', iscsi_adapter: 'iSCSI Adapter', iscsi_boot: 'iSCSI Boot',
  iscsi_static_target: 'iSCSI Target', lan_connectivity: 'LAN Connectivity', ldap: 'LDAP',
  link_aggregation: 'Link Aggregation', link_control: 'Link Control', local_user: 'Local User',
  mac_sec: 'MACsec', memory: 'Memory', multicast: 'Multicast', network_connectivity: 'DNS',
  ntp: 'NTP', persistent_memory: 'Persistent Memory', port: 'Port', power: 'Power',
  san_connectivity: 'SAN Connectivity', scrub: 'Scrub', sd_card: 'SD Card',
  serial_over_lan: 'Serial/LAN', server_pool_qualification: 'Server Pool Qual',
  smtp: 'SMTP', snmp: 'SNMP', ssh: 'SSH', storage: 'Storage', switch_control: 'Switch Control',
  syslog: 'Syslog', system_qos: 'System QoS', thermal: 'Thermal', vhba_template: 'vHBA Template',
  virtual_kvm: 'Virtual KVM', virtual_media: 'Virtual Media', vlan: 'VLAN',
  vnic_template: 'vNIC Template', vsan: 'VSAN', chassis: 'Chassis', domain: 'Domain', server: 'Server',
};

function OrgTree({ org, orgData, types, onSelect, onAdd, onDelete, onClone, depth = 0, expandedByDefault, icon, synced, displayLabel }) {
  return (
    <TreeItem
      label={displayLabel || org} icon={icon || <FolderIcon fontSize="small" />} depth={depth}
      expandedByDefault={expandedByDefault}
      onDelete={synced ? undefined : () => onDelete(org, null, null, null)}
    >
      {CATEGORY_ORDER.map((cat) => {
        const catTypes = types[cat] || [];
        const orgCat = orgData?.[cat] || {};
        return (
          <TreeItem key={cat} label={cat.charAt(0).toUpperCase() + cat.slice(1)} icon={CATEGORY_ICONS[cat]} depth={depth + 1}>
            {catTypes.map(({ type }) => {
              const resources = orgCat[type] || [];
              const isSyncedItem = (r) => r._source && r._source.startsWith('synced:');
              return (
                <TreeItem
                  key={type}
                  label={FRIENDLY[type] || type}
                  depth={depth + 2}
                  count={resources.length}
                  onAdd={() => onAdd(org, cat, type)}
                >
                  {resources.map((r) => (
                    <TreeItem
                      key={r.name}
                      label={r.name}
                      depth={depth + 3}
                      onClick={() => onSelect(org, cat, type, r.data)}
                      onDelete={isSyncedItem(r) ? undefined : () => onDelete(org, cat, type, r.name)}
                      onClone={() => onClone(org, cat, type, r.name)}
                    />
                  ))}
                </TreeItem>
              );
            })}
          </TreeItem>
        );
      })}
    </TreeItem>
  );
}

function resolveMoidLabel(org, moidNames) {
  if (!moidNames) return org;
  const name = moidNames[org];
  if (name) return `${name} (${org.slice(0, 8)}…)`;
  return org;
}

export default function TreeNavigator({ tree, types, onSelect, onAdd, onDelete, onClone, onAddOrg }) {
  if (!tree || !types) return null;

  const syncedDomains = tree._synced_domains || {};
  const moidNames = tree._moid_names || {};
  const localOrgs = Object.keys(tree).filter((k) => !k.startsWith('_'));
  const hasSynced = Object.keys(syncedDomains).length > 0;

  return (
    <Box sx={{ py: 1, overflow: 'auto', height: '100%' }}>
      <Box sx={{ display: 'flex', alignItems: 'center', px: 1, mb: 1 }}>
        <AccountTreeIcon sx={{ mr: 1, color: 'primary.main' }} />
        <Typography variant="subtitle2" sx={{ flex: 1, fontWeight: 700, textTransform: 'uppercase', letterSpacing: 1 }}>
          Resources
        </Typography>
        <Tooltip title="Add Organization">
          <IconButton size="small" onClick={onAddOrg} color="secondary">
            <AddIcon fontSize="small" />
          </IconButton>
        </Tooltip>
      </Box>

      {localOrgs.map((org) => (
        <OrgTree
          key={org} org={org} orgData={tree[org]} types={types}
          onSelect={onSelect} onAdd={onAdd} onDelete={onDelete} onClone={onClone}
          expandedByDefault={localOrgs.length <= 3}
        />
      ))}

      {hasSynced && (
        <Box sx={{ mt: 1.5 }}>
          <Box sx={{ display: 'flex', alignItems: 'center', px: 1, mb: 0.5 }}>
            <CloudIcon sx={{ mr: 1, color: 'success.main', fontSize: 18 }} />
            <Typography variant="subtitle2" sx={{ flex: 1, fontWeight: 700, textTransform: 'uppercase', letterSpacing: 1, color: 'success.main' }}>
              Synced from Intersight
            </Typography>
          </Box>
          {Object.entries(syncedDomains).map(([domain, domainOrgs]) => (
            <TreeItem
              key={domain}
              label={domain}
              icon={<LanIcon fontSize="small" sx={{ color: 'success.main' }} />}
              depth={0}
              expandedByDefault
            >
              {Object.entries(domainOrgs).map(([org, orgData]) => (
                <OrgTree
                  key={org} org={org} orgData={orgData} types={types}
                  onSelect={onSelect} onAdd={onAdd} onDelete={onDelete} onClone={onClone}
                  depth={1} expandedByDefault
                  displayLabel={resolveMoidLabel(org, moidNames)}
                  icon={<FolderIcon fontSize="small" sx={{ color: 'success.main' }} />}
                  synced
                />
              ))}
            </TreeItem>
          ))}
        </Box>
      )}
    </Box>
  );
}
