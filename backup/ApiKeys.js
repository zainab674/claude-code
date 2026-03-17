import React, { useState, useEffect } from 'react';

const BASE = process.env.REACT_APP_API_URL || 'http://localhost:8000';
const tkn = () => localStorage.getItem('payroll_token');
async function req(path, opts = {}) {
  const res = await fetch(`${BASE}${path}`, {
    ...opts, headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${tkn()}`, ...opts.headers },
  });
  if (!res.ok) { const e = await res.json().catch(() => ({ detail: res.statusText })); throw new Error(e.detail); }
  if (res.status === 204) return null;
  return res.json();
}

export default function ApiKeys() {
  const [keys, setKeys] = useState([]);
  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState({ name: '', environment: 'live', scopes: '*', expires_days: '' });
  const [newKey, setNewKey] = useState(null);
  const [copied, setCopied] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  const load = async () => {
    setLoading(true);
    try { setKeys(await req('/api-keys') || []); }
    catch (e) { setError(e.message); }
    setLoading(false);
  };

  useEffect(() => { load(); }, []);

  const create = async (e) => {
    e.preventDefault(); setError('');
    try {
      const body = { ...form, expires_days: form.expires_days ? Number(form.expires_days) : null };
      const r = await req('/api-keys', { method: 'POST', body: JSON.stringify(body) });
      setNewKey(r);
      setShowForm(false);
      setForm({ name: '', environment: 'live', scopes: '*', expires_days: '' });
      load();
    } catch (err) { setError(err.message); }
  };

  const revoke = async (id) => {
    if (!window.confirm('Revoke this API key? This cannot be undone.')) return;
    try { await req(`/api-keys/${id}`, { method: 'DELETE' }); load(); }
    catch (err) { setError(err.message); }
  };

  const copy = (text) => {
    navigator.clipboard.writeText(text);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <div className="page">
      <div className="page-header">
        <h1>API Keys <span className="count-badge">{keys.length}</span></h1>
        <button className="btn btn-primary" onClick={() => setShowForm(!showForm)}>+ Create key</button>
      </div>
      {error && <div className="alert alert-danger">{error}</div>}

      {/* New key reveal */}
      {newKey && (
        <div className="card" style={{ marginBottom: 16, border: '1px solid var(--green)' }}>
          <div className="card-header" style={{ background: 'var(--green-bg)' }}>
            <h3 style={{ color: 'var(--green)' }}>✓ API key created — copy it now</h3>
            <button className="btn btn-sm" onClick={() => setNewKey(null)}>Dismiss</button>
          </div>
          <div style={{ padding: 16 }}>
            <p style={{ fontSize: 13, color: 'var(--red)', marginBottom: 10 }}>
              This key will <strong>never be shown again</strong>. Copy it now and store it securely.
            </p>
            <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
              <code style={{ flex: 1, padding: '10px 12px', background: 'var(--bg3)', borderRadius: 6, fontSize: 12, wordBreak: 'break-all', border: '1px solid var(--border)' }}>
                {newKey.key}
              </code>
              <button className="btn btn-primary" onClick={() => copy(newKey.key)}>
                {copied ? '✓ Copied' : 'Copy'}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Create form */}
      {showForm && (
        <div className="card" style={{ marginBottom: 16 }}>
          <div className="card-header"><h3>Create API key</h3><button className="btn btn-sm" onClick={() => setShowForm(false)}>Cancel</button></div>
          <form onSubmit={create} style={{ padding: 16 }}>
            <div className="form-grid">
              <div className="form-group">
                <label>Key name *</label>
                <input type="text" value={form.name} onChange={e => setForm(f => ({ ...f, name: e.target.value }))}
                  placeholder="e.g. HR System Integration" required />
              </div>
              <div className="form-group">
                <label>Environment</label>
                <select value={form.environment} onChange={e => setForm(f => ({ ...f, environment: e.target.value }))}>
                  <option value="live">Live</option>
                  <option value="test">Test</option>
                </select>
              </div>
              <div className="form-group">
                <label>Scopes</label>
                <input type="text" value={form.scopes} onChange={e => setForm(f => ({ ...f, scopes: e.target.value }))}
                  placeholder="* for all, or: employees,payroll,reports" />
              </div>
              <div className="form-group">
                <label>Expires in (days, leave blank = never)</label>
                <input type="number" value={form.expires_days} onChange={e => setForm(f => ({ ...f, expires_days: e.target.value }))}
                  placeholder="e.g. 365" min="1" />
              </div>
            </div>
            <button className="btn btn-primary" type="submit">Create key</button>
          </form>
        </div>
      )}

      {/* Keys list */}
      <div className="card">
        <table className="table">
          <thead><tr><th>Name</th><th>Key prefix</th><th>Environment</th><th>Scopes</th><th>Last used</th><th>Expires</th><th>Status</th><th></th></tr></thead>
          <tbody>
            {loading && <tr><td colSpan={8} className="empty">Loading…</td></tr>}
            {!loading && keys.length === 0 && (
              <tr><td colSpan={8} className="empty">No API keys — create one to integrate external systems</td></tr>
            )}
            {keys.map(k => (
              <tr key={k.id}>
                <td style={{ fontWeight: 500 }}>{k.name}</td>
                <td><code style={{ fontSize: 11 }}>{k.key_prefix}</code></td>
                <td><span className={`badge badge-${k.environment === 'live' ? 'danger' : 'info'}`}>{k.environment}</span></td>
                <td style={{ fontSize: 12, color: 'var(--text3)' }}>{k.scopes}</td>
                <td style={{ fontSize: 12, color: 'var(--text3)' }}>{k.last_used ? new Date(k.last_used).toLocaleDateString() : 'Never'}</td>
                <td style={{ fontSize: 12, color: k.expires_at ? 'var(--amber)' : 'var(--text3)' }}>{k.expires_at ? new Date(k.expires_at).toLocaleDateString() : 'Never'}</td>
                <td><span className={`badge badge-${k.is_active ? 'success' : 'danger'}`}>{k.is_active ? 'Active' : 'Revoked'}</span></td>
                <td>{k.is_active && <button className="btn btn-sm btn-danger" onClick={() => revoke(k.id)}>Revoke</button>}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="card">
        <div className="card-header"><h3>Using API keys</h3></div>
        <div style={{ padding: 16, fontSize: 13, color: 'var(--text2)', lineHeight: 1.8 }}>
          <div>Include the key in the <code>X-API-Key</code> header on every request:</div>
          <pre style={{ marginTop: 8, background: 'var(--bg3)', padding: 12, borderRadius: 6, fontSize: 12 }}>
{`curl https://api.your-domain.com/employees \\
  -H "X-API-Key: pk_live_your_key_here"`}
          </pre>
          <div style={{ marginTop: 12 }}>API keys work alongside JWT tokens. Use keys for server-to-server integrations (HRIS, accounting software, etc.) and JWT tokens for user-facing sessions.</div>
        </div>
      </div>
    </div>
  );
}
