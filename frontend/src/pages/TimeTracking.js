import React, { useState, useEffect, useCallback } from 'react';
import * as api from '../services/api';

const today = () => new Date().toISOString().split('T')[0];
const fmtDate = (d) => d ? new Date(d).toLocaleDateString('en-US', { month: 'short', day: 'numeric' }) : '—';
const fmtHrs = (h) => `${Number(h || 0).toFixed(2)}h`;
const STATUS_COLOR = { pending: 'warning', approved: 'success', rejected: 'danger' };

export default function TimeTracking() {
  const [employees, setEmployees] = useState([]);
  const [entries, setEntries] = useState([]);
  const [filters, setFilters] = useState({ employee_id: '', start_date: today(), end_date: today() });
  const [form, setForm] = useState({ employee_id: '', entry_date: today(), regular_hours: 8, overtime_hours: 0, notes: '' });
  const [showForm, setShowForm] = useState(false);
  const [summary, setSummary] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  useEffect(() => {
    api.getEmployees({ status: 'active' }).then(r => setEmployees(r.employees || []));
  }, []);

  const loadEntries = useCallback(async () => {
    setLoading(true);
    try {
      const r = await api.getTimeEntries({
        employee_id: filters.employee_id || undefined,
        start_date: filters.start_date || undefined,
        end_date: filters.end_date || undefined,
      });
      setEntries(Array.isArray(r) ? r : r.entries || []);
    } catch (e) { setError(e.message); }
    setLoading(false);
  }, [filters]);

  useEffect(() => { loadEntries(); }, [loadEntries]);

  const loadSummary = async () => {
    if (!filters.employee_id) return;
    try {
      const r = await api.getTimeSummary({
        employee_id: filters.employee_id,
        start_date: filters.start_date,
        end_date: filters.end_date,
      });
      setSummary(r);
    } catch { setSummary(null); }
  };

  const submit = async (e) => {
    e.preventDefault(); setError('');
    try {
      await api.createTimeEntry(form);
      setShowForm(false);
      setForm({ employee_id: '', entry_date: today(), regular_hours: 8, overtime_hours: 0, notes: '' });
      loadEntries();
    } catch (err) { setError(err.message); }
  };

  const approve = async (id) => {
    try { await api.approveTimeEntry(id); loadEntries(); }
    catch (err) { setError(err.message); }
  };

  const del = async (id) => {
    if (!window.confirm('Delete this entry?')) return;
    try { await api.deleteTimeEntry(id); loadEntries(); }
    catch (err) { setError(err.message); }
  };

  const empMap = Object.fromEntries(employees.map(e => [e.id, e.full_name]));
  const totalRegular = entries.reduce((s, e) => s + Number(e.regular_hours || 0), 0);
  const totalOT = entries.reduce((s, e) => s + Number(e.overtime_hours || 0), 0);
  const pending = entries.filter(e => e.status === 'pending').length;

  return (
    <div className="page">
      <div className="page-header">
        <h1>Time Tracking</h1>
        <button className="btn btn-primary" onClick={() => setShowForm(!showForm)}>+ Add entry</button>
      </div>
      {error && <div className="alert alert-danger">{error}</div>}

      {/* Filters */}
      <div className="card" style={{ marginBottom: 16 }}>
        <div style={{ padding: '12px 16px', display: 'flex', gap: 12, flexWrap: 'wrap', alignItems: 'flex-end' }}>
          <div className="form-group" style={{ margin: 0, minWidth: 180 }}>
            <label style={{ fontSize: 11 }}>Employee</label>
            <select value={filters.employee_id} onChange={e => setFilters(f => ({ ...f, employee_id: e.target.value }))}>
              <option value="">All employees</option>
              {employees.map(e => <option key={e.id} value={e.id}>{e.full_name}</option>)}
            </select>
          </div>
          <div className="form-group" style={{ margin: 0 }}>
            <label style={{ fontSize: 11 }}>From</label>
            <input type="date" value={filters.start_date} onChange={e => setFilters(f => ({ ...f, start_date: e.target.value }))} />
          </div>
          <div className="form-group" style={{ margin: 0 }}>
            <label style={{ fontSize: 11 }}>To</label>
            <input type="date" value={filters.end_date} onChange={e => setFilters(f => ({ ...f, end_date: e.target.value }))} />
          </div>
          <button className="btn" onClick={() => { loadEntries(); loadSummary(); }}>Apply</button>
        </div>
        {entries.length > 0 && (
          <div style={{ padding: '0 16px 12px', display: 'flex', gap: 24, fontSize: 13 }}>
            <span style={{ color: 'var(--text2)' }}>{entries.length} entries</span>
            <span>Regular: <strong>{fmtHrs(totalRegular)}</strong></span>
            <span>Overtime: <strong style={{ color: totalOT > 0 ? 'var(--amber)' : 'inherit' }}>{fmtHrs(totalOT)}</strong></span>
            {pending > 0 && <span style={{ color: 'var(--amber)' }}>⚠ {pending} pending approval</span>}
          </div>
        )}
      </div>

      {/* Add entry form */}
      {showForm && (
        <div className="card" style={{ marginBottom: 16 }}>
          <div className="card-header"><h3>Add time entry</h3><button className="btn btn-sm" onClick={() => setShowForm(false)}>Cancel</button></div>
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
                <label>Date *</label>
                <input type="date" value={form.entry_date} onChange={e => setForm(f => ({ ...f, entry_date: e.target.value }))} required />
              </div>
              <div className="form-group">
                <label>Regular hours</label>
                <input type="number" step="0.25" min="0" max="24" value={form.regular_hours}
                  onChange={e => setForm(f => ({ ...f, regular_hours: Number(e.target.value) }))} />
              </div>
              <div className="form-group">
                <label>Overtime hours</label>
                <input type="number" step="0.25" min="0" max="24" value={form.overtime_hours}
                  onChange={e => setForm(f => ({ ...f, overtime_hours: Number(e.target.value) }))} />
              </div>
              <div className="form-group" style={{ gridColumn: '1/-1' }}>
                <label>Notes</label>
                <input type="text" value={form.notes} onChange={e => setForm(f => ({ ...f, notes: e.target.value }))} />
              </div>
            </div>
            <button className="btn btn-primary" type="submit">Save entry</button>
          </form>
        </div>
      )}

      {/* Entries table */}
      <div className="card">
        <table className="table">
          <thead>
            <tr><th>Employee</th><th>Date</th><th>Regular</th><th>Overtime</th><th>Total</th><th>Status</th><th></th></tr>
          </thead>
          <tbody>
            {loading && <tr><td colSpan={7} className="empty">Loading…</td></tr>}
            {!loading && entries.length === 0 && (
              <tr><td colSpan={7} className="empty">No time entries for this period</td></tr>
            )}
            {entries.map(e => (
              <tr key={e.id}>
                <td style={{ fontWeight: 500 }}>{empMap[e.employee_id] || e.employee_id?.slice(0, 8)}</td>
                <td style={{ fontSize: 12 }}>{fmtDate(e.entry_date)}</td>
                <td>{fmtHrs(e.regular_hours)}</td>
                <td style={{ color: Number(e.overtime_hours) > 0 ? 'var(--amber)' : 'inherit' }}>
                  {fmtHrs(e.overtime_hours)}
                </td>
                <td style={{ fontWeight: 500 }}>
                  {fmtHrs(Number(e.regular_hours) + Number(e.overtime_hours))}
                </td>
                <td><span className={`badge badge-${STATUS_COLOR[e.status] || 'info'}`}>{e.status}</span></td>
                <td>
                  <div style={{ display: 'flex', gap: 4 }}>
                    {e.status === 'pending' && (
                      <button className="btn btn-sm" style={{ color: 'var(--green)' }} onClick={() => approve(e.id)}>✓</button>
                    )}
                    <button className="btn btn-sm btn-danger" onClick={() => del(e.id)}>✗</button>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
