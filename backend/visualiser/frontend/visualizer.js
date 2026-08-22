/**
 * D3-based collapsible tree visualizer for the Intersight hierarchy.
 */

class TreeVisualizer {
  constructor(containerSelector) {
    this.container = containerSelector ? document.querySelector(containerSelector) : null;
    this.root = null;
    this.treeLayout = null;
    this.svg = null;
    this.g = null;
    this.zoom = null;
    this.tooltip = null;
    this.idCounter = 0;
    this.nodeHeight = 26;
    this.depthSpacing = 240;
    this.duration = 350;
    this.onNodeClick = null;
    this._initTooltip();
  }

  _initTooltip() {
    this.tooltip = document.createElement('div');
    this.tooltip.className = 'tree-tooltip';
    this.tooltip.style.display = 'none';
    document.body.appendChild(this.tooltip);
  }

  render(data) {
    this.container.innerHTML = '';
    this.idCounter = 0;

    const w = this.container.clientWidth;
    const h = this.container.clientHeight;

    this.svg = d3.select(this.container).append('svg').attr('width', w).attr('height', h);
    this.g = this.svg.append('g').attr('transform', 'translate(60,0)');
    this.zoom = d3.zoom()
      .scaleExtent([0.05, 5])
      .filter((event) => {
        // Allow touch events (pinch zoom), drag-to-pan, and Ctrl/Cmd+wheel zoom
        if (event.type === 'wheel') return event.ctrlKey || event.metaKey;
        if (event.type === 'touchstart' || event.type === 'touchmove' || event.type === 'touchend') return true;
        return !event.button;
      })
      .on('zoom', (e) => this.g.attr('transform', e.transform));
    this.svg.call(this.zoom);

    // Scroll-to-pan: translate wheel delta into pan
    this.svg.on('wheel.pan', (event) => {
      if (event.ctrlKey || event.metaKey) return; // pinch zoom handled by d3
      event.preventDefault();
      const t = d3.zoomTransform(this.svg.node());
      const newT = t.translate(-event.deltaX / t.k, -event.deltaY / t.k);
      this.svg.call(this.zoom.transform, newT);
    }, { passive: false });

    this.root = d3.hierarchy(data);
    this.root.x0 = h / 2;
    this.root.y0 = 0;
    this._collapseBelow(this.root, 2);
    this.treeLayout = d3.tree().nodeSize([this.nodeHeight + 6, this.depthSpacing]);
    this._update(this.root);

    this.svg.call(this.zoom.transform, d3.zoomIdentity.translate(60, h / 2).scale(0.85));
  }

  _collapseBelow(node, maxDepth) {
    if (!node.children) return;
    if (node.depth >= maxDepth) {
      node._children = node.children;
      node.children = null;
      if (node._children) node._children.forEach(c => this._collapseBelow(c, maxDepth));
    } else {
      node.children.forEach(c => this._collapseBelow(c, maxDepth));
    }
  }

  _textWidth(text) { return Math.min(Math.max(text.length * 6.5 + 20, 80), 320); }
  _truncate(text, max) { return text.length > max ? text.substring(0, max - 1) + '…' : text; }

