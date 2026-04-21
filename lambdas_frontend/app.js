const API = "https://kggmdmgpz2.execute-api.us-east-1.amazonaws.com/prod";
const COGNITO_CLIENT_ID = "1485nptlm6cp3ffd89eg5t8v6k";
const COGNITO_REGION = "us-east-1";
const COGNITO_URL = `https://cognito-idp.${COGNITO_REGION}.amazonaws.com/`;

let authToken = null;

// Clock
setInterval(() => {
  document.getElementById('clock').textContent = new Date().toLocaleTimeString('en-GB');
}, 1000);

// Show/hide password
function togglePassword() {
  const input = document.getElementById('auth-password');
  const label = document.getElementById('eye-label');
  if (input.type === 'password') {
    input.type = 'text';
    label.textContent = 'hide';
  } else {
    input.type = 'password';
    label.textContent = 'show';
  }
}

// ── AUTH ──
async function cognitoRequest(action, body) {
  const res = await fetch(COGNITO_URL, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/x-amz-json-1.1',
      'X-Amz-Target': `AWSCognitoIdentityProviderService.${action}`
    },
    body: JSON.stringify(body)
  });
  const data = await res.json();
  if (!res.ok) throw new Error(data.message || data.__type || 'Auth error');
  return data;
}

async function login() {
  const email = document.getElementById('auth-email').value.trim();
  const password = document.getElementById('auth-password').value.trim();
  if (!email || !password) {
    showMsg('auth-msg', 'ERROR: Email and password required.', 'error');
    return;
  }
  showMsg('auth-msg', '// Authenticating...', 'info');
  try {
    const data = await cognitoRequest('InitiateAuth', {
      AuthFlow: 'USER_PASSWORD_AUTH',
      ClientId: COGNITO_CLIENT_ID,
      AuthParameters: { USERNAME: email, PASSWORD: password }
    });
    authToken = data.AuthenticationResult.IdToken;
    showAuthenticatedUI(email);
  } catch (err) {
    showMsg('auth-msg', `ERROR: ${err.message}`, 'error');
  }
}

async function signup() {
  const email = document.getElementById('auth-email').value.trim();
  const password = document.getElementById('auth-password').value.trim();
  if (!email || !password) {
    showMsg('auth-msg', 'ERROR: Email and password required.', 'error');
    return;
  }
  if (password.length < 8) {
    showMsg('auth-msg', 'ERROR: Password must be at least 8 characters.', 'error');
    return;
  }
  showMsg('auth-msg', '// Creating account...', 'info');
  try {
    await cognitoRequest('SignUp', {
      ClientId: COGNITO_CLIENT_ID,
      Username: email,
      Password: password,
      UserAttributes: [{ Name: 'email', Value: email }]
    });
    document.getElementById('confirm-section').style.display = 'block';
    document.getElementById('confirm-email-display').textContent = email;
    showMsg('auth-msg', '// Account created! Enter the code sent to your email.', 'success');
  } catch (err) {
    showMsg('auth-msg', `ERROR: ${err.message}`, 'error');
  }
}

async function confirmSignup() {
  const email = document.getElementById('auth-email').value.trim();
  const code = document.getElementById('confirm-code').value.trim();
  if (!code) {
    showMsg('auth-msg', 'ERROR: Enter the confirmation code.', 'error');
    return;
  }
  showMsg('auth-msg', '// Verifying...', 'info');
  try {
    await cognitoRequest('ConfirmSignUp', {
      ClientId: COGNITO_CLIENT_ID,
      Username: email,
      ConfirmationCode: code
    });
    document.getElementById('confirm-section').style.display = 'none';
    showMsg('auth-msg', '// Email verified! You can now log in.', 'success');
  } catch (err) {
    showMsg('auth-msg', `ERROR: ${err.message}`, 'error');
  }
}

function logout() {
  authToken = null;
  document.getElementById('auth-section').style.display = 'block';
  document.getElementById('app-section').style.display = 'none';
  document.getElementById('auth-email').value = '';
  document.getElementById('auth-password').value = '';
  document.getElementById('confirm-section').style.display = 'none';
  document.getElementById('confirm-code').value = '';
  showMsg('auth-msg', '', '');
}

function showAuthenticatedUI(email) {
  document.getElementById('auth-section').style.display = 'none';
  document.getElementById('app-section').style.display = 'block';
  document.getElementById('logged-in-email').textContent = email;
  loadLeaderboard('monaco', document.querySelector('.tab.active'));
}

// ── DRAG AND DROP ──
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
    const preview = document.getElementById('tel-preview');
    preview.style.display = 'block';
    preview.innerHTML = lines.slice(0, 8).map((l, i) =>
      `<div><span class="line-num">${String(i).padStart(3, '0')}</span><span class="${i > 0 ? 'val' : ''}">${l}</span></div>`
    ).join('');
    const speedCol = headers.find(h => h.includes('speed'));
    const throttleCol = headers.find(h => h.includes('throttle'));
    document.getElementById('stat-maxspeed').textContent = speedCol
      ? Math.max(...rows.map(r => parseFloat(r[speedCol]) || 0)).toFixed(1) + ' km/h' : 'N/A';
    document.getElementById('stat-maxthrottle').textContent = throttleCol
      ? Math.max(...rows.map(r => parseFloat(r[throttleCol]) || 0)).toFixed(0) + '%' : 'N/A';
    document.getElementById('stat-rows').textContent = rows.length;
    document.getElementById('tel-stats').style.display = 'grid';
    showMsg('tel-msg', `// FILE LOADED: ${file.name} — ${rows.length} data points parsed.`, 'success');
  };
  reader.readAsText(file);
}

// ── HELPERS ──
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
  if (!el) return;
  el.textContent = text;
  el.className = `message ${type}`;
}

// ── LAP SUBMIT ──
async function submitLap() {
  if (!authToken) {
    showMsg('submit-msg', 'ERROR: You must be logged in.', 'error');
    return;
  }
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
      headers: {
        'Content-Type': 'application/json',
        'Authorization': authToken
      },
      body: JSON.stringify({ driver_id: driverId, driver_name: driverName, track_id: trackId, track_name: trackName, lap_time_ms: lapTimeMs })
    });
    const data = await res.json();
    if (data.is_record) {
      showMsg('submit-msg', '// NEW TRACK RECORD — SNS alert dispatched.', 'record');
    } else {
      showMsg('submit-msg', `// LAP ACCEPTED — ${formatTime(lapTimeMs)}`, 'success');
    }
  } catch (err) {
    showMsg('submit-msg', 'ERROR: Could not reach API.', 'error');
  }
}

// ── LEADERBOARD ──
async function loadLeaderboard(trackId, tabEl) {
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