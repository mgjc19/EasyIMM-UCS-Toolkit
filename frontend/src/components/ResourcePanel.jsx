import { useState, useEffect, useMemo } from 'react';
import Button from '@mui/material/Button';
import TextField from '@mui/material/TextField';
import MenuItem from '@mui/material/MenuItem';
import FormControlLabel from '@mui/material/FormControlLabel';
import Switch from '@mui/material/Switch';
import Typography from '@mui/material/Typography';
import Box from '@mui/material/Box';
import Accordion from '@mui/material/Accordion';
import AccordionSummary from '@mui/material/AccordionSummary';
import AccordionDetails from '@mui/material/AccordionDetails';
import ExpandMoreIcon from '@mui/icons-material/ExpandMore';
import Chip from '@mui/material/Chip';
import IconButton from '@mui/material/IconButton';
import AddIcon from '@mui/icons-material/Add';
import DeleteIcon from '@mui/icons-material/Delete';
import CloseIcon from '@mui/icons-material/Close';
import SaveIcon from '@mui/icons-material/Save';
import InputAdornment from '@mui/material/InputAdornment';
import SearchIcon from '@mui/icons-material/Search';
import Autocomplete from '@mui/material/Autocomplete';
import Divider from '@mui/material/Divider';
import { buildFormSections, getAllResourceNamesForRef } from '../utils/formBuilder';

function FieldRenderer({ field, value, onChange, tree, currentOrg }) {
  const handleChange = (val) => onChange(field.name, val);

  if (field.type === 'boolean') {
    return (
      <FormControlLabel
        control={<Switch checked={!!value} onChange={(e) => handleChange(e.target.checked)} />}
        label={field.label}
        sx={{ my: 0.5 }}
      />
    );
  }

  if (field.is_reference && tree) {
    const refType = field.ref_resource_type || field.name.replace(/_(?:policy|policies|pool|pools|template)$/, '');
    const options = getAllResourceNamesForRef(tree, refType);
    const isMulti = field.type === 'array';

    if (options.length > 0) {
      return (
        <Autocomplete
          freeSolo
          multiple={isMulti}
          options={options.map((o) => o.label)}
          value={value ?? (isMulti ? [] : '')}
          onChange={(_, newVal) => handleChange(newVal)}
          renderInput={(params) => (
            <TextField
              {...params}
              label={field.label}
              helperText={field.description || 'Type or select a resource name'}
              margin="dense"
              required={field.required}
            />
          )}
          sx={{ my: 0.5 }}
        />
      );
    }

    return (
      <TextField
        fullWidth label={field.label} value={value ?? field.default ?? ''}
        onChange={(e) => handleChange(e.target.value)}
        helperText={field.description || 'Reference by name. Use org/name for cross-org refs.'}
        margin="dense" required={field.required}
      />
    );
  }

  if (field.type === 'select') {
    return (
      <TextField
        select fullWidth label={field.label} value={value ?? field.default ?? ''}
        onChange={(e) => handleChange(e.target.value)}
        helperText={field.description} margin="dense" required={field.required}
      >
        {(field.options || []).map((opt) => (
          <MenuItem key={opt} value={opt}>{opt}</MenuItem>
        ))}
      </TextField>
    );
  }

  if (field.type === 'integer' || field.type === 'number') {
    return (
      <TextField
        fullWidth type="number" label={field.label}
        value={value ?? field.default ?? ''}
        onChange={(e) => handleChange(field.type === 'integer' ? parseInt(e.target.value) : parseFloat(e.target.value))}
        helperText={field.description} margin="dense" required={field.required}
        inputProps={{ min: field.minimum, max: field.maximum }}
      />
    );
  }

  if (field.type === 'array' && field.item_fields) {
    const items = Array.isArray(value) ? value : [];
    return (
      <Box sx={{ my: 1, p: 1.5, border: '1px solid', borderColor: 'divider', borderRadius: 1 }}>
        <Box sx={{ display: 'flex', alignItems: 'center', mb: 1 }}>
          <Typography variant="body2" sx={{ fontWeight: 600, flex: 1 }}>{field.label}</Typography>
          <Chip label={items.length} size="small" sx={{ mr: 1 }} />
          <IconButton size="small" onClick={() => handleChange([...items, {}])} color="secondary">
            <AddIcon fontSize="small" />
          </IconButton>
        </Box>
        {field.description && (
          <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mb: 1 }}>
            {field.description.split('\n')[0]}
          </Typography>
        )}
        {items.length === 0 && (
          <Box sx={{ py: 2, textAlign: 'center', bgcolor: 'action.hover', borderRadius: 1 }}>
            <Typography variant="body2" color="text.secondary">
              No entries yet. Click <b>+</b> to add one.
            </Typography>
          </Box>
        )}
        {items.map((item, idx) => (
          <Box key={idx} sx={{ pl: 2, borderLeft: '2px solid', borderColor: 'secondary.main', mb: 1.5, pt: 0.5 }}>
            <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 0.5 }}>
              <Typography variant="caption" sx={{ fontWeight: 600 }}>Entry #{idx + 1}</Typography>
              <IconButton size="small" onClick={() => handleChange(items.filter((_, i) => i !== idx))} color="error">
                <DeleteIcon sx={{ fontSize: 14 }} />
              </IconButton>
            </Box>
            {field.item_fields.map((subField) => (
              <FieldRenderer
                key={subField.name} field={subField} value={item[subField.name]}
                onChange={(name, val) => {
                  const updated = [...items];
                  updated[idx] = { ...updated[idx], [name]: val };
                  handleChange(updated);
                }}
                tree={tree} currentOrg={currentOrg}
              />
            ))}
          </Box>
        ))}
      </Box>
    );
  }

  if (field.type === 'array') {
    const items = Array.isArray(value) ? value : [];
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
            {field.item_type === 'select' ? (
              <TextField
                select fullWidth size="small" value={item}
                onChange={(e) => {
                  const updated = [...items];
                  updated[idx] = e.target.value;
                  handleChange(updated);
                }}
              >
                {(field.options || []).map((opt) => (
                  <MenuItem key={opt} value={opt}>{opt}</MenuItem>
                ))}
              </TextField>
            ) : (
              <TextField
                fullWidth size="small" value={item}
                onChange={(e) => {
                  const updated = [...items];
                  updated[idx] = e.target.value;
                  handleChange(updated);
                }}
              />
            )}
            <IconButton size="small" onClick={() => handleChange(items.filter((_, i) => i !== idx))} color="error">
              <DeleteIcon sx={{ fontSize: 14 }} />
            </IconButton>
          </Box>
        ))}
        {field.description && <Typography variant="caption" color="text.secondary">{field.description}</Typography>}
      </Box>
    );
  }

  if (field.type === 'object' && field.fields) {
    const obj = typeof value === 'object' && value ? value : {};
    return (
      <Accordion disableGutters sx={{ my: 0.5 }}>
        <AccordionSummary expandIcon={<ExpandMoreIcon />}>
          <Typography variant="body2" sx={{ fontWeight: 600 }}>{field.label}</Typography>
        </AccordionSummary>
        <AccordionDetails>
          {field.fields.map((subField) => (
            <FieldRenderer
              key={subField.name} field={subField} value={obj[subField.name]}
              onChange={(name, val) => handleChange({ ...obj, [name]: val })}
              tree={tree} currentOrg={currentOrg}
            />
          ))}
        </AccordionDetails>
      </Accordion>
    );
  }

  return (
    <TextField
      fullWidth label={field.label} value={value ?? field.default ?? ''}
      onChange={(e) => handleChange(e.target.value)}
      helperText={field.description} margin="dense" required={field.required}
    />
  );
}


