// ---- Configuration ----
const API_BASE = 'http://127.0.0.1:8000/api/'; // local
//const API_BASE = 'https://attendance-0gu9.onrender.com/api/'; //prod
const tokenKey = 'att_access_token';

// ---- Utilities ----
function el(id){ return document.getElementById(id); }
function qs(sel, parent=document){ return parent.querySelector(sel); }

function setTopActions(html){
  el('top-actions').innerHTML = html || '';
}

function setMain(html){
  el('main').innerHTML = html;
}

function showError(msg){
  setMain(`<div class="card error">${escapeHtml(msg)}</div>`);
}
function showSuccess(msg){
  setMain(`<div class="card success">${escapeHtml(msg)}</div>`);
}

function escapeHtml(s){ return (s+'').replace(/[&<>"']/g, c=>({ '&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;' }[c])); }

function getToken(){ return localStorage.getItem(tokenKey); }
function setToken(t){
  if(t) localStorage.setItem(tokenKey, t);
  else localStorage.removeItem(tokenKey);
}

async function apiFetch(path, opts={}){
  const headers = opts.headers||{};
  headers['Content-Type'] = headers['Content-Type'] || 'application/json';
  const token = getToken();
  if(token) headers['Authorization'] = 'Bearer ' + token;
  opts.headers = headers;
  const res = await fetch(API_BASE + path, opts);
  const ct = res.headers.get('content-type') || '';
  const isJson = ct.includes('application/json') || ct.includes('text/json');
  const data = isJson ? await res.json().catch(()=>null) : await res.blob().catch(()=>null);
  if(!res.ok){
    // Try to return error info
    throw { status: res.status, data };
  }
  return data;
}

// download blob
function downloadBlob(blob, name){
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url; a.download = name || 'file';
  document.body.appendChild(a); a.click(); a.remove();
  setTimeout(()=>URL.revokeObjectURL(url), 1000);
}

// ---- SPA Routing ----
function isLogged(){ return !!getToken(); }

function renderHeader(){
  if(isLogged()){
    setTopActions(`
      <button id="btn-profile" class="secondary">Profile</button>
      <button id="btn-logout" class="secondary">Logout</button>
    `);
    qs('#top-actions #btn-logout').addEventListener('click', ()=>{ setToken(null); navigateTo('#login'); render(); });
    qs('#top-actions #btn-profile').addEventListener('click', ()=>navigateTo('#dashboard'));
  } else {
    setTopActions(`
      <button id="btn-login" class="secondary">Sign In</button>
      <button id="btn-register" class="secondary">Register</button>
    `);
    qs('#top-actions #btn-login').addEventListener('click', ()=>navigateTo('#login'));
    qs('#top-actions #btn-register').addEventListener('click', ()=>navigateTo('#register'));
  }
}

function navigateTo(hash){
  location.hash = hash;
  render();
}

async function render(){
  renderHeader();
  const h = location.hash || '#home';
  if(h === '#login') return renderLogin();
  if(h === '#register') return renderRegister();
  if(h === '#dashboard') return renderDashboard();
  if(h === '#admin') return renderAdmin();
  // default
  if(isLogged()) navigateTo('#dashboard'); else navigateTo('#login');
}

// ---- Login / Register ----
function renderLogin(){
  setMain(`
    <div class="card">
      <h3>Sign In</h3>
      <form id="form-login">
        <div class="row"><label>Username</label><input id="login-username" required /></div>
        <div class="row"><label>Password</label><input id="login-password" type="password" required /></div>
        <div class="row"><button>Sign In</button></div>
        <div id="login-msg" class="helper"></div>
      </form>
    </div>
  `);
  document.getElementById('form-login').addEventListener('submit', async (e)=>{
    e.preventDefault();
    const u = document.getElementById('login-username').value.trim();
    const p = document.getElementById('login-password').value;
    const msg = document.getElementById('login-msg');
    msg.textContent = '';
    try{
      const res = await apiFetch('auth/token/', { method:'POST', body: JSON.stringify({username:u,password:p}) });
      setToken(res.access);
      msg.textContent = 'Logged in';
      navigateTo('#dashboard');
      render();
    }catch(err){
      console.error(err);
      msg.textContent = err?.data?.detail || 'Login failed';
    }
  });
}

function renderRegister(){
  setMain(`
    <div class="card">
      <h3>Register (Employee)</h3>
      <form id="form-register">
        <div class="row"><label>Username</label><input id="reg-username" required /></div>
        <div class="row"><label>Password</label><input id="reg-password" type="password" required /></div>
        <div class="row"><label>First name</label><input id="reg-first" /></div>
        <div class="row"><label>Last name</label><input id="reg-last" /></div>
        <div class="row"><label>Email</label><input id="reg-email" type="email" /></div>
        <div class="row"><button>Create account</button></div>
        <div id="reg-msg" class="helper"></div>
      </form>
    </div>
  `);
  document.getElementById('form-register').addEventListener('submit', async (e)=>{
    e.preventDefault();
    const payload = {
      username: document.getElementById('reg-username').value.trim(),
      password: document.getElementById('reg-password').value,
      first_name: document.getElementById('reg-first').value.trim(),
      last_name: document.getElementById('reg-last').value.trim(),
      email: document.getElementById('reg-email').value.trim()
    };
    const msg = document.getElementById('reg-msg');
    msg.textContent = '';
    try{
      await fetch(API_BASE + 'attendance/auth/register/', {
        method:'POST',
        headers: {'Content-Type':'application/json'},
        body: JSON.stringify(payload)
      }).then(r => r.json()).then(d=>{
        if(d.errors){ throw d; }
        msg.textContent = 'User created. Please sign in.';
        navigateTo('#login');
      });
    }catch(err){
      console.error(err);
      msg.textContent = (err?.errors || err?.detail || 'Registration failed' );
    }
  });
}

// ---- Dashboard (employee) ----
async function renderDashboard(){
  // fetch status
  setMain(`<div class="card"><h3>Dashboard</h3><div id="dash-content">Loading...</div></div>`);
  try{
    const status = await apiFetch('attendance/status/');
    const active = status.active_attendance;
    const last = status.last_attendance;
    let html = `<div class="card"><h4>Attendance</h4>`;
    html += `<div class="helper">Active: ${active ? 'Yes' : 'No'}</div>`;
    if(!active){
      html += `<div style="margin-top:12px"><button id="start-btn">Start Attendance</button></div>`;
    } else {
      // check if active break
      const activeBreak = active.breaks && active.breaks.some(b => b.end_time === null || b.end_time === undefined);
      html += `<div style="margin-top:12px" class="actions">`;
      html += `<button id="break-btn">${activeBreak ? 'End Break' : 'Start Break'}</button>`;
      html += `<button id="end-btn" style="margin-left:8px" class="secondary">Logout (End Attendance)</button>`;
      html += `</div>`;
    }
    html += `</div>`;

    html += `<div class="card"><h4>Last Attendance</h4><pre>${escapeHtml(JSON.stringify(last, null, 2))}</pre></div>`;

    html += `<div class="card"><h4>Actions</h4>
      <div class="actions">
        <button id="download-csv">Download Today's CSV</button>
        <button id="save-csv" class="secondary">Save CSV Server-side</button>
        <button id="flush-user" class="secondary">Flush My Data</button>
      </div>
    </div>`;

    // admin link (we will check if admin later)
    html += `<div id="admin-link" class="card" style="display:none"><button id="goto-admin" class="secondary">Admin Dashboard</button></div>`;

    setMain(html);

    // wire buttons
    const startBtn = document.getElementById('start-btn');
    if(startBtn) startBtn.addEventListener('click', async ()=>{
      try{
        await apiFetch('attendance/start/', { method:'POST' });
        renderDashboard();
      }catch(e){ alert('Start failed'); console.error(e); }
    });
    const breakBtn = document.getElementById('break-btn');
    if(breakBtn) breakBtn.addEventListener('click', async ()=>{
      try{ await apiFetch('attendance/break/toggle/', { method:'POST' }); renderDashboard(); }catch(e){ alert('Break toggle failed'); console.error(e); }
    });
    const endBtn = document.getElementById('end-btn');
    if(endBtn) endBtn.addEventListener('click', async ()=>{
      try{ await apiFetch('attendance/end/', { method:'POST' }); setToken(null); navigateTo('#login'); render(); }catch(e){ alert('End failed'); console.error(e); }
    });

    document.getElementById('download-csv').addEventListener('click', async ()=>{
      try{
        const res = await fetch(API_BASE + 'attendance/export/today/', { headers: { 'Authorization': 'Bearer ' + getToken() }});
        if(!res.ok) { const j = await res.json().catch(()=>null); throw j || 'error'; }
        const blob = await res.blob();
        downloadBlob(blob, `attendance_${new Date().toISOString().slice(0,10)}.csv`);
      }catch(e){ alert('CSV failed'); console.error(e); }
    });
    document.getElementById('save-csv').addEventListener('click', async ()=>{
      try{
        const r = await apiFetch('attendance/export/save/today/', { method:'POST' });
        alert('Saved: ' + r.path);
      }catch(e){ alert('Save failed'); console.error(e); }
    });
    document.getElementById('flush-user').addEventListener('click', async ()=>{
      if(!confirm('Clear your stored attendance data?')) return;
      try{ await apiFetch('attendance/flush/', { method:'POST' }); alert('Flushed your data'); renderDashboard(); }catch(e){ alert('Flush failed'); console.error(e); }
    });

    // check if user is admin (quick ping employee list)
    try{
      await apiFetch('employees/');
      // if succeeds, user is admin
      document.getElementById('admin-link').style.display = 'block';
      document.getElementById('goto-admin').addEventListener('click', ()=>navigateTo('#admin'));
    }catch(err){
      // not admin - ignore
    }

  }catch(err){
    console.error(err);
    if(err.status === 401 || err.status === 403){ setToken(null); navigateTo('#login'); render(); }
    else showError('Failed to load status');
  }
}

// ---- Admin dashboard ----
async function renderAdmin(){
  setMain(`<div class="card"><h3>Admin Dashboard</h3><div id="admin-content">Loading...</div></div>`);
  try{
    const res = await apiFetch('employees/');
    const employees = res.employees || [];
    let html = `<div class="card"><h4>Employees</h4><table class="table"><thead><tr><th>id</th><th>username</th><th>name</th><th>email</th><th>admin?</th><th>actions</th></tr></thead><tbody>`;
    for(const u of employees){
      html += `<tr data-id="${u.id}"><td>${u.id}</td><td>${escapeHtml(u.username)}</td><td>${escapeHtml(u.first_name + ' ' + u.last_name)}</td><td>${escapeHtml(u.email || '')}</td><td>${u.is_staff? 'Yes' : 'No'}</td><td><div class="actions"><button class="view-tracking">View</button><button class="promote">${u.is_staff? 'Demote':'Promote'}</button></div></td></tr>`;
    }
    html += `</tbody></table></div>`;

    // create user form
    html += `<div class="card"><h4>Create user</h4>
      <form id="admin-create">
        <div class="row"><label>Username</label><input id="adm-username" required /></div>
        <div class="row"><label>Password</label><input id="adm-password" required /></div>
        <div class="row"><label>First name</label><input id="adm-first" /></div>
        <div class="row"><label>Last name</label><input id="adm-last" /></div>
        <div class="row"><label>Email</label><input id="adm-email" /></div>
        <div class="row"><label>Make admin?</label><select id="adm-isstaff"><option value="false" selected>No</option><option value="true">Yes</option></select></div>
        <div class="row"><button>Create user</button></div>
      </form></div>`;

    // flush all
    html += `<div class="card"><h4>Danger</h4><div class="actions"><button id="flush-all" class="secondary">Flush ALL stored attendance (admin)</button></div></div>`;

    setMain(html);

    // wire employee table actions
    document.querySelectorAll('.view-tracking').forEach(btn=>{
      btn.addEventListener('click', async (e)=>{
        const id = e.target.closest('tr').dataset.id;
        try{
          const data = await apiFetch(`employees/${id}/tracking/`);
          let out = `<h4>Tracking for ${escapeHtml(data.user.username)}</h4>`;
          out += '<pre>' + escapeHtml(JSON.stringify(data.sessions, null, 2)) + '</pre>';
          const md = document.createElement('div'); md.className='card'; md.innerHTML = out;
          document.querySelector('#admin-content').prepend(md);
        }catch(err){ alert('Failed to fetch tracking'); console.error(err); }
      });
    });

    document.querySelectorAll('.promote').forEach(btn=>{
      btn.addEventListener('click', async (e)=>{
        const tr = e.target.closest('tr'); const id = tr.dataset.id;
        const makeAdmin = e.target.textContent.trim() === 'Promote';
        try{
          await apiFetch(`auth/admin/promote/${id}/`, { method:'POST', body: JSON.stringify({ is_staff: makeAdmin }) });
          alert('Updated');
          renderAdmin();
        }catch(err){ alert('Promote failed'); console.error(err); }
      });
    });

    document.getElementById('admin-create').addEventListener('submit', async (ev)=>{
      ev.preventDefault();
      const payload = {
        username: document.getElementById('adm-username').value.trim(),
        password: document.getElementById('adm-password').value,
        first_name: document.getElementById('adm-first').value.trim(),
        last_name: document.getElementById('adm-last').value.trim(),
        email: document.getElementById('adm-email').value.trim(),
      };
      const isStaff = document.getElementById('adm-isstaff').value === 'true';
      if(isStaff) payload.is_staff = true;
      try{
        await apiFetch('auth/admin/create/', { method:'POST', body: JSON.stringify(payload) });
        alert('User created');
        renderAdmin();
      }catch(err){ alert('Create failed'); console.error(err); }
    });

    document.getElementById('flush-all').addEventListener('click', async ()=>{
      if(!confirm('Flush ALL stored attendance? This cannot be undone.')) return;
      try{ await apiFetch('flush/all/', { method:'POST' }); alert('Flushed all'); renderAdmin(); }catch(err){ alert('Flush all failed'); console.error(err); }
    });

  }catch(err){
    console.error(err);
    if(err.status === 401 || err.status === 403){ setToken(null); navigateTo('#login'); render(); }
    else showError('Failed to load admin data');
  }
}

// ---- App init ----
window.addEventListener('hashchange', render);
window.addEventListener('load', render);