  _update(source) {
    const tree = this.treeLayout(this.root);
    const nodes = tree.descendants();
    const links = tree.descendants().slice(1);
    nodes.forEach(d => { d.y = d.depth * this.depthSpacing; });

    const tw = (d) => this._textWidth(d.data.name);

    // Nodes
    const sel = this.g.selectAll('g.node-group').data(nodes, d => d._vizId || (d._vizId = ++this.idCounter));

    const enter = sel.enter().append('g')
      .attr('class', d => {
        let cls = 'node-group';
        if (d.data.disjoint) cls += ' disjoint';
        if (d.data.severity) cls += ` severity-${d.data.severity}`;
        if (['vlan_list', 'policy', 'server_profile', 'pool'].includes(d.data.type)) cls += ' clickable';
        return cls;
      })
      .attr('transform', `translate(${source.y0},${source.x0})`)
      .on('click', (e, d) => this._handleClick(e, d))
      .on('mouseenter', (e, d) => this._showTooltip(e, d))
      .on('mousemove', (e) => this._moveTooltip(e))
      .on('mouseleave', () => this._hideTooltip());

    enter.append('rect').attr('class', 'node-rect').attr('y', -this.nodeHeight / 2)
      .attr('height', this.nodeHeight).attr('rx', 4)
      .attr('width', tw).attr('fill', d => d.data.colour || '#475569').attr('fill-opacity', 0.85)
      .attr('stroke', d => { const c = d3.color(d.data.colour || '#475569'); return c ? c.darker(0.5) : '#333'; })
      .attr('stroke-width', 1);

    enter.append('text').attr('class', 'node-label').attr('x', 8).text(d => this._truncate(d.data.name, 42));

    enter.append('text').attr('class', 'node-expand-indicator')
      .attr('x', d => tw(d) - 14)
      .text(d => d._children ? '+' : (d.children && d.children.length ? '−' : ''));

    const update = enter.merge(sel);
    update.attr('class', d => {
      let cls = 'node-group';
      if (d.data.disjoint) cls += ' disjoint';
      if (d.data.severity) cls += ` severity-${d.data.severity}`;
      return cls;
    });
    update.transition().duration(this.duration).attr('transform', d => `translate(${d.y},${d.x})`);
    update.select('.node-rect').attr('width', tw)
      .attr('fill', d => d.data.colour || '#475569')
      .attr('stroke', d => { const c = d3.color(d.data.colour || '#475569'); return c ? c.darker(0.5) : '#333'; });
    update.select('.node-label').text(d => this._truncate(d.data.name, 42));
    update.select('.node-expand-indicator').attr('x', d => tw(d) - 14)
      .text(d => d._children ? '+' : (d.children && d.children.length ? '−' : ''));

    const exit = sel.exit().transition().duration(this.duration)
      .attr('transform', `translate(${source.y},${source.x})`).remove();
    exit.select('rect').attr('width', 0);
    exit.select('text').style('fill-opacity', 0);

    // Links
    const linkSel = this.g.selectAll('path.link').data(links, d => d._vizId);
    const linkPath = (d, p) => {
      const sx = p.y + this._textWidth(p.data.name), sy = p.x, tx = d.y, ty = d.x, mx = (sx + tx) / 2;
      return `M${sx},${sy} C${mx},${sy} ${mx},${ty} ${tx},${ty}`;
    };
    const o0 = { x: source.x0, y: source.y0, data: source.data };

    linkSel.enter().insert('path', 'g').attr('class', 'link').attr('d', () => linkPath(o0, o0))
      .merge(linkSel).transition().duration(this.duration).attr('d', d => linkPath(d, d.parent));

    linkSel.exit().transition().duration(this.duration)
      .attr('d', () => { const o = { x: source.x, y: source.y, data: source.data }; return linkPath(o, o); }).remove();

    nodes.forEach(d => { d.x0 = d.x; d.y0 = d.y; });
  }

  _handleClick(event, d) {
    event.stopPropagation();
    const isLeaf = !d.children && !d._children;

    if ((d.data.severity || d.data.disjoint) && this.onNodeClick) {
      this.onNodeClick(d.data);
      if (!isLeaf) {
        if (d.children) { d._children = d.children; d.children = null; }
        else if (d._children) { d.children = d._children; d._children = null; }
        this._update(d);
      }
      return;
    }

    // VLAN list node: open detail panel, don't toggle
    if (d.data.type === 'vlan_list' && this.onNodeClick) { this.onNodeClick(d.data); return; }

    // Policy nodes: open detail panel AND toggle children
    if (d.data.type === 'policy' && d.data.description && this.onNodeClick) {
      this.onNodeClick(d.data);
    }
    // Nodes with description: open detail panel AND toggle children
    else if (d.data.description && this.onNodeClick && !d.data.moid) {
      this.onNodeClick(d.data);
    }

    if (isLeaf && d.data.moid && d.data.objectType && this.onNodeClick) { this.onNodeClick(d.data); return; }
    if (d.children) { d._children = d.children; d.children = null; }
    else if (d._children) { d.children = d._children; d._children = null; }
    this._update(d);
  }