function BiosSectionGroup({ section, formData, onFieldChange, search, tree, currentOrg }) {
  const filtered = search
    ? section.fields.filter((f) =>
        f.name.toLowerCase().includes(search.toLowerCase()) ||
        f.label.toLowerCase().includes(search.toLowerCase())
      )
    : section.fields;

  if (filtered.length === 0) return null;

  const modifiedCount = section.fields.filter(
    (f) => formData[f.name] !== undefined && formData[f.name] !== 'platform-default'
  ).length;

  return (
    <Accordion disableGutters TransitionProps={{ unmountOnExit: true }}>
      <AccordionSummary expandIcon={<ExpandMoreIcon />}>
        <Typography variant="body2" sx={{ fontWeight: 600, flex: 1 }}>
          {section.title} ({filtered.length})
        </Typography>
        {modifiedCount > 0 && (
          <Chip label={`${modifiedCount} set`} size="small" color="secondary" sx={{ mr: 1 }} />
        )}
      </AccordionSummary>
      <AccordionDetails sx={{ maxHeight: 400, overflow: 'auto' }}>
        {filtered.map((field) => (
          <FieldRenderer
            key={field.name} field={field} value={formData[field.name]}
            onChange={onFieldChange} tree={tree} currentOrg={currentOrg}
          />
        ))}
      </AccordionDetails>
    </Accordion>
  );
}


