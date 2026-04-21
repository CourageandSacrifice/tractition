const API = "https://kggmdmgpz2.execute-api.us-east-1.amazonaws.com/prod";

// Clock
setInterval(() => {
  document.getElementById('clock').textContent = new Date().toLocaleTimeString('en-GB');
}, 1000);

// Drag and drop
const zone = document.getElementById('upload-zone');
zone.addEventListener('dragover', e => { e.preventDefault(); zone.classList.add('dragover'); });
zone.addEventListener('dragleave', () => zone.classList.remove('dragover'));
zone.addEventListener('drop', e => {
  e.preventDefault();
  zone.classList.remove('dragover');
  const file = e.dataTransfer.files[0];
  if (file) processFile(file);
});

function handleFile(input) {
  if (input.files[0]) processFile(input.files[0]);
}

function processFile(file) {
  if (!file.name.endsWith('.csv')) {
    showMsg('tel-msg', 'ERROR: Only CSV files are supported.', 'error');
    return;
  }
  const reader = new FileReader();
  reader.onload = e => {
    const lines = e.target.result.trim().split('\n');
    const headers = lines[0].split(',').map(h => h.trim().toLowerCase());
    const rows = lines.slice(1).map(l => {
      const vals = l.split(',');
      const obj = {};
      headers.forEach((h, i) => obj[h] = vals[i]?.trim());
      return obj;
    });

    // Preview
    const preview = document.getElementById('tel-preview');
    preview.style.display = 'block';
    preview.innerHTML = lines.slice(0, 8).map((l, i) =>
      `<div><span class="line-num">${String(i).padStart(3, '0')}</span><span class="${i > 0 ? 'val' : ''}">${l}</span></div>`
    ).join('');

    // Stats
    const speedCol = headers.find(h => h.includes('speed'));
    const throttleCol = headers.find(h => h.includes('throttle'));

    const maxSpeed = speedCol
      ? Math.max(...rows.map(r => parseFloat(r[speedCol]) || 0)).toFixed(1) + ' km/h'
      : 'N/A';
    const maxThrottle = throttleCol
      ? Math.max(...rows.map(r => parseFloat(r[throttleCol]) || 0)).toFixed(0) + '%'
      : 'N/A';

    document.getElementById('stat-maxspeed').textContent = maxSpeed;
    document.getElementById('stat-maxthrottle').textContent = maxThrottle;
    document.getElementById('stat-rows').textContent = rows.length;
    document.getElementById('tel-stats').style.display = 'grid';

    showMsg('tel-msg', `// FILE LOADED: ${file.name} — ${rows.length} data points parsed.`, 'success');
  };
  reader.readAsText(file);
}

function parseTime(str) {
  const parts = str.split(':');
  if (parts.length !== 2) return null;
  const mins = parseInt(parts[0]);
  const secs = parseFloat(parts[1]);
  if (isNaN(mins) || isNaN(secs)) return null;
  return (mins * 60 * 1000) + Math.round(secs * 1000);
}

function formatTime(ms) {
  const mins = Math.floor(ms / 60000);
  const secs = ((ms % 60000) / 1000).toFixed(3);
  return `${mins}:${secs.padStart(6, '0')}`;
}

function showMsg(id, text, type) {
  const el = document.getElementById(id);
  el.textContent = text;
  el.className = `message ${type}`;
}

async function submitLap() {
  const driverName = document.getElementById('driver-name').value.trim();
  const driverId = document.getElementById('driver-id').value.trim();
  const trackSelect = document.getElementById('track-id');
  const trackId = trackSelect.value;
  const trackName = trackSelect.options[trackSelect.selectedIndex].dataset.name;
  const lapTimeStr = document.getElementById('lap-time').value.trim();

  if (!driverName || !driverId || !lapTimeStr) {
    showMsg('submit-msg', 'ERROR: All fields are required.', 'error');
    return;
  }

  const lapTimeMs = parseTime(lapTimeStr);
  if (!lapTimeMs) {
    showMsg('submit-msg', 'ERROR: Invalid format. Use mm:ss.ms — e.g. 1:23.456', 'error');
    return;
  }

  showMsg('submit-msg', '// Transmitting...', 'info');

  try {
    const res = await fetch(`${API}/laps`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ driver_id: driverId, driver_name: driverName, track_id: trackId, track_name: trackName, lap_time_ms: lapTimeMs })
    });
    const data = await res.json();
    if (data.is_record) {
      showMsg('submit-msg', '// NEW TRACK RECORD — SNS alert dispatched.', 'record');
    } else {
      showMsg('submit-msg', `// LAP ACCEPTED — ${formatTime(lapTimeMs)}`, 'success');
    }
  } catch (err) {
    showMsg('submit-msg', 'ERROR: Could not reach API. Is LocalStack running?', 'error');
  }
}

function renderTrackMap(trackId) {
  const path = typeof TRACK_PATHS !== 'undefined' ? TRACK_PATHS[trackId] : null;
  if (!path) return;
  document.getElementById('track-path').setAttribute('d', path);
  document.getElementById('track-path-highlight').setAttribute('d', path);
}

async function loadLeaderboard(trackId, tabEl) {
  renderTrackMap(trackId);
  document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
  tabEl.classList.add('active');

  const tbody = document.getElementById('leaderboard-body');
  tbody.innerHTML = '<tr><td colspan="4" style="color:#333;text-align:center;padding:32px;font-family:var(--mono);font-size:12px">// LOADING...</td></tr>';

  try {
    const res = await fetch(`${API}/leaderboard/${trackId}`);
    const data = await res.json();

    document.getElementById('cache-badge').style.display = data.cached ? 'inline' : 'none';

    if (!data.leaderboard || data.leaderboard.length === 0) {
      tbody.innerHTML = '<tr><td colspan="4" style="color:#333;text-align:center;padding:32px;font-family:var(--mono);font-size:12px">// NO LAPS RECORDED</td></tr>';
      return;
    }

    tbody.innerHTML = data.leaderboard.map((entry, i) => `
      <tr class="${i === 0 ? 'first-place' : ''}">
        <td class="pos ${i === 0 ? 'gold' : ''}">${i === 0 ? '01 &#9660;' : String(i + 1).padStart(2, '0')}</td>
        <td>${entry.driver_name}</td>
        <td>${formatTime(entry.lap_time_ms)}</td>
        <td style="color:#444">${new Date(entry.timestamp).toLocaleDateString()}</td>
      </tr>
    `).join('');
  } catch (err) {
    tbody.innerHTML = '<tr><td colspan="4" style="color:#cc0000;text-align:center;padding:32px;font-family:var(--mono);font-size:12px">// CONNECTION FAILED</td></tr>';
  }
}

loadLeaderboard('monaco', document.querySelector('.tab.active'));