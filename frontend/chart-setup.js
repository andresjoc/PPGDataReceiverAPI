// chart-setup.js
export let charts = {};
// COLORS will be populated from CSS custom properties at runtime so colors
// can be themed from `index.css`. We keep fallbacks when CSS variables
// are not available.
export let COLORS = [];
function cssVar(name, fallback) {
  try {
    if (typeof window !== 'undefined' && window.getComputedStyle) {
      const v = getComputedStyle(document.documentElement).getPropertyValue(name);
      return (v || '').trim() || fallback;
    }
  } catch (err) {
    // ignore and fallback
  }
  return fallback;
}
function readChartColors() {
  COLORS = [
    cssVar('--line-ir', '#ffffff'),
    cssVar('--line-red', '#ff0000'),
    cssVar('--line-green', '#00ff00'),
  ];
}
export const MAX_POINTS = 500;

function defaultConfig(label, color) {
  return {
    type: 'line',
    data: { datasets: [{ label, data: [] }] },
    options: {
      animation: false,
      parsing: false,
      plugins: { legend: { display: false }, title: { display: true, text: label } },
      scales: {
        x: {
          type: 'linear',
          title: { display: true, text: 'Segundos desde carga' },
          bounds: 'data',
          ticks: { maxTicksLimit: 8, callback: function(tickValue){ const n = (typeof tickValue === 'object' && tickValue !== null && tickValue.value !== undefined) ? Number(tickValue.value) : Number(tickValue); if (Number.isNaN(n)) return ''; return Math.round(n) + 's'; } },
          grid: { color: 'rgba(0,0,0,0.04)' }
        },
        y: {
          title: { display: true, text: 'Valor' },
          grid: { color: 'rgba(0,0,0,0.03)' }
        }
      },
      elements: { line: { tension: 0 } },
      maintainAspectRatio: false
    }
  };
}

function colorFor(colName) {
  const c = (colName || '').toString().trim().toUpperCase();
  if (c === 'IR') return cssVar('--line-ir', COLORS[0] || '#ffffff');
  if (c === 'RED') return cssVar('--line-red', COLORS[1] || '#ff0000');
  if (c === 'GREEN') return cssVar('--line-green', COLORS[2] || '#00ff00');
  return COLORS[0] || '#888';
}

export function initCharts(mapping) {
  // mapping: {RED: 'chart-red', IR: 'chart-ir', GREEN: 'chart-green'} or undefined
  readChartColors();
  const map = mapping || { RED: 'chart-red', IR: 'chart-ir', GREEN: 'chart-green' };
  for (const key of Object.keys(map)) {
    try {
      const canvas = document.getElementById(map[key]);
      if (!canvas) continue;
      const ctx = canvas.getContext('2d');
      const color = colorFor(key);
      const cfg = defaultConfig(key, color);
      // set dataset color
      cfg.data.datasets[0].borderColor = color;
      cfg.data.datasets[0].backgroundColor = color;
      cfg.data.datasets[0].pointRadius = 0;
      cfg.data.datasets[0].borderWidth = 1;
      charts[key.toUpperCase()] = new Chart(ctx, cfg);
    } catch (err) {
      console.warn('Could not init chart for', key, err);
    }
  }
  return charts;
}

export function ensureChartsForColumns(columns) {
  if (!columns || !Array.isArray(columns)) return;
  if (!COLORS || COLORS.length === 0) readChartColors();
  for (const col of columns) {
    const name = (col || '').toString().trim().toUpperCase();
    if (!name) continue;
    if (!charts[name]) {
      // attempt to initialize with default id mapping
      const defaultId = name === 'IR' ? 'chart-ir' : name === 'RED' ? 'chart-red' : name === 'GREEN' ? 'chart-green' : null;
      if (defaultId) {
        try {
          const canvas = document.getElementById(defaultId);
          if (canvas) {
            const ctx = canvas.getContext('2d');
            const color = colorFor(name);
            const cfg = defaultConfig(name, color);
            cfg.data.datasets[0].borderColor = color;
            cfg.data.datasets[0].backgroundColor = color;
            cfg.data.datasets[0].pointRadius = 0;
            cfg.data.datasets[0].borderWidth = 1;
            charts[name] = new Chart(ctx, cfg);
          }
        } catch (err) {
          console.warn('Could not lazy-init chart for', name, err);
        }
      }
    }
  }
  updateLegend();
}

