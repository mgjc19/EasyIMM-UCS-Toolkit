/**
 * Form Builder -- converts JSON schema field definitions into
 * structured form sections for the ResourceDialog to render.
 *
 * Handles grouping, ordering, and identifying special field types
 * (references, BIOS tokens, etc.)
 */

const CORE_FIELDS = new Set(['name', 'description', 'tags']);

const BIOS_CORE = new Set(['name', 'description', 'tags', 'bios_template']);

export function buildFormSections(schema, resourceType) {
  if (!schema || !schema.fields) return { core: [], sections: [] };

  if (resourceType === 'bios') {
    return buildBiosForm(schema);
  }

  const core = [];
  const references = [];
  const advanced = [];

  for (const field of schema.fields) {
    if (CORE_FIELDS.has(field.name) || field.required) {
      core.push(field);
    } else if (field.is_reference) {
      references.push(field);
    } else {
      advanced.push(field);
    }
  }

  const sections = [];
  if (references.length > 0) {
    sections.push({ title: 'Policy & Pool References', fields: references });
  }
  if (advanced.length > 0) {
    sections.push({ title: 'Advanced Settings', fields: advanced });
  }

  return { core, sections };
}

function buildBiosForm(schema) {
  const core = schema.fields.filter((f) => BIOS_CORE.has(f.name) || f.required);

  const groups = schema.bios_groups || {};
  const tokenFieldMap = new Map();
  for (const field of schema.fields) {
    if (!BIOS_CORE.has(field.name) && !field.required) {
      tokenFieldMap.set(field.name, field);
    }
  }

  const sections = [];
  const assigned = new Set();

  for (const [groupName, tokenNames] of Object.entries(groups)) {
    const fields = [];
    for (const name of tokenNames) {
      const field = tokenFieldMap.get(name);
      if (field) {
        fields.push(field);
        assigned.add(name);
      }
    }
    if (fields.length > 0) {
      sections.push({ title: groupName, fields });
    }
  }

  const ungrouped = [];
  for (const [name, field] of tokenFieldMap) {
    if (!assigned.has(name)) {
      ungrouped.push(field);
    }
  }
  if (ungrouped.length > 0) {
    sections.push({ title: 'Other', fields: ungrouped });
  }

  return { core, sections, isBios: true };
}

export function getResourceNames(tree, org, category, resourceType) {
  if (!tree || !org || !category || !resourceType) return [];
  const resources = tree[org]?.[category]?.[resourceType] || [];
  return resources.map((r) => r.name);
}

export function getAllResourceNamesForRef(tree, refType) {
  if (!tree || !refType) return [];
  const names = [];
  for (const [org, orgData] of Object.entries(tree)) {
    for (const category of ['pools', 'policies', 'profiles', 'templates']) {
      const catData = orgData?.[category] || {};
      const resources = catData[refType] || [];
      for (const r of resources) {
        names.push({ name: r.name, org, label: `${r.name} (${org})` });
      }
    }
  }
  return names;
}
