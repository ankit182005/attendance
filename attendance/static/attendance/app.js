// ==============================
// Full app.js - complete version
// - diagnostics + setLogoutIndicator
// - sendBeacon on close + revive on quick reload
// - improved Admin Create User modal
// API_BASE must be "http://127.0.0.1:8000/api/"
// tokenKey = 'att_access_token'
// ==============================

// ---- Configuration ----
//const API_BASE = 'http://127.0.0.1:8000/api/'; // local
const API_BASE = 'https://attendance-0gu9.onrender.com/api/'; // prod
const tokenKey = 'att_access_token';

// ===== styles =====
(function injectStyles(){
  const css = `
    .danger-btn { background-color:#d9534f;color:white;border:none;padding:6px 10px;border-radius:4px;cursor:pointer;margin-left:6px; }
    .danger-btn:hover { background-color:#c9302c; }
    .secondary { margin-left:8px; }

    #tracking-backdrop { position:fixed; inset:0; background:rgba(0,0,0,0.45); display:flex; align-items:center; justify-content:center; opacity:0; transition:.18s; z-index:9999; }
    #tracking-backdrop.show { opacity:1; }
    .tracking-modal { background:white; border-radius:8px; box-shadow:0 6px 24px rgba(0,0,0,.25); width:600px; max-height:90vh; overflow:auto; }
    .tracking-btn { padding:6px 8px; border-radius:4px; border:1px solid #ddd; background:#f0f0f0; cursor:pointer; }
    .tracking-btn.primary { background:#007bff;color:white;border-color:#007bff; }
    .small-note { color:#666; font-size:12px; }
    /* logout-indicator */
    #logout-indicator-wrapper { padding:8px 10px; border-radius:6px; background:#f7f7f7; margin-bottom:10px; border:1px solid #eee; }
    #logout-indicator .dot { display:inline-block; width:10px; height:10px; background:#28a745; border-radius:50%; margin-right:8px; vertical-align:middle; }

    /* basic cards/tables for layout */
    .card { background:white;border-radius:8px;padding:12px;margin-bottom:12px;border:1px solid #eee;box-shadow:0 1px 4px rgba(0,0,0,0.03); }
    .row { margin-bottom:8px; }
    .table { width:100%; border-collapse:collapse; }
    .table th, .table td { padding:8px; border-bottom:1px solid #f0f0f0; }
    .actions button { margin-right:6px; }
  `;
  const s = document.createElement('style');
  s.appendChild(document.createTextNode(css));
  document.head.appendChild(s);
})();