  _showTooltip(event, d) {
    let html = `<div class="tt-type">${d.data.type.replace(/_/g, ' ')}</div>`;
    html += `<div class="tt-name">${this._esc(d.data.name)}</div>`;
    if (d.data.description) html += `<div class="tt-desc">${this._esc(d.data.description)}</div>`;
    if (d.data.assignedServer) html += `<div class="tt-desc">Server: ${this._esc(d.data.assignedServer)}</div>`;
    if (d.data.type === 'vlan_list') html += `<div class="tt-desc" style="color:#93c5fd">Click to view full VLAN list</div>`;
    if (d.data.disjoint) html += `<div class="tt-desc" style="color:#dc2626;font-weight:600">DISJOINT — exists on one fabric only</div>`;
    if (d.data.severity) html += `<div class="tt-desc" style="font-weight:600">Severity: ${d.data.severity.toUpperCase()}</div>`;
    const cc = (d.children || d._children || []).length;
    if (cc) html += `<div class="tt-desc">${cc} item${cc > 1 ? 's' : ''}</div>`;
    this.tooltip.innerHTML = html;
    this.tooltip.style.display = 'block';
    this._moveTooltip(event);
  }
  _moveTooltip(e) { this.tooltip.style.left = (e.pageX + 14) + 'px'; this.tooltip.style.top = (e.pageY - 10) + 'px'; }
  _hideTooltip() { this.tooltip.style.display = 'none'; }
  _esc(s) { const el = document.createElement('span'); el.textContent = s || ''; return el.innerHTML; }

  expandAll() { this._walk(this.root, n => { if (n._children) { n.children = n._children; n._children = null; } }); this._update(this.root); }
  collapseAll() { if (this.root.children) this.root.children.forEach(c => this._walk(c, n => { if (n.children) { n._children = n.children; n.children = null; } })); this._update(this.root); }
  _walk(node, fn) { fn(node); (node.children || node._children || []).forEach(c => this._walk(c, fn)); }

  search(query) {
    if (!this.root) return 0;
    const q = (query || '').toLowerCase().trim();
    const all = this.g.selectAll('g.node-group');
    if (!q) { all.classed('search-match', false).classed('search-dim', false); return -1; }
    let n = 0;
    all.each(function (d) {
      const m = [d.data.name, d.data.objectType, d.data.description].join(' ').toLowerCase().includes(q);
      d3.select(this).classed('search-match', m).classed('search-dim', !m);
      if (m) n++;
    });
    return n;
  }

  getNodeCount() { if (!this.root) return 0; let c = 0; this.root.each(() => c++); return c; }

  fitToScreen() {
    if (!this.root || !this.svg) return;
    const b = this.g.node().getBBox(), w = this.container.clientWidth, h = this.container.clientHeight;
    const s = Math.min((w - 80) / (b.width || 1), (h - 80) / (b.height || 1), 1.5);
    const tx = w / 2 - (b.x + b.width / 2) * s, ty = h / 2 - (b.y + b.height / 2) * s;
    this.svg.transition().duration(500).call(this.zoom.transform, d3.zoomIdentity.translate(tx, ty).scale(s));
  }

