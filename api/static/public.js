'use strict';

let CONFIG = null;

async function loadDeployments() {
  const res = await fetch('/static/deployments.json');
  if (!res.ok) throw new Error(`deployments.json ${res.status}`);
  return res.json();
}

async function getJSON(path) {
  const res = await fetch(path);
  if (!res.ok) throw new Error(`API error ${res.status}`);
  return res.json();
}

function shifted(ts) {
  return new Date((ts + CONFIG.timezone.utc_offset_hours * 3600) * 1000);
}

const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
                'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];

function fmtLocal(ts) {
  const d = shifted(ts);
  const hh = String(d.getUTCHours()).padStart(2, '0');
  const mm = String(d.getUTCMinutes()).padStart(2, '0');
  return `${d.getUTCDate()} ${MONTHS[d.getUTCMonth()]} ${d.getUTCFullYear()}, ${hh}:${mm} ${CONFIG.timezone.label.split(' ')[0]}`;
}

function fmtLocalShort(ts) {
  const d = shifted(ts);
  return `${d.getUTCDate()} ${MONTHS[d.getUTCMonth()]}`;
}

function relativeTime(ts) {
  const diff = Math.floor(Date.now() / 1000) - ts;
  if (diff < 60) return 'just now';
  if (diff < 3600) return `${Math.floor(diff / 60)} min ago`;
  if (diff < 86400) return `${Math.floor(diff / 3600)} h ago`;
  return `${Math.floor(diff / 86400)} days ago`;
}

function allRuns() {
  return CONFIG.campaigns.flatMap(c => c.runs);
}

function runsBySensorId() {
  const table = {};
  for (const run of allRuns()) {
    for (const id of run.sensor_ids) {
      if (!table[id] || table[id].end_utc < run.end_utc) table[id] = run;
    }
  }
  return table;
}

function coordsOf(run) {
  const p = CONFIG.positions[run.position];
  return [p.lat, p.lon];
}

function makeTiles() {
  return L.tileLayer(CONFIG.map.tile_url, {
    maxZoom: CONFIG.map.max_zoom,
    maxNativeZoom: CONFIG.map.max_zoom,
    attribution: CONFIG.map.attribution,
  });
}

function siteBounds() {
  const points = [[CONFIG.gateway.lat, CONFIG.gateway.lon],
                  [CONFIG.station.lat, CONFIG.station.lon]];
  for (const p of Object.values(CONFIG.positions)) points.push([p.lat, p.lon]);
  return L.latLngBounds(points).pad(0.25);
}

function newMap(elementId) {
  const map = L.map(elementId, { scrollWheelZoom: false });
  makeTiles().addTo(map);
  map.fitBounds(siteBounds(), { maxZoom: CONFIG.map.max_zoom });
  return map;
}

function addFixedPoints(map) {
  const gateway = L.marker([CONFIG.gateway.lat, CONFIG.gateway.lon], {
    icon: L.divIcon({ className: '', html: '<div class="gateway-pin"></div>', iconSize: [14, 14], iconAnchor: [7, 7] }),
  }).addTo(map);
  gateway.bindTooltip('Gateway', { permanent: true, direction: 'right', className: 'node-label', offset: [10, 0] });

  const station = L.marker([CONFIG.station.lat, CONFIG.station.lon], {
    icon: L.divIcon({ className: '', html: '<div class="station-pin"></div>', iconSize: [12, 12], iconAnchor: [6, 6] }),
  }).addTo(map);
  station.bindTooltip(CONFIG.station.name, { permanent: true, direction: 'right', className: 'node-label', offset: [10, 0] });
}

function nodeMarker(run, map) {
  const marker = L.circleMarker(coordsOf(run), {
    radius: 9, weight: 2, color: '#ffffff', fillColor: '#6f6753', fillOpacity: 0.35,
  }).addTo(map);
  marker.bindTooltip(run.node, { permanent: true, direction: 'right', className: 'node-label', offset: [10, 0] });
  return marker;
}

const STATE_STYLE = {
  fresh:   { color: '#ffffff', fillColor: '#3e8a2e', fillOpacity: 0.95, weight: 2 },
  recent:  { color: '#ffffff', fillColor: '#b5820a', fillOpacity: 0.95, weight: 2 },
  offline: { color: '#6f6753', fillColor: '#6f6753', fillOpacity: 0.15, weight: 2 },
  faulty:  { color: '#ffffff', fillColor: '#5b6572', fillOpacity: 0.95, weight: 2 },
};

