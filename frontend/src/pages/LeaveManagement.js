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
const fmtDate = d => d ? new Date(d + 'T00:00:00').toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' }) : '—';
const STATUS_COLOR = { pending: 'warning', approved: 'success', active: 'info', completed: 'info', denied: 'danger' };

export default function LeaveManagement() {
  const [tab, setTab] = useState('active');
  const [leaveTypes, setLeaveTypes] = useState([]);
  const [records, setRecords] = useState([]);
  const [activeToday, setActiveToday] = useState(null);
  const [employees, setEmployees] = useState([]);
  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState({ employee_id: '', leave_type: 'fmla', start_date: '', expected_return: '', reason: '', is_paid: null, intermittent: false });
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(true);

  const load = async () => {
    setLoading(true);
    try {
      const [types, active, emps] = await Promise.all([
        req('/leave/types'),
        req('/leave/active'),
        req('/employees?status=active'),
      ]);
      setLeaveTypes(types || []);
      setActiveToday(active);
      setEmployees(emps?.employees || []);
      const all = await req('/leave');
      setRecords(all || []);
    } catch (e) { setError(e.message); }
    setLoading(false);
  };

  useEffect(() => { load(); }, []);

  const submit = async (e) => {
    e.preventDefault(); setError('');
    try {
      await req('/leave', { method: 'POST', body: JSON.stringify({ ...form, is_paid: form.is_paid === '' ? null : form.is_paid }) });
      setShowForm(false);
      setForm({ employee_id: '', leave_type: 'fmla', start_date: '', expected_return: '', reason: '', is_paid: null, intermittent: false });
      load();
    } catch (err) { setError(err.message); }
  };

  const review = async (id, status) => {
    try { await req(`/leave/${id}/review`, { method: 'PUT', body: JSON.stringify({ status }) }); load(); }
    catch (err) { setError(err.message); }
  };

  const empMap = Object.fromEntries(employees.map(e => [e.id, e.full_name]));
  const filtered = tab === 'active'
    ? records.filter(r => ['pending', 'approved', 'active'].includes(r.status))
    : tab === 'history'
    ? records.filter(r => ['completed', 'denied'].includes(r.status))
    : records;

  return (
    <div className="page">
      <div className="page-header">
        <h1>Leave Management</h1>
        <button className="btn btn-primary" onClick={() => setShowForm(!showForm)}>+ New leave request</button>
      </div>
      {error && <div className="alert alert-danger">{error}</div>}

      {/* Active now banner */}
      {activeToday && activeToday.count > 0 && (
        <div className="card" style={{ marginBottom: 16, border: '1px solid var(--amber)', background: 'var(--amber-bg)' }}>
          <div style={{ padding: '12px 16px', display: 'flex', alignItems: 'center', gap: 12 }}>
            <span style={{ fontSize: 18 }}>📅</span>
            <span style={{ fontWeight: 500, color: 'var(--amber)' }}>{activeToday.count} employee{activeToday.count > 1 ? 's' : ''} on leave today</span>
            <span style={{ fontSize: 12, color: 'var(--amber)' }}>
              {activeToday.employees_on_leave.map(r => empMap[r.employee_id] || 'Unknown').join(', ')}
            </span>
          </div>
        </div>
      )}

      {/* New leave form */}
      {showForm && (
        <div className="card" style={{ marginBottom: 16 }}>
          <div className="card-header"><h3>New leave request</h3><button className="btn btn-sm" onClick={() => setShowForm(false)}>Cancel</button></div>
          <form onSubmit={submit} style={{ padding: 16 }}>
            <div className="form-grid">
              <div className="form-group">
                <label>Employee *</label>
                <select value={form.employee_id} onChange={e => setForm(f => ({ ...f, employee_id: e.target.value }))} required>
                  <option value="">Select…</option>
                  {employees.map(e => <option key={e.id} value={e.id}>{e.full_name}</option>)}
                </select>
              </div>
              <div className="form-group">
                <label>Leave type *</label>
                <select value={form.leave_type} onChange={e => setForm(f => ({ ...f, leave_type: e.target.value }))}>
                  {leaveTypes.map(t => <option key={t.key} value={t.key}>{t.label} {t.paid ? '(paid)' : '(unpaid)'}</option>)}
                </select>
              </div>
              <div className="form-group"><label>Start date *</label><input type="date" value={form.start_date} onChange={e => setForm(f => ({ ...f, start_date: e.target.value }))} required /></div>
              <div className="form-group"><label>Expected return</label><input type="date" value={form.expected_return} onChange={e => setForm(f => ({ ...f, expected_return: e.target.value }))} /></div>
              <div className="form-group" style={{ gridColumn: '1/-1' }}>
                <label>Reason</label>
                <input type="text" value={form.reason} onChange={e => setForm(f => ({ ...f, reason: e.target.value }))} />
              </div>
              <div className="form-group" style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                <input type="checkbox" id="intermittent" checked={form.intermittent} onChange={e => setForm(f => ({ ...f, intermittent: e.target.checked }))} style={{ width: 'auto' }} />
                <label htmlFor="intermittent" style={{ cursor: 'pointer' }}>Intermittent leave</label>
              </div>
            </div>
            <button className="btn btn-primary" type="submit">Submit request</button>
          </form>
        </div>
      )}

      <div className="tab-bar">
        {[['active', 'Active'], ['history', 'History'], ['all', 'All']].map(([id, label]) => (
          <button key={id} className={`tab-btn ${tab === id ? 'active' : ''}`} onClick={() => setTab(id)}>{label}</button>
        ))}
      </div>

      <div className="card">
        <table className="table">
          <thead><tr><th>Employee</th><th>Type</th><th>Start</th><th>Return</th><th>Days</th><th>Paid</th><th>Status</th><th></th></tr></thead>
          <tbody>
            {loading && <tr><td colSpan={8} className="empty">Loading…</td></tr>}
            {!loading && filtered.length === 0 && <tr><td colSpan={8} className="empty">No leave records</td></tr>}
            {filtered.map(r => (
              <tr key={r.id}>
                <td style={{ fontWeight: 500 }}>{empMap[r.employee_id] || r.employee_id.slice(0, 8)}</td>
                <td><span className="badge badge-info">{r.leave_label}</span></td>
                <td style={{ fontSize: 12 }}>{fmtDate(r.start_date)}</td>
                <td style={{ fontSize: 12 }}>{fmtDate(r.actual_return || r.expected_return)}</td>
                <td style={{ color: 'var(--text3)' }}>{r.duration_days ? `${r.duration_days}d` : '—'}</td>
                <td>{r.is_paid ? <span className="badge badge-success">Paid</span> : <span className="badge badge-warning">Unpaid</span>}</td>
                <td><span className={`badge badge-${STATUS_COLOR[r.status] || 'info'}`}>{r.status}</span></td>
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

      {/* Leave type reference */}
      <div className="card">
        <div className="card-header"><h3>Leave types reference</h3></div>
        <table className="table" style={{ fontSize: 12 }}>
          <thead><tr><th>Type</th><th>Max weeks</th><th>Paid</th></tr></thead>
          <tbody>
            {leaveTypes.map(t => (
              <tr key={t.key}>
                <td style={{ fontWeight: 500 }}>{t.label}</td>
                <td>{t.max_weeks} weeks</td>
                <td>{t.paid ? <span className="badge badge-success">Paid</span> : <span className="badge badge-warning">Unpaid</span>}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
