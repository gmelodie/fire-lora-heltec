'use strict';

// ---- Auth ----

const Auth = {
  getPassword() { return sessionStorage.getItem('apiPassword'); },
  setPassword(pw) { sessionStorage.setItem('apiPassword', pw); },
  clear() { sessionStorage.removeItem('apiPassword'); },
  headers() { return { 'X-API-Password': this.getPassword() }; },
};

function showLoginOverlay() {
  document.getElementById('login-overlay').classList.remove('hidden');
}

function hideLoginOverlay() {
  document.getElementById('login-overlay').classList.add('hidden');
}

// ---- API ----

async function apiFetch(path) {
  const res = await fetch(path, { headers: Auth.headers() });
  if (res.status === 401) {
    Auth.clear();
    showLoginOverlay();
    throw new Error('Unauthorized');
  }
  if (!res.ok) throw new Error(`API error ${res.status}`);
  return res.json();
}

// ---- Time helpers ----

function relativeTime(unixSec) {
  const diffSec = Math.floor(Date.now() / 1000) - unixSec;
  if (diffSec < 60) return 'just now';
  if (diffSec < 3600) return `${Math.floor(diffSec / 60)}m ago`;
  if (diffSec < 86400) return `${Math.floor(diffSec / 3600)}h ago`;
  return `${Math.floor(diffSec / 86400)}d ago`;
}

function toDatetimeLocal(unixSec) {
  const d = new Date(unixSec * 1000);
  return d.getFullYear() + '-' +
    String(d.getMonth() + 1).padStart(2, '0') + '-' +
    String(d.getDate()).padStart(2, '0') + 'T' +
    String(d.getHours()).padStart(2, '0') + ':' +
    String(d.getMinutes()).padStart(2, '0');
}

function formatTick(unixSec) {
  const d = new Date(unixSec * 1000);
  return d.toLocaleDateString([], { month: 'short', day: 'numeric' }) + ' ' +
         d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
}

// ---- Sensor cards ----

function buildSensorCard(r) {
  const card = document.createElement('div');
  card.className = 'sensor-card';
  if (r.battery >= 60) card.classList.add('batt-ok');
  else if (r.battery >= 20) card.classList.add('batt-warn');
  else card.classList.add('batt-low');

  const header = document.createElement('div');
  header.className = 'card-header';
  header.innerHTML = `Sensor ${r.sensor_id} <span>${relativeTime(r.timestamp)}</span>`;
  card.appendChild(header);

  const metrics = [
    ['Temperature',   r.temperature    != null ? `${r.temperature.toFixed(1)} °C` : '—'],
    ['Humidity',      r.humidity       != null ? `${r.humidity.toFixed(1)} %`     : '—'],
    ['Pressure',      r.pressure       != null ? `${r.pressure.toFixed(1)} hPa`   : '—'],
    ['Battery',       r.battery        != null ? `${r.battery} %`                 : '—'],
    ['Camera Batt',   r.camera_battery != null ? `${r.camera_battery} %`          : '—'],
    ['RSSI',          r.rssi           != null ? `${r.rssi} dBm`                  : '—'],
    ['Counter',       r.counter        != null ? `#${r.counter}`                  : '—'],
  ];

  for (const [label, value] of metrics) {
    const row = document.createElement('div');
    row.className = 'metric-row';
    row.innerHTML = `<span class="metric-label">${label}</span><span class="metric-value">${value}</span>`;
    card.appendChild(row);
  }

  return card;
}

async function refreshCurrentState() {
  const grid = document.getElementById('sensor-grid');
  try {
    const readings = await apiFetch('/readings/latest');
    grid.innerHTML = '';
    if (readings.length === 0) {
      grid.innerHTML = '<p class="placeholder">No sensor data yet.</p>';
      return;
    }
    readings.forEach(r => grid.appendChild(buildSensorCard(r)));
  } catch (err) {
    if (err.message !== 'Unauthorized') {
      grid.innerHTML = '<p class="placeholder">Failed to load sensor data.</p>';
    }
  }
}

// ---- Live graphs ----

const CHART_COLORS = [
  '#f97316', '#3b82f6', '#22c55e', '#a855f7',
  '#eab308', '#ec4899', '#14b8a6', '#f43f5e',
];

const METRICS = [
  { key: 'temperature',    label: 'Temperature (°C)' },
  { key: 'humidity',       label: 'Humidity (%)'      },
  { key: 'pressure',       label: 'Pressure (hPa)'    },
  { key: 'battery',        label: 'Battery (%)'       },
  { key: 'camera_battery', label: 'Camera Battery (%)'},
  { key: 'rssi',           label: 'RSSI (dBm)'        },
];

const PRESETS = { '1h': 3600, '6h': 21600, '24h': 86400, '7d': 604800 };

let activePreset = '24h';
const chartInstances = {};

function setActivePreset(key) {
  activePreset = key;
  document.querySelectorAll('.preset-btn').forEach(btn => {
    btn.classList.toggle('active', btn.dataset.preset === key);
  });
  const customRange = document.getElementById('custom-range');
  if (key === 'custom') {
    customRange.classList.remove('hidden');
  } else {
    customRange.classList.add('hidden');
    const now = Math.floor(Date.now() / 1000);
    document.getElementById('from-dt').value = toDatetimeLocal(now - PRESETS[key]);
    document.getElementById('to-dt').value   = toDatetimeLocal(now);
  }
}