function fieldLine(run, reading, key, unit, decimals) {
  const value = reading[key];
  if (!run.valid[key]) return [labelOf(key), 'sensor fault'];
  if (value === null || value === undefined) return [labelOf(key), '—'];
  return [labelOf(key), `${value.toFixed(decimals)} ${unit}`];
}

function labelOf(key) {
  return { temperature: 'Temperature', humidity: 'Humidity', pressure: 'Pressure' }[key];
}

function popupHTML(run, reading, extraRows) {
  const p = CONFIG.positions[run.position];
  const rows = [
    fieldLine(run, reading, 'temperature', '°C', 1),
    fieldLine(run, reading, 'humidity', '%', 1),
    fieldLine(run, reading, 'pressure', 'hPa', 1),
    ['Battery', reading.battery != null ? `${reading.battery} %` : '—'],
    ['Signal', `${reading.rssi} dBm`],
    ['Packet', `#${reading.counter}`],
  ].concat(extraRows || []);

  const dl = rows.map(([k, v]) => `<dt>${k}</dt><dd>${v}</dd>`).join('');
  const note = run.note ? `<p class="popup-note">${run.note}</p>` : '';
  return `<div class="popup"><h3>${run.node}</h3>` +
         `<p class="popup-sub">Position ${run.position}, ${p.distance_m} m from the gateway · sensor id ${reading.sensor_id}</p>` +
         `<dl>${dl}</dl>${note}</div>`;
}

let liveMap = null;
const liveMarkers = {};

function initLiveMap() {
  liveMap = newMap('live-map');
  addFixedPoints(liveMap);
  for (const run of allRuns()) {
    liveMarkers[run.node] = { run, marker: nodeMarker(run, liveMap) };
  }
}

function newestPerNode(rows) {
  const index = runsBySensorId();
  const best = {};
  const unknown = {};
  for (const row of rows) {
    const run = index[row.sensor_id];
    if (!run) {
      if (!unknown[row.sensor_id] || unknown[row.sensor_id].timestamp < row.timestamp) unknown[row.sensor_id] = row;
      continue;
    }
    if (!best[run.node] || best[run.node].timestamp < row.timestamp) best[run.node] = row;
  }
  return { best, unknown };
}

function liveState(run, reading) {
  if (!reading) return 'offline';
  const age = Math.floor(Date.now() / 1000) - reading.timestamp;
  if (age <= 2 * run.interval_min * 60) return 'fresh';
  if (age <= 86400) return 'recent';
  return 'offline';
}

function renderUnknown(unknown) {
  const el = document.getElementById('live-unknown');
  const ids = Object.keys(unknown);
  if (ids.length === 0) {
    el.classList.add('hidden');
    return;
  }
  const parts = ids.map(id => `id ${id} (${relativeTime(unknown[id].timestamp)})`);
  el.textContent = `Other sensors reporting, not yet mapped to a node: ${parts.join(', ')}.`;
  el.classList.remove('hidden');
}

async function refreshLive() {
  const status = document.getElementById('live-status');
  let rows;
  try {
    rows = await getJSON('/readings/latest');
  } catch (_) {
    status.textContent = 'The API did not answer. The markers below hold the last state that loaded.';
    return;
  }

  const { best, unknown } = newestPerNode(rows);
  let reporting = 0;

  for (const { run, marker } of Object.values(liveMarkers)) {
    const reading = best[run.node];
    const state = liveState(run, reading);
    if (state !== 'offline') reporting++;
    marker.setStyle(STATE_STYLE[state]);
    marker.bindPopup(reading
      ? popupHTML(run, reading, [['Last seen', `${fmtLocal(reading.timestamp)} (${relativeTime(reading.timestamp)})`]])
      : `<div class="popup"><h3>${run.node}</h3><p class="popup-sub">Position ${run.position} · no reading on record</p></div>`);
  }

  const now = Math.floor(Date.now() / 1000);
  status.textContent = `Updated ${fmtLocal(now)} · ${Object.keys(liveMarkers).length} nodes deployed, ` +
                       `${reporting} reporting in the last 24 h.`;
  renderUnknown(unknown);
}

const TEMP_STOPS = [
  [5,  [253, 227, 200]],
  [15, [246, 178, 107]],
  [25, [224, 138, 52]],
  [35, [180, 83, 9]],
  [45, [124, 58, 8]],
];