// ===== utilities =====
function el(id){ return document.getElementById(id); }
function qs(sel, parent=document){ return parent.querySelector(sel); }
function escapeHtml(s){ return (s+'').replace(/[&<>"']/g, c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c])); }
function fmtDate(ts){ if(!ts) return '—'; const d = new Date(ts); return isNaN(d) ? String(ts) : d.toLocaleString(); }
function fmtDuration(start, end){ try{ const s=new Date(start); const e=new Date(end); if(isNaN(s) || isNaN(e)) return '—'; const ms=Math.max(0, e-s); const sec=Math.floor(ms/1000)%60; const min=Math.floor(ms/60000)%60; const hr=Math.floor(ms/3600000); return `${hr}h ${min}m ${sec}s`; }catch(e){ return '—'; } }

// ===== token helpers =====
function getToken(){ try{ return sessionStorage.getItem(tokenKey); }catch(e){ return null; } }
function setToken(t){ try{ if(t) sessionStorage.setItem(tokenKey, t); else sessionStorage.removeItem(tokenKey); }catch(e){} }

// ===== diagnostic-friendly apiFetch =====
async function apiFetch(path, opts = {}) {
  const headers = Object.assign({}, opts.headers || {});

  // add client timezone header
  try { headers['X-Client-Timezone'] = Intl.DateTimeFormat().resolvedOptions().timeZone; } catch(e){}

  // auto json stringify
  if(opts.body && typeof opts.body === 'object' && !(opts.body instanceof FormData) && !(opts.body instanceof Blob)) {
    if(!headers['Content-Type']) headers['Content-Type'] = 'application/json';
    if(typeof opts.body !== 'string') opts.body = JSON.stringify(opts.body);
  }

  // add authorization
  const token = getToken();
  if(token) headers['Authorization'] = 'Bearer ' + token;

  opts.headers = headers;

  const fullUrl = API_BASE + path;
  let res;
  try {
    res = await fetch(fullUrl, opts);
  } catch(fetchErr) {
    console.error('apiFetch network error:', fetchErr, fullUrl, opts);
    throw { status: 'network_error', data: String(fetchErr) };
  }

  const ct = res.headers.get('content-type') || '';
  const isJson = ct.includes('application/json') || ct.includes('text/json');
  let data = null;
  try {
    if(isJson) data = await res.json().catch(()=>null);
    else data = await res.blob().catch(()=>null);
  } catch(parseErr){
    console.warn('apiFetch parse error', parseErr, fullUrl);
  }

  if(!res.ok) {
    console.error(`apiFetch bad response: ${res.status} ${res.statusText} -> ${fullUrl}`, data);
    // If unauthorized, clear token and redirect to login
    if(res.status === 401){
      try{ setToken(null); location.hash = '#login'; } catch(e){/* ignore */ }
    }
    throw { status: res.status, data };
  }
  return data;
}

// ===== helper to download blobs =====
function downloadBlob(blob, filename){
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a'); a.href = url; a.download = filename || 'file';
  document.body.appendChild(a); a.click(); a.remove();
  setTimeout(()=>URL.revokeObjectURL(url), 1000);
}

// ===== navigation & rendering =====
window.addEventListener('hashchange', render);
window.addEventListener('load', render);

function navigateTo(hash){ location.hash = hash; render(); }
function isLogged(){ return !!getToken(); }

function renderHeader(){
  if(!el('top-actions')) return;
  if(isLogged()){
    el('top-actions').innerHTML = `<button id="btn-profile">Profile</button><button id="btn-logout" class="secondary">Logout</button>`;
    el('btn-profile').addEventListener('click', ()=>navigateTo('#dashboard'));
    el('btn-logout').addEventListener('click', ()=>{ setToken(null); navigateTo('#login'); render(); });
  } else {
    el('top-actions').innerHTML = `<button id="btn-login" class="secondary">Sign In</button>`;
    el('btn-login').addEventListener('click', ()=>navigateTo('#login'));
  }
}

// ===== NEW: logout indicator UI helper (fixed) =====
function setLogoutIndicator(show) {
  const container = document.getElementById('dash-content') || document.getElementById('main') || document.body;
  if (!container) return;
  const existing = document.getElementById('logout-indicator-wrapper');
  if (existing) existing.remove();
  if (!show) return;

  const wrapper = document.createElement('div');
  wrapper.id = 'logout-indicator-wrapper';
  wrapper.style.marginBottom = '10px';

  const badge = document.createElement('div');
  badge.id = 'logout-indicator';
  badge.className = 'logout-indicator';
  badge.innerHTML = `<span class="dot" aria-hidden="true"></span><span style="font-weight:600">Auto-logout on tab close</span>`;

  const note = document.createElement('div');
  note.className = 'logout-note small-note';
  note.textContent = 'If you close the tab or browser, your session will end and logout time will be saved. Quick refreshes will NOT end the session.';

  wrapper.appendChild(badge);
  wrapper.appendChild(note);

  // Insert at top of container
  try { container.insertBefore(wrapper, container.firstChild); } catch(e){ container.appendChild(wrapper); }
}

// ===== render router =====
async function render(){
  renderHeader();
  const h = location.hash || '';

  // allowed routes
  const allowed = ['#login', '#dashboard', '#admin'];
  // if no hash -> route to appropriate default
  if(!h || h === '#'){
    const target = isLogged() ? '#dashboard' : '#login';
    if(location.hash !== target) { location.hash = target; return; }
  }

  // if unknown hash send to appropriate page (but only change location.hash once)
  if(!allowed.includes(h)){
    const target = isLogged() ? '#dashboard' : '#login';
    if(location.hash !== target){ location.hash = target; return; }
  }

  // dispatch
  if(location.hash === '#login') return renderLogin();
  if(location.hash === '#dashboard') return renderDashboard();
  if(location.hash === '#admin') return renderAdmin();
}

// ===== Login UI =====
function renderLogin(){
  if(!el('main')) { console.error('renderLogin: #main missing'); return; }
  el('main').innerHTML = `
    <div class="card">
      <h3>Sign In</h3>
      <form id="form-login">
        <div class="row"><label>Username</label><input id="login-username" required /></div>
        <div class="row"><label>Password</label><input id="login-password" type="password" required /></div>
        <div class="row"><button id="login-submit">Sign In</button></div>
        <div id="login-msg" class="small-note"></div>
      </form>
    </div>
  `;

  const form = document.getElementById('form-login');
  const submitBtn = document.getElementById('login-submit');
  const msg = document.getElementById('login-msg');

  let submitting = false;
  form.addEventListener('submit', async (e)=>{
    e.preventDefault();
    if(submitting) return;
    submitting = true;
    submitBtn.disabled = true;
    msg.textContent = '';

    const u = document.getElementById('login-username').value.trim();
    const p = document.getElementById('login-password').value;

    try{
      const res = await apiFetch('auth/token/', { method: 'POST', body: { username: u, password: p } });
      console.log('login response', res);
      const token = res?.access || res?.token || res?.key || res;
      if(!token) { msg.textContent = 'Login succeeded but token missing in response'; console.error('Login token missing', res); submitting = false; submitBtn.disabled = false; return; }
      setToken(token);
      // navigate to dashboard
      navigateTo('#dashboard');
    }catch(err){
      console.error('Login failed', err);
      // prefer known error shapes
      msg.textContent = err?.data?.detail || (typeof err?.data === 'string' ? err.data : 'Login failed. Check credentials and try again.');
      submitting = false;
      submitBtn.disabled = false;
    }
  });
}

// ===== Dashboard =====
async function renderDashboard(){
  if(!el('main')) { console.error('#main not found'); return; }
  if(!isLogged()) return navigateTo('#login');

  el('main').innerHTML = `<div class="card"><h3>Dashboard</h3><div id="dash-content">Loading...</div></div>`;

  try{
    const me = await apiFetch('attendance/auth/me/');
    console.log('current user', me);
    const isAdmin = !!me?.is_staff;

    const status = await apiFetch('attendance/status/');
    console.log('status', status);
    const active = status.active_attendance;
    const last = status.last_attendance;

    let html = `<div class="card"><h4>Attendance</h4><div class="small-note">Active: ${active ? 'Yes' : 'No'}</div>`;

    if(!active){
      html += `<div style="margin-top:12px"><button id="start-btn">Start Attendance</button></div>`;
    } else {
      const activeBreak = active.breaks && active.breaks.some(b => b.end_time === null || b.end_time === undefined);
      html += `<div style="margin-top:12px" class="actions"><button id="break-btn">${activeBreak ? 'End Break' : 'Start Break'}</button><button id="end-btn" style="margin-left:8px" class="secondary">Logout (End Attendance)</button></div>`;
    }
    html += `</div>`;

    if(!last) {
      html += `<div class="card"><h4>Last Attendance</h4><div class="small-note">No recent attendance</div></div>`;
    } else {
      const start = last.start_time || last.start || null;
      const end   = last.end_time || last.end || null;
      const breaks = Array.isArray(last.breaks) ? last.breaks : [];
      const duration = start ? (end ? fmtDuration(start, end) : fmtDuration(start, new Date().toISOString())) : '—';
      html += `<div class="card"><h4>Last Attendance</h4>
        <div><strong>Start:</strong> ${escapeHtml(fmtDate(start))}</div>
        <div><strong>End:</strong> ${escapeHtml(fmtDate(end))}</div>
        <div><strong>Duration:</strong> ${escapeHtml(duration)}</div>
        <div><strong>Breaks:</strong> ${breaks.length}</div>
      </div>`;
    }

    if(isAdmin) {
      html += `<div class="card"><h4>Actions</h4><div class="actions"><button id="download-csv">Download Today's CSV</button><button id="save-csv" class="secondary">Save CSV Server-side</button><button id="goto-admin" class="secondary">Admin Dashboard</button></div></div>`;
    }

    const dashContent = el('dash-content');
    dashContent.innerHTML = html;

    // button handlers
    const startBtn = el('start-btn'); if(startBtn) startBtn.addEventListener('click', async ()=>{ try{ await apiFetch('attendance/start/', { method:'POST' }); renderDashboard(); }catch(e){ console.error('start failed', e); alert('Start failed'); }});
    const breakBtn = el('break-btn'); if(breakBtn) breakBtn.addEventListener('click', async ()=>{ try{ await apiFetch('attendance/break/toggle/', { method:'POST' }); renderDashboard(); }catch(e){ console.error('break toggle failed', e); alert('Break toggle failed'); }});
    const endBtn = el('end-btn'); if(endBtn) endBtn.addEventListener('click', async ()=>{ try{ await apiFetch('attendance/end/', { method:'POST' }); setToken(null); navigateTo('#login'); render(); }catch(e){ console.error('end failed', e); alert('End failed'); }});

    if(isAdmin){
      const dl = el('download-csv'); if(dl) dl.addEventListener('click', async ()=>{
        try{
          const token = getToken();
          const headers = {};
          if(token) headers['Authorization'] = 'Bearer ' + token;
          const res = await fetch(API_BASE + 'attendance/export/today/', { headers });
          if(!res.ok){
            // try parse json error
            let j = null;
            try{ j = await res.json().catch(()=>null); }catch(e){}
            throw j || `CSV download failed with ${res.status}`;
          }
          const blob = await res.blob();
          downloadBlob(blob, `attendance_${new Date().toISOString().slice(0,10)}.csv`);
        }catch(e){ console.error('csv download failed', e); alert('CSV failed'); }
      });

      const saveBtn = el('save-csv'); if(saveBtn) saveBtn.addEventListener('click', async ()=>{ try{ const r = await apiFetch('attendance/export/save/today/', { method:'POST' }); alert('Saved: ' + r.path); }catch(e){ console.error('save csv failed', e); alert('Save failed'); }});

      const gotoAdmin = el('goto-admin'); if(gotoAdmin) gotoAdmin.addEventListener('click', ()=>navigateTo('#admin'));
    }

    // logout indicator UI
    setLogoutIndicator(!!active);

  } catch(err){
    console.error('renderDashboard error', err);
    if(err && err.status === 401){
      setToken(null);
      navigateTo('#login');
    } else {
      const dc = el('dash-content');
      if(dc) dc.innerHTML = '<div class="card"><div class="small-note">Failed to load. See console for details.</div></div>';
    }
  }
}

// ===== Admin UI (improved Create User modal) =====
async function renderAdmin(){
  if(!el('main')) { console.error('#main missing'); return; }
  el('main').innerHTML = `<div class="card"><h3>Admin Dashboard</h3></div><div id="admin-body">Loading...</div>`;

  try{
    const me = await apiFetch('attendance/auth/me/');
    if(!me.is_staff) { el('admin-body').innerHTML = 'Access denied'; return; }

    const res = await apiFetch('attendance/employees/');
    const employees = res.employees || [];

    let tableHtml = `<div class="card" style="margin-bottom:12px"><h4>Employees</h4><table class="table" style="width:100%;border-collapse:collapse"><thead><tr style="text-align:left"><th>id</th><th>username</th><th>name</th><th>email</th><th>admin?</th><th>actions</th></tr></thead><tbody>`;
    for(const u of employees){
      let actions = `<button class="view-tracking">View</button>`;
      if(u.id !== me.id) actions += `<button class="promote">${u.is_staff? 'Demote':'Promote'}</button>`;
      if(!u.is_staff && u.id !== me.id){
        actions += `<button class="flush-user danger-btn">Flush</button>`;
        actions += `<button class="delete-user danger-btn">Delete</button>`;
      }
      tableHtml += `<tr data-id="${u.id}" style="border-top:1px solid #eee"><td style="padding:8px">${u.id}</td><td style="padding:8px">${escapeHtml(u.username)}</td><td style="padding:8px">${escapeHtml(u.first_name + ' ' + u.last_name)}</td><td style="padding:8px">${escapeHtml(u.email || '')}</td><td style="padding:8px">${u.is_staff? 'Yes' : 'No'}</td><td style="padding:8px"><div class="actions">${actions}</div></td></tr>`;
    }
    tableHtml += `</tbody></table></div>`;

    // compact toolbar with Create User button
    tableHtml += `<div style="display:flex;gap:8px;align-items:center;margin-bottom:12px">
      <button id="btn-open-create" style="padding:8px 12px;border-radius:6px">Create user</button>
      <div class="small-note" style="margin-left:8px">Create new user accounts (admins only).</div>
    </div>`;

    tableHtml += `<div class="card"><h4>Bulk Admin Actions</h4><div class="helper small-note">Flush attendance data for all non-admin users.</div><div style="margin-top:8px"><button id="flush-all-btn" class="danger-btn">Flush all non-admin attendance data</button></div></div>`;

    el('admin-body').innerHTML = tableHtml;

    // Create User modal markup (hidden initially)
    const modalHtml = `
      <div id="create-user-modal" style="position:fixed;inset:0;display:none;align-items:center;justify-content:center;z-index:10000;">
        <div style="position:absolute;inset:0;background:rgba(0,0,0,0.45)"></div>
        <div role="dialog" aria-modal="true" style="background:#fff;border-radius:8px;width:520px;max-width:94%;box-shadow:0 8px 40px rgba(0,0,0,0.25);position:relative;z-index:10001;padding:18px">
          <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px">
            <div style="font-weight:700;font-size:16px">Create user</div>
            <button id="cu-close" aria-label="Close" style="background:none;border:none;font-size:18px;cursor:pointer">✕</button>
          </div>

          <form id="cu-form" style="display:grid;gap:10px">
            <div style="display:grid;grid-template-columns:1fr 1fr;gap:8px">
              <div>
                <label style="font-size:13px">Username <span style="color:#d00">*</span></label>
                <input id="cu-username" required autocomplete="off" style="width:100%;padding:8px;border:1px solid #ddd;border-radius:6px" />
                <div id="err-cu-username" class="small-note" style="color:#d00;display:none"></div>
              </div>
              <div>
                <label style="font-size:13px">Email</label>
                <input id="cu-email" type="email" style="width:100%;padding:8px;border:1px solid #ddd;border-radius:6px" />
                <div id="err-cu-email" class="small-note" style="color:#d00;display:none"></div>
              </div>
            </div>

            <div style="display:grid;grid-template-columns:1fr 1fr;gap:8px">
              <div>
                <label style="font-size:13px">First name</label>
                <input id="cu-first" style="width:100%;padding:8px;border:1px solid #ddd;border-radius:6px" />
              </div>
              <div>
                <label style="font-size:13px">Last name</label>
                <input id="cu-last" style="width:100%;padding:8px;border:1px solid #ddd;border-radius:6px" />
              </div>
            </div>

            <div>
              <label style="font-size:13px">Password <span style="color:#d00">*</span></label>
              <div style="display:flex;gap:8px">
                <input id="cu-password" type="password" required style="flex:1;padding:8px;border:1px solid #ddd;border-radius:6px" autocomplete="new-password" />
                <button id="cu-gen" type="button" class="secondary" style="padding:6px 8px">Generate</button>
                <button id="cu-show" type="button" class="secondary" style="padding:6px 8px">Show</button>
              </div>
              <div style="display:flex;align-items:center;gap:8px;margin-top:6px">
                <div id="pw-meter" style="height:8px;border-radius:4px;background:#eee;flex:1;overflow:hidden">
                  <div id="pw-meter-fill" style="width:0%;height:100%;background:#eee"></div>
                </div>
                <div id="pw-score" class="small-note" style="min-width:80px;text-align:right;color:#666;font-size:12px">Too weak</div>
              </div>
              <div id="err-cu-password" class="small-note" style="color:#d00;display:none"></div>
            </div>

            <div style="display:flex;align-items:center;gap:8px">
              <label style="display:flex;align-items:center;gap:8px"><input id="cu-is-staff" type="checkbox" /> Grant admin</label>
              <div style="flex:1"></div>
              <div id="cu-form-msg" class="small-note" style="color:#070"></div>
            </div>

            <div style="display:flex;justify-content:flex-end;gap:8px;margin-top:6px">
              <button id="cu-cancel" type="button" class="secondary">Cancel</button>
              <button id="cu-submit" type="submit" style="padding:8px 12px;border-radius:6px">Create user</button>
            </div>
          </form>
        </div>
      </div>
    `;

    // append modal to body (once)
    if(!document.getElementById('create-user-modal')){
      document.body.insertAdjacentHTML('beforeend', modalHtml);
    }

    // open modal handler
    const openBtn = document.getElementById('btn-open-create');
    openBtn.addEventListener('click', ()=> {
      const modal = document.getElementById('create-user-modal');
      if(modal) {
        modal.style.display = 'flex';
        // reset fields
        document.getElementById('cu-form').reset();
        hideErr('cu-username'); hideErr('cu-email'); hideErr('cu-password');
        setPwMeter(0);
        document.getElementById('cu-form-msg').textContent = '';
        document.getElementById('cu-username').focus();
      }
    });

    // modal controls
    document.getElementById('cu-close').addEventListener('click', ()=> { document.getElementById('create-user-modal').style.display = 'none'; });
    document.getElementById('cu-cancel').addEventListener('click', ()=> { document.getElementById('create-user-modal').style.display = 'none'; });

    // password utilities
    function randPwd(len=12){
      const chars = 'ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnpqrstuvwxyz23456789!@#$%&*';
      let s=''; for(let i=0;i<len;i++) s += chars[Math.floor(Math.random()*chars.length)]; return s;
    }
    function estimateStrength(pw){
      // 0..100 simple estimator
      let score = 0;
      if(pw.length >= 8) score += 20;
      if(pw.length >= 12) score += 10;
      if(/[a-z]/.test(pw)) score += 20;
      if(/[A-Z]/.test(pw)) score += 20;
      if(/[0-9]/.test(pw)) score += 15;
      if(/[^A-Za-z0-9]/.test(pw)) score += 15;
      return Math.min(100, score);
    }
    function setPwMeter(score){
      const fill = document.getElementById('pw-meter-fill');
      const txt = document.getElementById('pw-score');
      if(!fill || !txt) return;
      fill.style.width = score + '%';
      if(score < 40){ fill.style.background = '#e55353'; txt.textContent = 'Too weak'; }
      else if(score < 70){ fill.style.background = '#f0ad4e'; txt.textContent = 'Okay'; }
      else { fill.style.background = '#5cb85c'; txt.textContent = 'Strong'; }
    }

    // show/hide password
    const showBtn = document.getElementById('cu-show');
    showBtn.addEventListener('click', ()=>{
      const p = document.getElementById('cu-password');
      if(p.type === 'password'){ p.type = 'text'; showBtn.textContent = 'Hide'; }
      else { p.type = 'password'; showBtn.textContent = 'Show'; }
    });

    // generate password
    document.getElementById('cu-gen').addEventListener('click', ()=>{
      const pw = randPwd(12);
      const p = document.getElementById('cu-password');
      p.value = pw;
      const score = estimateStrength(pw);
      setPwMeter(score);
    });

    // password input strength update
    document.getElementById('cu-password').addEventListener('input', (e)=>{
      const pw = e.target.value || '';
      setPwMeter(estimateStrength(pw));
      hideErr('cu-password');
    });

    // helper to show/hide field error
    function showErr(id, msg){
      const elErr = document.getElementById('err-' + id);
      if(elErr){ elErr.style.display = 'block'; elErr.textContent = msg; }
    }
    function hideErr(id){
      const elErr = document.getElementById('err-' + id);
      if(elErr){ elErr.style.display = 'none'; elErr.textContent = ''; }
    }

    // submit handler
    const cuForm = document.getElementById('cu-form');
    cuForm.addEventListener('submit', async (ev)=>{
      ev.preventDefault();
      // clear messages
      hideErr('cu-username'); hideErr('cu-email'); hideErr('cu-password');
      const msg = document.getElementById('cu-form-msg'); msg.textContent = ''; 
      const submitBtn = document.getElementById('cu-submit');
      submitBtn.disabled = true; submitBtn.textContent = 'Creating...';

      const username = document.getElementById('cu-username').value.trim();
      const password = document.getElementById('cu-password').value;
      const first_name = document.getElementById('cu-first').value.trim();
      const last_name = document.getElementById('cu-last').value.trim();
      const email = document.getElementById('cu-email').value.trim();
      const is_staff = document.getElementById('cu-is-staff').checked;

      // client-side validation
      let ok = true;
      if(!username){ showErr('cu-username','Username required'); ok = false; }
      if(!password){ showErr('cu-password','Password required'); ok = false; }
      if(email && !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)){ showErr('cu-email','Invalid email'); ok = false; }

      if(!ok){ submitBtn.disabled = false; submitBtn.textContent = 'Create user'; return; }

      try{
        const body = { username, password, first_name, last_name, email, is_staff };
        const r = await apiFetch('attendance/auth/admin/create/', { method: 'POST', body });
        msg.style.color = '#070';
        msg.textContent = 'User created (id: ' + (r?.id || 'unknown') + ')';
        // close modal after short delay
        setTimeout(()=> {
          document.getElementById('create-user-modal').style.display = 'none';
          // refresh admin list
          renderAdmin();
        }, 700);
      }catch(err){
        console.error('Create user failed', err);
        const errData = err?.data;
        if(errData && typeof errData === 'object'){
          const detail = errData.detail || errData.error || null;
          if(detail) { msg.style.color = '#d00'; msg.textContent = detail; }
          if(typeof detail === 'string' && detail.toLowerCase().includes('username')) {
            showErr('cu-username', detail);
          }
        } else {
          msg.style.color = '#d00';
          msg.textContent = typeof errData === 'string' ? errData : 'Create failed';
        }
      } finally {
        submitBtn.disabled = false; submitBtn.textContent = 'Create user';
      }
    });

    // rest of admin buttons (promote/flush/delete) - reuse existing handlers
    bindViewTrackingButtonsToPopup();

    document.querySelectorAll('.promote').forEach(btn=>{
      btn.addEventListener('click', async (e)=>{
        const tr = e.target.closest('tr'); const id = tr.dataset.id;
        const makeAdmin = e.target.textContent.trim() === 'Promote';
        try{ await apiFetch(`attendance/auth/admin/promote/${id}/`, { method:'POST', body: { is_staff: makeAdmin } }); alert('Updated'); renderAdmin(); }catch(err){ console.error('promote failed', err); alert('Promote failed'); }
      });
    });

    document.querySelectorAll('.flush-user').forEach(btn=>{
      btn.addEventListener('click', async (e)=>{
        const id = e.target.closest('tr').dataset.id;
        if(!confirm(`Flush all attendance data of user ID ${id}?`)) return;
        try{ await apiFetch(`attendance/auth/admin/flush/${id}/`, { method:'POST' }); alert('User data flushed successfully'); renderAdmin(); }catch(err){ console.error('flush user failed', err); alert('Flush failed'); }
      });
    });

    document.querySelectorAll('.delete-user').forEach(btn=>{
      btn.addEventListener('click', async (e)=>{
        const id = e.target.closest('tr').dataset.id;
        if(!confirm(`DELETE user ID ${id}? This will remove the user account and attendance data and cannot be undone.`)) return;
        try{ await apiFetch(`attendance/auth/admin/delete/${id}/`, { method:'DELETE' }); alert('User deleted'); renderAdmin(); }catch(err){ console.error('delete failed', err); alert(err?.data?.detail || (err?.data || 'Delete failed')); }
      });
    });

    const flushAllBtn = el('flush-all-btn');
    if(flushAllBtn){
      flushAllBtn.addEventListener('click', async ()=>{
        if(!confirm('Are you sure? This will CLEAR attendance sessions for ALL non-admin users. This action is irreversible. Proceed?')) return;
        try{ const r = await apiFetch('attendance/auth/admin/flush_all/', { method:'POST' }); alert(`Flush completed. Flushed ${r.flushed.length || 0} users, skipped ${r.skipped.length || 0} staff accounts.`); renderAdmin(); }catch(err){ console.error('flush all failed', err); alert(err?.data?.detail || 'Flush all failed'); }
      });
    }

  }catch(err){
    console.error('renderAdmin error', err);
    el('admin-body').innerHTML = '<div class="small-note">Error loading admin panel. See console for details.</div>';
  }
}

// ===== popup: last attendance only =====
function bindViewTrackingButtonsToPopup(){
  document.querySelectorAll('.view-tracking').forEach(btn=>{
    const clone = btn.cloneNode(true);
    btn.parentNode.replaceChild(clone, btn);
    clone.addEventListener('click', async (e)=>{
      const id = e.target.closest('tr')?.dataset?.id;
      if(!id) return alert('Missing id');
      showTrackingPopup(id);
    });
  });
}

async function showTrackingPopup(empId){
  const existing = el('tracking-backdrop'); if(existing) existing.remove();
  const backdrop = document.createElement('div'); backdrop.id = 'tracking-backdrop';
  backdrop.innerHTML = `
    <div class="tracking-modal" role="dialog" aria-modal="true" aria-label="Last attendance for ${escapeHtml(empId)}">
      <div style="padding:10px;border-bottom:1px solid #eee;display:flex;justify-content:space-between;">
        <div style="font-weight:600">Last attendance — ID ${escapeHtml(empId)}</div>
        <div><button class="tracking-btn" id="tracking-close">Close</button></div>
      </div>
      <div id="track-content" style="padding:12px">Loading…</div>
    </div>
  `;
  document.body.appendChild(backdrop);
  requestAnimationFrame(()=>backdrop.classList.add('show'));
  const closeBtn = backdrop.querySelector('#tracking-close');
  if(closeBtn) closeBtn.addEventListener('click', ()=>backdrop.remove());
  backdrop.addEventListener('click', (ev)=>{ if(ev.target === backdrop) backdrop.remove(); });

  try{
    const res = await apiFetch(`attendance/employees/${empId}/tracking/`);
    const sessions = Array.isArray(res.sessions) ? res.sessions : [];
    if(sessions.length === 0){ el('track-content').innerHTML = '<div class="small-note">No sessions</div>'; return; }

    sessions.sort((a,b)=> (new Date(b.start_time||b.start||0)) - (new Date(a.start_time||a.start||0)));
    const last = sessions[0];
    const start = last.start_time || last.start || null;
    const end = last.end_time || last.end || null;
    const duration = start ? (end ? fmtDuration(start,end) : fmtDuration(start,new Date().toISOString())) : '—';
    const breaks = Array.isArray(last.breaks) ? last.breaks : [];

    el('track-content').innerHTML = `
      <div><strong>Start:</strong> ${escapeHtml(fmtDate(start))}</div>
      <div><strong>End:</strong> ${escapeHtml(fmtDate(end))}</div>
      <div><strong>Duration:</strong> ${escapeHtml(duration)}</div>
      <div style="margin-top:8px"><strong>Breaks:</strong><div class="small-note">${breaks.length}</div></div>
    `;
  }catch(err){
    console.error('popup load failed', err);
    el('track-content').innerHTML = `<div class="small-note">Failed to load. See console.</div>`;
  }
}

// ===== reliable close handling: sendBeacon on unload + revive on load =====
(function(){
  // must match server-side REFRESH_GRACE_MS (ms)
  const CLOSE_GRACE_MS = 1000; // 1 second
  const KEY = 'att_last_unload';

  // sendEnd function (keeps previous behavior)
  let sent = false;
  function sendEnd(){
    if(sent) return; sent = true;
    const token = getToken();
    if(!token) {
      console.debug('sendEnd: no token, skipping');
      return;
    }
    const payload = { logout_time: new Date().toISOString(), token };
    // try sendBeacon
    try{
      if(navigator.sendBeacon){
        try {
          const blob = new Blob([JSON.stringify(payload)], { type: 'application/json' });
          const ok = navigator.sendBeacon(API_BASE + 'attendance/end/', blob);
          console.debug('sendEnd: sendBeacon called, result=', ok);
        } catch(beErr){
          console.warn('sendEnd: sendBeacon failed to create blob', beErr);
        }
        return;
      }
    }catch(e){ console.warn('sendEnd: sendBeacon error', e); }
    // fallback fetch keepalive
    try{
      fetch(API_BASE + 'attendance/end/', {
        method: 'POST',
        body: JSON.stringify(payload),
        headers: { 'Content-Type': 'application/json' },
        keepalive: true
      }).catch((err)=>{ console.warn('sendEnd fallback fetch failed', err); });
    }catch(e){
      console.warn('sendEnd fetch threw', e);
    }
  }

  // On pagehide, record unload time AND try to send end via beacon.
  window.addEventListener('pagehide', (e)=>{
    try {
      sessionStorage.setItem(KEY, String(Date.now()));
    } catch(err){}
    // Always attempt to notify server (best-effort)
    try { sendEnd(); } catch(err){ console.warn('pagehide: sendEnd failed', err); }
  }, { passive: true });

  // On load, if previous unload was within CLOSE_GRACE_MS, call revive endpoint
  window.addEventListener('load', async ()=>{
    try {
      let raw = null;
      try { raw = sessionStorage.getItem(KEY); } catch(e){}
      let last = raw ? Number(raw) || 0 : 0;
      // clear marker to avoid repeated calls
      try { sessionStorage.removeItem(KEY); } catch(e){}
      const diff = last ? (Date.now() - last) : Infinity;

      if(last && diff < CLOSE_GRACE_MS){
        // quick reload — attempt revive
        console.debug('Quick reload detected (diff ms):', diff, '— sending revive request');
        try {
          // best-effort revive; server will decide if it should restore
          await apiFetch('attendance/revive_if_recent/', { method: 'POST' });
          console.debug('Revive request completed');
        } catch(revErr){
          console.warn('Revive request failed', revErr);
        }
      } else {
        // If diff exists and >= grace: previous tab likely closed long enough ago.
        // No action needed here because sendBeacon already attempted to notify server on pagehide.
        if(last) console.debug('Previous unload older than grace (diff ms):', diff);
      }
    } catch(e){ console.warn('unload/revive check failed', e); }
  }, { passive: true });
})();