export default function ResourcePanel({ onClose, onSave, schema, initialData, org, category, resourceType, tree }) {
  const [formData, setFormData] = useState({});
  const [search, setSearch] = useState('');

  useEffect(() => {
    setFormData(initialData || {});
    setSearch('');
  }, [initialData, schema, org, category, resourceType]);

  const formStructure = useMemo(
    () => buildFormSections(schema, resourceType),
    [schema, resourceType]
  );

  if (!schema) return null;

  const handleFieldChange = (name, value) => {
    setFormData((prev) => {
      const updated = { ...prev };
      if (value === '' || value === undefined || value === null) {
        delete updated[name];
      } else {
        updated[name] = value;
      }
      return updated;
    });
  };

  const INTERSIGHT_NAME_RE = /^[a-zA-Z0-9_.:-]{1,64}$/;
  const nameValue = formData.name || '';
  const nameError = nameValue && !INTERSIGHT_NAME_RE.test(nameValue)
    ? 'Only letters, numbers, dots, underscores, colons, and hyphens allowed (no spaces). Max 64 chars.'
    : '';

  const handleSave = () => {
    if (nameError) return;
    onSave(formData);
  };

  const isEditing = !!initialData;

  return (
    <Box sx={{ display: 'flex', flexDirection: 'column', height: '100%' }}>
      {/* Header bar */}
      <Box sx={{
        display: 'flex', alignItems: 'center', gap: 1,
        px: 2.5, py: 1.5,
        borderBottom: '1px solid', borderColor: 'divider',
        bgcolor: 'background.paper',
      }}>
        <Box sx={{ flex: 1 }}>
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
            <Typography variant="subtitle1" sx={{ fontWeight: 700 }}>
              {isEditing ? 'Edit' : 'Create'} {schema.friendly_name}
            </Typography>
            {isEditing && initialData?.name && (
              <Chip label={initialData.name} size="small" color="primary" variant="outlined" />
            )}
          </Box>
          <Typography variant="caption" color="text.secondary">
            {org} / {category} / {resourceType}
          </Typography>
        </Box>
        <Button
          variant="contained" size="small"
          startIcon={<SaveIcon />}
          onClick={handleSave}
          disabled={!formData.name || !!nameError}
        >
          {isEditing ? 'Save' : 'Create'}
        </Button>
        <IconButton size="small" onClick={onClose}>
          <CloseIcon fontSize="small" />
        </IconButton>
      </Box>

      {/* Scrollable form body */}
      <Box sx={{ flex: 1, overflow: 'auto', px: 2.5, py: 2 }}>
        {formStructure.core.map((field) => {
          if (field.name === 'name' && nameError) {
            return (
              <TextField
                key="name" fullWidth label={field.label}
                value={formData.name ?? field.default ?? ''}
                onChange={(e) => handleFieldChange('name', e.target.value)}
                helperText={nameError}
                error
                margin="dense" required={field.required}
              />
            );
          }
          return (
            <FieldRenderer
              key={field.name} field={field} value={formData[field.name]}
              onChange={handleFieldChange} tree={tree} currentOrg={org}
            />
          );
        })}

        {formStructure.isBios && formStructure.sections.length > 0 && (
          <Box sx={{ mt: 2 }}>
            <Divider sx={{ mb: 1.5 }} />
            <TextField
              fullWidth placeholder="Search BIOS tokens..." size="small"
              value={search} onChange={(e) => setSearch(e.target.value)}
              slotProps={{
                input: {
                  startAdornment: (
                    <InputAdornment position="start">
                      <SearchIcon fontSize="small" />
                    </InputAdornment>
                  ),
                },
              }}
              sx={{ mb: 1 }}
            />
            {formStructure.sections.map((section) => (
              <BiosSectionGroup
                key={section.title} section={section}
                formData={formData} onFieldChange={handleFieldChange}
                search={search} tree={tree} currentOrg={org}
              />
            ))}
          </Box>
        )}

        {!formStructure.isBios && formStructure.sections.length > 0 && (
          <Box sx={{ mt: 2 }}>
            <Divider sx={{ mb: 1.5 }} />
            {formStructure.sections.map((section) => (
              <Accordion key={section.title} disableGutters sx={{ mt: 0.5 }} TransitionProps={{ unmountOnExit: true }}>
                <AccordionSummary expandIcon={<ExpandMoreIcon />}>
                  <Typography variant="body2" sx={{ fontWeight: 600 }}>
                    {section.title} ({section.fields.length})
                  </Typography>
                </AccordionSummary>
                <AccordionDetails>
                  {section.fields.map((field) => (
                    <FieldRenderer
                      key={field.name} field={field} value={formData[field.name]}
                      onChange={handleFieldChange} tree={tree} currentOrg={org}
                    />
                  ))}
                </AccordionDetails>
              </Accordion>
            ))}
          </Box>
        )}
      </Box>
    </Box>
  );
}