function tempColor(value) {
  const v = Math.max(TEMP_STOPS[0][0], Math.min(TEMP_STOPS[TEMP_STOPS.length - 1][0], value));
  for (let i = 1; i < TEMP_STOPS.length; i++) {
    const [t0, c0] = TEMP_STOPS[i - 1];
    const [t1, c1] = TEMP_STOPS[i];
    if (v > t1) continue;
    const f = (v - t0) / (t1 - t0);
    const mix = c0.map((c, k) => Math.round(c + f * (c1[k] - c)));
    return `rgb(${mix.join(',')})`;
  }
  return `rgb(${TEMP_STOPS[TEMP_STOPS.length - 1][1].join(',')})`;
}

function nearestReading(rows, t, maxDelta) {
  if (rows.length === 0) return null;
  let lo = 0;
  let hi = rows.length - 1;
  while (lo < hi) {
    const mid = (lo + hi) >> 1;
    if (rows[mid].timestamp < t) lo = mid + 1;
    else hi = mid;
  }
  const candidates = [rows[lo], rows[lo - 1]].filter(Boolean);
  let best = null;
  for (const row of candidates) {
    if (!best || Math.abs(row.timestamp - t) < Math.abs(best.timestamp - t)) best = row;
  }
  return Math.abs(best.timestamp - t) <= maxDelta ? best : null;
}

const replay = {
  map: null,
  campaign: null,
  markers: {},
  cache: {},
  rows: {},
  timer: null,
};

async function fetchCampaignRows(campaign) {
  const ids = new Set(campaign.runs.flatMap(r => r.sensor_ids));
  const params = new URLSearchParams({ from_ts: campaign.start_utc, to_ts: campaign.end_utc, limit: 2000 });
  let rows = await getJSON(`/readings?${params}`);

  // A full page means the window was truncated; one query per sensor keeps every node complete.
  if (rows.length === 2000) {
    const perSensor = await Promise.all([...ids].map(id => {
      const q = new URLSearchParams({ sensor_id: id, from_ts: campaign.start_utc, to_ts: campaign.end_utc, limit: 2000 });
      return getJSON(`/readings?${q}`);
    }));
    rows = perSensor.flat();
  }

  const byNode = {};
  const index = runsBySensorId();
  for (const row of rows) {
    if (!ids.has(row.sensor_id)) continue;
    const node = index[row.sensor_id].node;
    (byNode[node] = byNode[node] || []).push(row);
  }
  for (const node of Object.keys(byNode)) byNode[node].sort((a, b) => a.timestamp - b.timestamp);
  return byNode;
}

function buildReplayMarkers(campaign) {
  for (const entry of Object.values(replay.markers)) {
    replay.map.removeLayer(entry.marker);
  }
  replay.markers = {};
  for (const run of campaign.runs) {
    replay.markers[run.node] = { run, marker: nodeMarker(run, replay.map) };
  }
}

function readoutRow(run, reading) {
  if (!reading) return `<tr><td>${run.node}</td><td class="stale" colspan="2">no packet near this time</td></tr>`;
  const temp = run.valid.temperature && reading.temperature != null
    ? `${reading.temperature.toFixed(1)} °C` : 'sensor fault';
  const rh = run.valid.humidity && reading.humidity != null
    ? `${reading.humidity.toFixed(1)} %` : '—';
  return `<tr><td>${run.node}</td><td>${temp}</td><td>${rh}, ${reading.battery ?? '—'} % battery, ${reading.rssi} dBm</td></tr>`;
}

function renderCursor(t) {
  document.getElementById('cursor-time').textContent = fmtLocal(t);
  const lines = [];

  for (const { run, marker } of Object.values(replay.markers)) {
    const rows = replay.rows[run.node] || [];
    const reading = nearestReading(rows, t, 2 * run.interval_min * 60);
    lines.push(readoutRow(run, reading));

    if (!reading) {
      marker.setStyle(STATE_STYLE.offline);
      marker.unbindPopup();
      continue;
    }
    if (run.valid.temperature && reading.temperature != null) {
      marker.setStyle({ color: '#ffffff', weight: 2, fillColor: tempColor(reading.temperature), fillOpacity: 0.95 });
    } else {
      marker.setStyle(STATE_STYLE.faulty);
    }
    marker.bindPopup(popupHTML(run, reading, [['Sent', fmtLocal(reading.timestamp)]]));
  }

  document.getElementById('cursor-readout').innerHTML =
    `<table><tr><th>Node</th><th>Temperature</th><th>Other fields</th></tr>${lines.join('')}</table>`;
}