  exportHTML(title) {
    if (!this.root || !this.treeLayout) return;

    this._walk(this.root, n => {
      if (n._children) { n.children = n._children; n._children = null; }
    });

    const tree = this.treeLayout(this.root);
    const nodes = tree.descendants();
    const links = tree.descendants().slice(1);
    nodes.forEach(d => { d.y = d.depth * this.depthSpacing; });

    const tw = (d) => this._textWidth(d.data.name);
    const linkPath = (d) => {
      const sx = d.parent.y + tw(d.parent), sy = d.parent.x, tx = d.y, ty = d.x, mx = (sx + tx) / 2;
      return `M${sx},${sy} C${mx},${sy} ${mx},${ty} ${tx},${ty}`;
    };

    const ns = 'http://www.w3.org/2000/svg';
    const svg = document.createElementNS(ns, 'svg');
    const g = document.createElementNS(ns, 'g');
    svg.appendChild(g);

    links.forEach(d => {
      const path = document.createElementNS(ns, 'path');
      path.setAttribute('class', 'link');
      path.setAttribute('d', linkPath(d));
      g.appendChild(path);
    });

    nodes.forEach(d => {
      const ng = document.createElementNS(ns, 'g');
      let cls = 'node-group';
      if (d.data.disjoint) cls += ' disjoint';
      if (d.data.severity) cls += ` severity-${d.data.severity}`;
      ng.setAttribute('class', cls);
      ng.setAttribute('transform', `translate(${d.y},${d.x})`);

      const w = tw(d);
      const rect = document.createElementNS(ns, 'rect');
      rect.setAttribute('class', 'node-rect');
      rect.setAttribute('y', -this.nodeHeight / 2);
      rect.setAttribute('height', this.nodeHeight);
      rect.setAttribute('rx', 4);
      rect.setAttribute('width', w);
      const col = d.data.colour || '#475569';
      rect.setAttribute('fill', col);
      rect.setAttribute('fill-opacity', '0.85');
      const darker = d3.color(col);
      rect.setAttribute('stroke', darker ? darker.darker(0.5) : '#333');
      rect.setAttribute('stroke-width', '1');
      ng.appendChild(rect);

      const label = document.createElementNS(ns, 'text');
      label.setAttribute('class', 'node-label');
      label.setAttribute('x', '8');
      label.textContent = this._truncate(d.data.name, 42);
      ng.appendChild(label);

      g.appendChild(ng);
    });

    document.body.appendChild(svg);
    const bbox = g.getBBox();
    document.body.removeChild(svg);

    const pad = 40;
    const svgW = bbox.width + pad * 2, svgH = bbox.height + pad * 2;
    svg.setAttribute('width', svgW);
    svg.setAttribute('height', svgH);
    svg.setAttribute('viewBox', `${bbox.x - pad} ${bbox.y - pad} ${svgW} ${svgH}`);
    svg.setAttribute('xmlns', ns);

    const svgStr = new XMLSerializer().serializeToString(svg);

    return `<!DOCTYPE html>
<html lang="en"><head><meta charset="UTF-8">
<title>${title || 'UCS View'}</title>
<style>
*{box-sizing:border-box;margin:0;padding:0}
body{background:#0f172a;color:#e2e8f0;font-family:'Segoe UI',system-ui,sans-serif;padding:20px}
h1{text-align:center;font-size:20px;margin-bottom:16px;color:#38bdf8}
.wrap{overflow:auto;border:1px solid #334155;border-radius:8px;background:#1e293b}
svg{display:block;margin:0 auto}
.node-label{font-size:11px;fill:#fff;dominant-baseline:central;font-family:'Segoe UI',system-ui,sans-serif}
.link{fill:none;stroke:#475569;stroke-width:1.2;stroke-opacity:.6}
.node-rect:hover{filter:brightness(1.25)}
.disjoint .node-rect{stroke:#dc2626;stroke-width:2.5;stroke-dasharray:6 3}
.severity-critical .node-rect{stroke:#dc2626;stroke-width:2.5}
.severity-major .node-rect{stroke:#f97316;stroke-width:2.5}
.severity-minor .node-rect{stroke:#eab308;stroke-width:2}
.severity-warning .node-rect{stroke:#64748b;stroke-width:2}
.footer{text-align:center;font-size:11px;color:#64748b;margin-top:12px}
@media print{body{background:#fff;color:#000}.wrap{border-color:#ccc;background:#fff}
.link{stroke:#999}.node-label{fill:#000}}
</style></head><body>
<h1>${title || 'UCS View'}</h1>
<div class="wrap">${svgStr}</div>
<div class="footer">Exported ${new Date().toLocaleString()} — Cisco Intersight Visualiser</div>
</body></html>`;
  }
}
