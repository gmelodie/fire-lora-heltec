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

// ---- Relative time ----

function relativeTime(unixSec) {
  const diffSec = Math.floor(Date.now() / 1000) - unixSec;
  if (diffSec < 60) return 'just now';
  if (diffSec < 3600) return `${Math.floor(diffSec / 60)}m ago`;
  if (diffSec < 86400) return `${Math.floor(diffSec / 3600)}h ago`;
  return `${Math.floor(diffSec / 86400)}d ago`;
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
    ['Temperature', r.temperature != null ? `${r.temperature.toFixed(1)} °C` : '—'],
    ['Humidity',    r.humidity    != null ? `${r.humidity.toFixed(1)} %`    : '—'],
    ['Pressure',    r.pressure    != null ? `${r.pressure.toFixed(1)} hPa`  : '—'],
    ['Battery',     r.battery     != null ? `${r.battery} %`                : '—'],
    ['RSSI',        r.rssi        != null ? `${r.rssi} dBm`                 : '—'],
    ['Counter',     r.counter     != null ? `#${r.counter}`                 : '—'],
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

// ---- Auto-refresh ----

let refreshCountdown = 30;

function startAutoRefresh() {
  refreshCurrentState();
  setInterval(() => {
    refreshCountdown--;
    document.getElementById('refresh-countdown').textContent = refreshCountdown;
    if (refreshCountdown <= 0) {
      refreshCountdown = 30;
      refreshCurrentState();
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

// ---- History chart ----

let chartInstance = null;

const metricLabels = {
  temperature: 'Temperature (°C)',
  humidity:    'Humidity (%)',
  pressure:    'Pressure (hPa)',
  battery:     'Battery (%)',
  rssi:        'RSSI (dBm)',
};

async function searchHistory() {
  const sensorId = document.getElementById('sensor-select').value;
  const metric   = document.getElementById('metric-select').value;
  const fromDt   = document.getElementById('from-dt').value;
  const toDt     = document.getElementById('to-dt').value;

  if (!sensorId) return;

  const params = new URLSearchParams({ sensor_id: sensorId, limit: 500 });
  if (fromDt) params.set('from_ts', Math.floor(new Date(fromDt).getTime() / 1000));
  if (toDt)   params.set('to_ts',   Math.floor(new Date(toDt).getTime()   / 1000));

  const placeholder = document.getElementById('chart-placeholder');
  placeholder.textContent = 'Loading…';
  placeholder.classList.remove('hidden');

  let rows;
  try {
    rows = await apiFetch(`/readings?${params}`);
  } catch (err) {
    if (err.message !== 'Unauthorized') {
      placeholder.textContent = 'Failed to load data.';
    }
    return;
  }

  placeholder.classList.add('hidden');

  if (rows.length === 0) {
    if (chartInstance) { chartInstance.destroy(); chartInstance = null; }
    placeholder.textContent = 'No data found for the selected range.';
    placeholder.classList.remove('hidden');
    return;
  }

  const labels = rows.map(r => {
    const d = new Date(r.timestamp * 1000);
    return d.toLocaleDateString([], { month: 'short', day: 'numeric' }) + ' ' +
           d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
  });
  const values = rows.map(r => r[metric]);

  if (chartInstance) chartInstance.destroy();

  const ctx = document.getElementById('history-chart').getContext('2d');
  chartInstance = new Chart(ctx, {
    type: 'line',
    data: {
      labels,
      datasets: [{
        label: metricLabels[metric] || metric,
        data: values,
        borderColor: '#f97316',
        backgroundColor: 'rgba(249,115,22,0.08)',
        borderWidth: 2,
        tension: 0.2,
        pointRadius: rows.length > 200 ? 0 : 3,
        pointHoverRadius: 4,
      }]
    },
    options: {
      responsive: true,
      interaction: { mode: 'index', intersect: false },
      plugins: {
        legend: { labels: { color: '#e6edf3' } },
        tooltip: { backgroundColor: '#161b22', borderColor: '#30363d', borderWidth: 1 },
      },
      scales: {
        x: {
          ticks: { color: '#8b949e', maxTicksLimit: 10, maxRotation: 0 },
          grid:  { color: '#30363d' },
        },
        y: {
          ticks: { color: '#8b949e' },
          grid:  { color: '#30363d' },
        },
      },
    },
  });
}

// ---- Login flow ----

async function handleLogin() {
  const pw = document.getElementById('login-password').value.trim();
  if (!pw) return;

  Auth.setPassword(pw);
  try {
    await apiFetch('/readings/latest');
    hideLoginOverlay();
    await Promise.all([populateSensorDropdown(), startAutoRefresh()]);
    document.getElementById('search-btn').addEventListener('click', searchHistory);
  } catch (err) {
    if (err.message === 'Unauthorized') {
      document.getElementById('login-error').classList.remove('hidden');
    }
  }
}

// ---- Init ----

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
  await Promise.all([populateSensorDropdown(), startAutoRefresh()]);
  document.getElementById('search-btn').addEventListener('click', searchHistory);
});