function stopPlayback() {
  if (replay.timer === null) return;
  clearInterval(replay.timer);
  replay.timer = null;
  document.getElementById('play-btn').innerHTML = '&#9654; Play';
}

function startPlayback() {
  const scrubber = document.getElementById('scrubber');
  const step = Math.max(60, Math.round((replay.campaign.end_utc - replay.campaign.start_utc) / 450));
  if (Number(scrubber.value) >= Number(scrubber.max)) scrubber.value = scrubber.min;
  document.getElementById('play-btn').innerHTML = '&#10073;&#10073; Pause';
  replay.timer = setInterval(() => {
    const next = Number(scrubber.value) + step;
    if (next >= Number(scrubber.max)) {
      scrubber.value = scrubber.max;
      renderCursor(Number(scrubber.value));
      stopPlayback();
      return;
    }
    scrubber.value = next;
    renderCursor(next);
  }, 100);
}

async function selectCampaign(campaign) {
  stopPlayback();
  replay.campaign = campaign;

  document.querySelectorAll('#campaign-picker button').forEach(btn => {
    btn.classList.toggle('active', btn.dataset.campaign === campaign.id);
  });
  document.getElementById('campaign-summary').textContent = campaign.summary;

  buildReplayMarkers(campaign);

  const scrubber = document.getElementById('scrubber');
  scrubber.min = campaign.start_utc;
  scrubber.max = campaign.end_utc;
  scrubber.value = campaign.start_utc;
  document.getElementById('cursor-time').textContent = fmtLocal(campaign.start_utc);

  if (!replay.cache[campaign.id]) {
    document.getElementById('cursor-readout').innerHTML = '<p class="placeholder">Loading the campaign&hellip;</p>';
    try {
      replay.cache[campaign.id] = await fetchCampaignRows(campaign);
    } catch (_) {
      document.getElementById('cursor-readout').innerHTML = '<p class="placeholder">The API did not answer.</p>';
      return;
    }
  }
  replay.rows = replay.cache[campaign.id];
  renderCursor(campaign.start_utc);
}

function initReplay() {
  replay.map = newMap('replay-map');
  addFixedPoints(replay.map);

  const picker = document.getElementById('campaign-picker');
  for (const campaign of CONFIG.campaigns) {
    const btn = document.createElement('button');
    btn.className = 'btn-quiet';
    btn.dataset.campaign = campaign.id;
    btn.textContent = `${campaign.id} · ${fmtLocalShort(campaign.start_utc)} to ${fmtLocalShort(campaign.end_utc)}`;
    btn.addEventListener('click', () => selectCampaign(campaign));
    picker.appendChild(btn);
  }

  const scrubber = document.getElementById('scrubber');
  scrubber.addEventListener('input', () => {
    stopPlayback();
    renderCursor(Number(scrubber.value));
  });
  document.getElementById('play-btn').addEventListener('click', () => {
    if (replay.timer === null) startPlayback();
    else stopPlayback();
  });

  return selectCampaign(CONFIG.campaigns[CONFIG.campaigns.length - 1]);
}

function renderCampaignTable() {
  const rows = CONFIG.campaigns.map(c => {
    const nodes = c.runs.map(r => `${r.node} at ${r.position} (${CONFIG.positions[r.position].distance_m} m)`).join(', ');
    const notes = c.runs.filter(r => r.note).map(r => `${r.node}: ${r.note}`).join('. ');
    return `<tr><td>${c.id}</td>` +
           `<td>${fmtLocalShort(c.start_utc)} to ${fmtLocalShort(c.end_utc)} 2026</td>` +
           `<td>${nodes}</td>` +
           `<td>SF${c.sf}, ${c.tx_dbm} dBm, ${c.enclosure}</td>` +
           `<td class="note">${notes || '—'}</td></tr>`;
  });
  document.getElementById('campaign-table').innerHTML =
    '<tr><th>Campaign</th><th>Window</th><th>Nodes</th><th>Radio</th><th>Sensor state</th></tr>' + rows.join('');
}

document.addEventListener('DOMContentLoaded', async () => {
  CONFIG = await loadDeployments();
  document.getElementById('attribution').textContent = CONFIG.map.attribution;
  document.getElementById('tz-label').textContent = CONFIG.timezone.label;

  renderCampaignTable();
  initLiveMap();
  await refreshLive();
  setInterval(refreshLive, 60000);
  await initReplay();
});
