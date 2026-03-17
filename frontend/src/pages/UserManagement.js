import React, { useState, useEffect } from 'react';

const BASE = process.env.REACT_APP_API_URL || 'http://localhost:8000';
const tkn = () => localStorage.getItem('payroll_token');

async function req(path, opts = {}) {
  const res = await fetch(`${BASE}${path}`, {
    ...opts,
    headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${tkn()}`, ...opts.headers },
  });
  if (!res.ok) { const e = await res.json().catch(() => ({ detail: res.statusText })); throw new Error(e.detail); }
  if (res.status === 204) return null;
  return res.json();
}

const ROLE_COLORS = { admin: 'danger', manager: 'warning', viewer: 'info' };

export default function UserManagement() {
  const [users, setUsers] = useState([]);
  const [me, setMe] = useState(null);
  const [showInvite, setShowInvite] = useState(false);
  const [showProfile, setShowProfile] = useState(false);
  const [invite, setInvite] = useState({ email: '', first_name: '', last_name: '', role: 'viewer', temp_password: 'ChangeMe123!' });
  const [profile, setProfile] = useState({ first_name: '', last_name: '', current_password: '', new_password: '' });
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [success, setSuccess] = useState('');
  const [newUser, setNewUser] = useState(null);

  const load = async () => {
    setLoading(true);
    try {
      const [u, m] = await Promise.all([req('/users'), req('/users/me')]);
      setUsers(u || []);
      setMe(m);
      setProfile({ first_name: m.first_name || '', last_name: m.last_name || '', current_password: '', new_password: '' });
    } catch (e) { setError(e.message); }
    setLoading(false);
  };

  useEffect(() => { load(); }, []);

  const doInvite = async (e) => {
    e.preventDefault(); setError(''); setSuccess('');
    try {
      const res = await req('/users/invite', { method: 'POST', body: JSON.stringify(invite) });
      setNewUser(res);
      setShowInvite(false);
      setInvite({ email: '', first_name: '', last_name: '', role: 'viewer', temp_password: 'ChangeMe123!' });
      load();
    } catch (err) { setError(err.message); }
  };

  const doProfile = async (e) => {
    e.preventDefault(); setError(''); setSuccess('');
    try {
      await req('/users/me', { method: 'PUT', body: JSON.stringify(profile) });
      setSuccess('Profile updated');
      setShowProfile(false);
      load();
    } catch (err) { setError(err.message); }
  };

  const toggleActive = async (user) => {
    try {
      await req(`/users/${user.id}`, { method: 'PUT', body: JSON.stringify({ is_active: !user.is_active }) });
      load();
    } catch (err) { setError(err.message); }
  };

  const changeRole = async (user, role) => {
    try {
      await req(`/users/${user.id}`, { method: 'PUT', body: JSON.stringify({ role }) });
      load();
    } catch (err) { setError(err.message); }
  };

  return (
    <div className="page">
      <div className="page-header">
        <h1>Team & Users <span className="count-badge">{users.length}</span></h1>
        <div style={{ display: 'flex', gap: 8 }}>
          <button className="btn" onClick={() => setShowProfile(!showProfile)}>My profile</button>
          {/* <button className="btn btn-primary" onClick={() => setShowInvite(!showInvite)}>+ Invite user</button> */}
        </div>
      </div>

      {error && <div className="alert alert-danger">{error}</div>}
      {success && <div className="alert" style={{ background: 'var(--green-bg)', color: 'var(--green)', border: '1px solid #b2dfb2', padding: '10px 14px', borderRadius: 6, marginBottom: 12, fontSize: 13 }}>✓ {success}</div>}

      {/* New user credentials */}
      {newUser && (
        <div className="card" style={{ marginBottom: 16, border: '1px solid var(--color-border-success)' }}>
          <div className="card-header" style={{ background: 'var(--green-bg)' }}>
            <h3 style={{ color: 'var(--green)' }}>✓ User invited — share these credentials</h3>
            <button className="btn btn-sm" onClick={() => setNewUser(null)}>Dismiss</button>
          </div>
          <div style={{ padding: 16, fontFamily: 'monospace', fontSize: 13 }}>
            <div>Email: <strong>{newUser.email}</strong></div>
            <div>Temp password: <strong>{newUser.temp_password}</strong></div>
            <div style={{ marginTop: 8, fontSize: 11, color: 'var(--text3)' }}>
              The user should change their password on first login.
            </div>
          </div>
        </div>
      )}

      {/* Invite form */}
      {showInvite && (
        <div className="card" style={{ marginBottom: 16 }}>
          <div className="card-header"><h3>Invite new user</h3><button className="btn btn-sm" onClick={() => setShowInvite(false)}>Cancel</button></div>
          <form onSubmit={doInvite} style={{ padding: 16 }}>
            <div className="form-grid">
              {[['First name','first_name','text'],['Last name','last_name','text'],['Email','email','email'],['Temp password','temp_password','text']].map(([label, key, type]) => (
                <div className="form-group" key={key}>
                  <label>{label}</label>
                  <input type={type} value={invite[key]} onChange={e => setInvite(i => ({ ...i, [key]: e.target.value }))} required />
                </div>
              ))}
              <div className="form-group">
                <label>Role</label>
                <select value={invite.role} onChange={e => setInvite(i => ({ ...i, role: e.target.value }))}>
                  <option value="viewer">Viewer — read-only</option>
                  <option value="manager">Manager — run payroll</option>
                  <option value="admin">Admin — full access</option>
                </select>
              </div>
            </div>
            <button className="btn btn-primary" type="submit">Send invite</button>
          </form>
        </div>
      )}

      {/* Profile edit */}
      {showProfile && me && (
        <div className="card" style={{ marginBottom: 16 }}>
          <div className="card-header"><h3>My profile</h3><button className="btn btn-sm" onClick={() => setShowProfile(false)}>Cancel</button></div>
          <form onSubmit={doProfile} style={{ padding: 16 }}>
            <div className="form-grid">
              <div className="form-group"><label>First name</label><input type="text" value={profile.first_name} onChange={e => setProfile(p => ({ ...p, first_name: e.target.value }))} /></div>
              <div className="form-group"><label>Last name</label><input type="text" value={profile.last_name} onChange={e => setProfile(p => ({ ...p, last_name: e.target.value }))} /></div>
              <div className="form-group"><label>Current password</label><input type="password" value={profile.current_password} onChange={e => setProfile(p => ({ ...p, current_password: e.target.value }))} placeholder="Only if changing password" /></div>
              <div className="form-group"><label>New password</label><input type="password" value={profile.new_password} onChange={e => setProfile(p => ({ ...p, new_password: e.target.value }))} placeholder="Leave blank to keep current" /></div>
            </div>
            <button className="btn btn-primary" type="submit">Save changes</button>
          </form>
        </div>
      )}

      {/* Users table */}
      <div className="card">
        <table className="table">
          <thead><tr><th>Name</th><th>Email</th><th>Role</th><th>Status</th><th>Joined</th><th></th></tr></thead>
          <tbody>
            {loading && <tr><td colSpan={6} className="empty">Loading…</td></tr>}
            {users.map(u => (
              <tr key={u.id} style={{ opacity: u.is_active ? 1 : 0.5 }}>
                <td>
                  <div style={{ fontWeight: 500 }}>{u.first_name} {u.last_name}</div>
                  {me?.id === u.id && <div style={{ fontSize: 11, color: 'var(--text3)' }}>You</div>}
                </td>
                <td style={{ fontSize: 13 }}>{u.email}</td>
                <td>
                  <select
                    className="badge"
                    style={{ background: 'none', border: '1px solid var(--border)', padding: '2px 6px', fontSize: 11, cursor: 'pointer' }}
                    value={u.role}
                    onChange={e => changeRole(u, e.target.value)}
                    disabled={me?.id === u.id}
                  >
                    <option value="admin">admin</option>
                    <option value="manager">manager</option>
                    <option value="viewer">viewer</option>
                  </select>
                </td>
                <td><span className={`badge badge-${u.is_active ? 'success' : 'danger'}`}>{u.is_active ? 'Active' : 'Inactive'}</span></td>
                <td style={{ fontSize: 12, color: 'var(--text3)' }}>{u.created_at ? new Date(u.created_at).toLocaleDateString() : '—'}</td>
                <td>
                  {me?.id !== u.id && (
                    <button className={`btn btn-sm ${u.is_active ? 'btn-danger' : ''}`} onClick={() => toggleActive(u)}>
                      {u.is_active ? 'Deactivate' : 'Reactivate'}
                    </button>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* Role guide */}
      <div className="card">
        <div className="card-header"><h3>Role permissions</h3></div>
        <div style={{ padding: 16 }}>
          <table className="table" style={{ fontSize: 12 }}>
            <thead><tr><th>Permission</th><th>Viewer</th><th>Manager</th><th>Admin</th></tr></thead>
            <tbody>
              {[
                ['View dashboard & reports', '✓', '✓', '✓'],
                ['View employees', '✓', '✓', '✓'],
                ['Add / edit employees', '', '✓', '✓'],
                ['Run payroll preview', '', '✓', '✓'],
                ['Approve & run payroll', '', '✓', '✓'],
                ['Download paystubs', '✓', '✓', '✓'],
                ['Export CSV', '', '✓', '✓'],
                ['Import employees', '', '✓', '✓'],
                ['Manage webhooks', '', '', '✓'],
                ['Manage users', '', '', '✓'],
                ['Edit company settings', '', '', '✓'],
              ].map(([perm, ...roles]) => (
                <tr key={perm}>
                  <td>{perm}</td>
                  {roles.map((r, i) => (
                    <td key={i} style={{ textAlign: 'center', color: r ? 'var(--green)' : 'var(--text3)' }}>{r || '—'}</td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
