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
const fmt = h => `${Number(h || 0).toFixed(1)}h`;
const fmtDate = d => d ? new Date(d + 'T00:00:00').toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' }) : '—';

const STATUS_COLOR = { pending: 'warning', approved: 'success', denied: 'danger', cancelled: 'info' };

export default function PTOTracker() {
  const [tab, setTab] = useState('requests');
  const [requests, setRequests] = useState([]);
  const [balances, setBalances] = useState([]);
  const [policies, setPolicies] = useState([]);
  const [employees, setEmployees] = useState([]);
  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState({ employee_id: '', start_date: '', end_date: '', hours: 8, pto_type: 'pto', notes: '' });
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  const load = async () => {
    setLoading(true);
    try {
      const [r, b, p] = await Promise.all([
        req('/pto/requests'),
        req('/pto/balances'),
        req('/pto/policies'),
      ]);
      setRequests(r || []); setBalances(b || []); setPolicies(p || []);
      const emps = await req('/employees?status=active');
      setEmployees(emps.employees || []);
    } catch (e) { setError(e.message); }
    setLoading(false);
  };

  useEffect(() => { load(); }, []);

  const submitRequest = async (e) => {
    e.preventDefault(); setError('');
    try { await req('/pto/requests', { method: 'POST', body: JSON.stringify(form) }); setShowForm(false); load(); }
    catch (err) { setError(err.message); }
  };

  const review = async (id, status) => {
    try { await req(`/pto/requests/${id}/review`, { method: 'PUT', body: JSON.stringify({ status }) }); load(); }
    catch (err) { setError(err.message); }
  };

  const runAccrual = async () => {
    try {
      const today = new Date().toISOString().split('T')[0];
      const r = await req(`/pto/balances/accrue?pay_period_end=${today}`, { method: 'POST' });
      alert(`Accrual complete: ${r.accrued_for} employees, ${r.hours_per_employee}h each`);
      load();
    } catch (err) { setError(err.message); }
  };

  const empMap = Object.fromEntries(employees.map(e => [e.id, e.full_name]));

  return (
    <div className="page">
      <div className="page-header">
        <h1>PTO Tracker</h1>
        <div style={{ display: 'flex', gap: 8 }}>
          <button className="btn" onClick={runAccrual}>↻ Run accrual</button>
          <button className="btn btn-primary" onClick={() => setShowForm(!showForm)}>+ Request PTO</button>
        </div>
      </div>
      {error && <div className="alert alert-danger">{error}</div>}

      <div className="tab-bar">
        {[['requests', 'Requests'], ['balances', 'Balances'], ['policies', 'Policies']].map(([id, label]) => (
          <button key={id} className={`tab-btn ${tab === id ? 'active' : ''}`} onClick={() => setTab(id)}>{label}</button>
        ))}
      </div>

      {showForm && (
        <div className="card" style={{ marginBottom: 16 }}>
          <div className="card-header"><h3>New PTO request</h3><button className="btn btn-sm" onClick={() => setShowForm(false)}>Cancel</button></div>
          <form onSubmit={submitRequest} style={{ padding: 16 }}>
            <div className="form-grid">
              <div className="form-group">
                <label>Employee *</label>
                <select value={form.employee_id} onChange={e => setForm(f => ({ ...f, employee_id: e.target.value }))} required>
                  <option value="">Select…</option>
                  {employees.map(e => <option key={e.id} value={e.id}>{e.full_name}</option>)}
                </select>
              </div>
              <div className="form-group">
                <label>Type</label>
                <select value={form.pto_type} onChange={e => setForm(f => ({ ...f, pto_type: e.target.value }))}>
                  {['pto', 'sick', 'personal', 'bereavement'].map(t => <option key={t} value={t}>{t}</option>)}
                </select>
              </div>
              <div className="form-group"><label>Start date *</label><input type="date" value={form.start_date} onChange={e => setForm(f => ({ ...f, start_date: e.target.value }))} required /></div>
              <div className="form-group"><label>End date *</label><input type="date" value={form.end_date} onChange={e => setForm(f => ({ ...f, end_date: e.target.value }))} required /></div>
              <div className="form-group"><label>Hours requested</label><input type="number" step="0.5" value={form.hours} onChange={e => setForm(f => ({ ...f, hours: Number(e.target.value) }))} /></div>
              <div className="form-group"><label>Notes</label><input type="text" value={form.notes} onChange={e => setForm(f => ({ ...f, notes: e.target.value }))} /></div>
            </div>
            <button className="btn btn-primary" type="submit">Submit request</button>
          </form>
        </div>
      )}

      {tab === 'requests' && (
        <div className="card">
          <table className="table">
            <thead><tr><th>Employee</th><th>Type</th><th>Dates</th><th>Hours</th><th>Status</th><th></th></tr></thead>
            <tbody>
              {loading && <tr><td colSpan={6} className="empty">Loading…</td></tr>}
              {!loading && requests.length === 0 && <tr><td colSpan={6} className="empty">No PTO requests yet</td></tr>}
              {requests.map(r => (
                <tr key={r.id}>
                  <td style={{ fontWeight: 500 }}>{empMap[r.employee_id] || r.employee_id.slice(0, 8)}</td>
                  <td><span className="badge badge-info">{r.pto_type}</span></td>
                  <td style={{ fontSize: 12 }}>{fmtDate(r.start_date)} – {fmtDate(r.end_date)}</td>
                  <td>{fmt(r.hours)}</td>
                  <td><span className={`badge badge-${STATUS_COLOR[r.status]}`}>{r.status}</span></td>
                  <td>
                    {r.status === 'pending' && (
                      <div style={{ display: 'flex', gap: 4 }}>
                        <button className="btn btn-sm" style={{ background: 'var(--green-bg)', color: 'var(--green)' }} onClick={() => review(r.id, 'approved')}>✓</button>
                        <button className="btn btn-sm btn-danger" onClick={() => review(r.id, 'denied')}>✗</button>
                      </div>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {tab === 'balances' && (
        <div className="card">
          <table className="table">
            <thead><tr><th>Employee</th><th>Available</th><th>Pending</th><th>Net available</th><th>Used YTD</th><th>Accrued YTD</th></tr></thead>
            <tbody>
              {loading && <tr><td colSpan={6} className="empty">Loading…</td></tr>}
              {!loading && balances.length === 0 && <tr><td colSpan={6} className="empty">No PTO balances — run accrual to initialize</td></tr>}
              {balances.map(b => (
                <tr key={b.id}>
                  <td style={{ fontWeight: 500 }}>{empMap[b.employee_id] || b.employee_id.slice(0, 8)}</td>
                  <td>{fmt(b.available_hours)}</td>
                  <td style={{ color: 'var(--amber)' }}>{fmt(b.pending_hours)}</td>
                  <td style={{ fontWeight: 600, color: 'var(--green)' }}>{fmt(b.net_available)}</td>
                  <td style={{ color: 'var(--text3)' }}>{fmt(b.used_hours)}</td>
                  <td style={{ color: 'var(--text3)' }}>{fmt(b.ytd_accrued)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {tab === 'policies' && (
        <div className="card">
          <div className="card-header"><h3>PTO policies</h3></div>
          <table className="table">
            <thead><tr><th>Policy</th><th>Accrual rate</th><th>Max accrual</th><th>Carryover</th><th>Waiting period</th><th>Status</th></tr></thead>
            <tbody>
              {policies.length === 0 && <tr><td colSpan={6} className="empty">No policies yet</td></tr>}
              {policies.map(p => (
                <tr key={p.id}>
                  <td style={{ fontWeight: 500 }}>{p.name}</td>
                  <td>{fmt(p.accrual_rate)}/period</td>
                  <td>{fmt(p.max_accrual)}</td>
                  <td>{fmt(p.carryover_limit)}</td>
                  <td>{p.waiting_period_days} days</td>
                  <td><span className={`badge badge-${p.is_active ? 'success' : 'danger'}`}>{p.is_active ? 'Active' : 'Inactive'}</span></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