function updateLegend() {
  try {
    const root = document.getElementById('legend');
    if (!root) return;
    root.innerHTML = '';
    for (const name of Object.keys(charts)) {
      const ch = charts[name];
      if (!ch || !ch.data || !ch.data.datasets || ch.data.datasets.length === 0) continue;
      const ds = ch.data.datasets[0];
      const item = document.createElement('div');
      item.className = 'item';
      const box = document.createElement('div');
      box.className = 'color-box';
      box.style.background = ds.borderColor || colorFor(name);
      box.style.border = '1px solid rgba(0,0,0,0.06)';
      item.appendChild(box);
      const label = document.createElement('div');
      label.textContent = ds.label || name;
      label.style.fontSize = '0.85rem';
      label.style.color = 'var(--muted)';
      item.appendChild(label);
      root.appendChild(item);
    }
  } catch (err) {
    console.warn('Could not update legend:', err);
  }
}

export function appendBatch(timestampsSec, columns, columnsData) {
  if (!columns || !Array.isArray(columns)) return;
  for (let i = 0; i < columns.length; i++) {
    const name = (columns[i] || '').toString().trim().toUpperCase();
    const ch = charts[name];
    if (!ch) continue;
    const pts = (columnsData[i] || []).map((v, idx) => ({ x: timestampsSec[idx], y: v }));
    if (!ch.data.datasets || ch.data.datasets.length === 0) ch.data.datasets = [{ label: name, data: [] }];
    ch.data.datasets[0].data = ch.data.datasets[0].data.concat(pts);
    // Trim per-chart
    const len = ch.data.datasets[0].data.length;
    if (len > MAX_POINTS) {
      const excess = len - MAX_POINTS;
      ch.data.datasets[0].data.splice(0, excess);
    }
    adjustYRangeForChart(ch);
    adjustXRangeForChart(ch);
    try { ch.update(); } catch (err) { console.warn('Chart update failed for', name, err); }
  }
}

export function adjustYRangeForChart(ch) {
  if (!ch || !ch.data || !ch.data.datasets) return;
  let globalMin = Infinity, globalMax = -Infinity;
  for (const ds of ch.data.datasets) {
    for (const p of ds.data) {
      if (p.y < globalMin) globalMin = p.y;
      if (p.y > globalMax) globalMax = p.y;
    }
  }
  if (!isFinite(globalMin) || !isFinite(globalMax)) return;
  if (globalMax === globalMin) { globalMax += 1; globalMin -= 1; }
  const range = globalMax - globalMin;
  const pad = range * 0.06;
  ch.options.scales.y.min = globalMin - pad;
  ch.options.scales.y.max = globalMax + pad;
}

export function adjustXRangeForChart(ch) {
  if (!ch || !ch.data || !ch.data.datasets) return;
  let minX = Infinity, maxX = -Infinity;
  for (const ds of ch.data.datasets) {
    for (const p of ds.data) {
      if (p.x < minX) minX = p.x;
      if (p.x > maxX) maxX = p.x;
    }
  }
  if (!isFinite(minX) || !isFinite(maxX)) return;
  if (minX === maxX) { minX -= 1; maxX += 1; }
  const step = 2;
  const minRounded = Math.floor(minX / step) * step;
  const maxRounded = Math.ceil(maxX / step) * step;
  ch.options.scales.x.min = minRounded;
  ch.options.scales.x.max = maxRounded;
  const range = maxRounded - minRounded;
  try {
    if (ch.options && ch.options.scales && ch.options.scales.x && ch.options.scales.x.ticks) {
      ch.options.scales.x.ticks.stepSize = range < step ? Math.max(range / 4, 0.1) : step;
    }
  } catch (err) {
    console.warn('Could not set x.ticks.stepSize for chart:', err);
  }
}