function renderAllCharts(rows) {
  const grid = document.getElementById('charts-grid');
  grid.innerHTML = '';

  for (const key of Object.keys(chartInstances)) {
    chartInstances[key].destroy();
    delete chartInstances[key];
  }

  const groups = {};
  for (const r of rows) {
    (groups[r.sensor_id] = groups[r.sensor_id] || []).push(r);
  }
  const sensorIds = Object.keys(groups).sort();

  for (const { key, label } of METRICS) {
    const tile = document.createElement('div');
    tile.className = 'chart-tile';

    const titleEl = document.createElement('div');
    titleEl.className = 'chart-tile-title';
    titleEl.textContent = label;
    tile.appendChild(titleEl);

    const canvas = document.createElement('canvas');
    tile.appendChild(canvas);
    grid.appendChild(tile);

    const datasets = sensorIds.map((id, i) => {
      const pts = groups[id];
      const color = CHART_COLORS[i % CHART_COLORS.length];
      return {
        label: `Sensor ${id}`,
        data: pts.map(r => ({ x: r.timestamp * 1000, y: r[key] })),
        borderColor: color,
        backgroundColor: color + '18',
        borderWidth: 1.5,
        tension: 0.2,
        pointRadius: pts.length > 100 ? 0 : 2,
        pointHoverRadius: 4,
      };
    });

    chartInstances[key] = new Chart(canvas.getContext('2d'), {
      type: 'line',
      data: { datasets },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        interaction: { mode: 'nearest', axis: 'x', intersect: false },
        plugins: {
          legend: {
            display: sensorIds.length > 1,
            labels: { color: '#e6edf3', boxWidth: 10, font: { size: 10 } },
          },
          tooltip: {
            backgroundColor: '#161b22',
            borderColor: '#30363d',
            borderWidth: 1,
            titleColor: '#e6edf3',
            bodyColor: '#8b949e',
            callbacks: { title: items => formatTick(items[0].parsed.x / 1000) },
          },
        },
        scales: {
          x: {
            type: 'linear',
            ticks: {
              color: '#8b949e',
              maxTicksLimit: 6,
              maxRotation: 0,
              font: { size: 10 },
              callback: val => formatTick(val / 1000),
            },
            grid: { color: '#30363d' },
          },
          y: {
            ticks: { color: '#8b949e', font: { size: 10 } },
            grid: { color: '#30363d' },
          },
        },
      },
    });
  }
}

async function fetchAndRenderCharts() {
  const sensorId = document.getElementById('sensor-select').value;
  const fromDt   = document.getElementById('from-dt').value;
  const toDt     = document.getElementById('to-dt').value;

  const grid = document.getElementById('charts-grid');
  grid.innerHTML = '<p class="placeholder" style="padding:1rem">Loading…</p>';

  const params = new URLSearchParams({ limit: 2000 });
  if (sensorId) params.set('sensor_id', sensorId);
  if (fromDt)   params.set('from_ts', Math.floor(new Date(fromDt).getTime() / 1000));
  if (toDt)     params.set('to_ts',   Math.floor(new Date(toDt).getTime()   / 1000));

  let rows;
  try {
    rows = await apiFetch(`/readings?${params}`);
  } catch (err) {
    if (err.message !== 'Unauthorized') {
      grid.innerHTML = '<p class="placeholder" style="padding:1rem">Failed to load data.</p>';
    }
    return;
  }

  if (rows.length === 0) {
    grid.innerHTML = '<p class="placeholder" style="padding:1rem">No data in the selected range.</p>';
    return;
  }

  renderAllCharts(rows);
}

// ---- Auto-refresh ----

let refreshCountdown = 30;

function startAutoRefresh() {
  refreshCurrentState();
  fetchAndRenderCharts();
  setInterval(() => {
    refreshCountdown--;
    document.getElementById('refresh-countdown').textContent = refreshCountdown;
    if (refreshCountdown <= 0) {
      refreshCountdown = 30;
      if (activePreset !== 'custom') {
        const now = Math.floor(Date.now() / 1000);
        document.getElementById('from-dt').value = toDatetimeLocal(now - PRESETS[activePreset]);
        document.getElementById('to-dt').value   = toDatetimeLocal(now);
      }
      refreshCurrentState();
      fetchAndRenderCharts();
    }
  }, 1000);
}

// ---- Sensor dropdown ----

async function populateSensorDropdown() {
  try {
    const data = await apiFetch('/sensors');
    const sel = document.getElementById('sensor-select');
    data.sensors.forEach(id => {
      const opt = document.createElement('option');
      opt.value = opt.textContent = id;
      sel.appendChild(opt);
    });
  } catch (_) { /* handled by apiFetch */ }
}

// ---- Controls wiring ----

function wireControls() {
  document.getElementById('sensor-select').addEventListener('change', fetchAndRenderCharts);
  document.getElementById('apply-custom-btn').addEventListener('click', fetchAndRenderCharts);
  document.querySelectorAll('.preset-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      setActivePreset(btn.dataset.preset);
      if (btn.dataset.preset !== 'custom') fetchAndRenderCharts();
    });
  });
}

// ---- Init ----

async function initDashboard() {
  await populateSensorDropdown();
  setActivePreset('24h');
  wireControls();
  startAutoRefresh();
}

async function handleLogin() {
  const pw = document.getElementById('login-password').value.trim();
  if (!pw) return;
  Auth.setPassword(pw);
  try {
    await apiFetch('/readings/latest');
    hideLoginOverlay();
    await initDashboard();
  } catch (err) {
    if (err.message === 'Unauthorized') {
      document.getElementById('login-error').classList.remove('hidden');
    }
  }
}

document.addEventListener('DOMContentLoaded', async () => {
  document.getElementById('login-btn').addEventListener('click', handleLogin);
  document.getElementById('login-password').addEventListener('keydown', e => {
    if (e.key === 'Enter') handleLogin();
  });

  if (!Auth.getPassword()) {
    showLoginOverlay();
    return;
  }

  hideLoginOverlay();
  await initDashboard();
});
