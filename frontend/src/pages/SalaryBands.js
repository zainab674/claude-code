import React, { useState, useEffect } from 'react';

const BASE = process.env.REACT_APP_API_URL || 'http://localhost:8000';
const tkn = () => localStorage.getItem('payroll_token');
async function req(path, opts = {}) {
  const res = await fetch(`${BASE}${path}`, {
    ...opts, headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${tkn()}`, ...opts.headers },
  });
  if (!res.ok) { const e = await res.json().catch(() => ({ detail: res.statusText })); throw new Error(e.detail); }
  return res.json();
}
const fmt = n => `$${Number(n || 0).toLocaleString()}`;

function CompaRatioBadge({ ratio }) {
  if (!ratio) return <span className="badge badge-info">No band</span>;
  if (ratio < 80)  return <span className="badge badge-danger">{ratio}% below</span>;
  if (ratio > 120) return <span className="badge badge-warning">{ratio}% above</span>;
  return <span className="badge badge-success">{ratio}% in band</span>;
}

export default function SalaryBands() {
  const [tab, setTab] = useState('analysis');
  const [bands, setBands] = useState([]);
  const [analysis, setAnalysis] = useState(null);
  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState({ job_title: '', department: '', level: '', min_salary: '', mid_salary: '', max_salary: '', notes: '' });
  const [error, setError] = useState('');

  const load = async () => {
    const [b, a] = await Promise.all([req('/salary-bands'), req('/salary-bands/analysis')]);
    setBands(b || []); setAnalysis(a);
  };
  useEffect(() => { load(); }, []);

  const save = async (e) => {
    e.preventDefault(); setError('');
    try {
      await req('/salary-bands', { method: 'POST', body: JSON.stringify({ ...form, min_salary: Number(form.min_salary), mid_salary: form.mid_salary ? Number(form.mid_salary) : null, max_salary: Number(form.max_salary) }) });
      setShowForm(false);
      setForm({ job_title: '', department: '', level: '', min_salary: '', mid_salary: '', max_salary: '', notes: '' });
      load();
    } catch (err) { setError(err.message); }
  };

  return (
    <div className="page">
      <div className="page-header">
        <h1>Salary Bands & Pay Equity</h1>
        <button className="btn btn-primary" onClick={() => setShowForm(!showForm)}>+ Add band</button>
      </div>
      {error && <div className="alert alert-danger">{error}</div>}

      {analysis && (
        <div className="metrics-grid" style={{ marginBottom: 16 }}>
          <div className="metric-card"><div className="metric-label">In band</div><div className="metric-value" style={{ color: 'var(--green)' }}>{analysis.in_band}</div><div className="metric-delta">{analysis.in_band_pct}% of employees</div></div>
          <div className="metric-card"><div className="metric-label">Below band</div><div className="metric-value" style={{ color: 'var(--red)' }}>{analysis.below_band}</div><div className="metric-delta">Potential underpaid</div></div>
          <div className="metric-card"><div className="metric-label">Above band</div><div className="metric-value" style={{ color: 'var(--amber)' }}>{analysis.above_band}</div><div className="metric-delta">Review at next cycle</div></div>
          <div className="metric-card"><div className="metric-label">No band defined</div><div className="metric-value">{analysis.no_band_defined}</div><div className="metric-delta">Create bands for these roles</div></div>
        </div>
      )}

      <div className="tab-bar">
        {[['analysis','Pay equity analysis'],['bands','Band definitions']].map(([id, label]) => (
          <button key={id} className={`tab-btn ${tab === id ? 'active' : ''}`} onClick={() => setTab(id)}>{label}</button>
        ))}
      </div>

      {showForm && (
        <div className="card" style={{ marginBottom: 16 }}>
          <div className="card-header"><h3>New salary band</h3><button className="btn btn-sm" onClick={() => setShowForm(false)}>Cancel</button></div>
          <form onSubmit={save} style={{ padding: 16 }}>
            <div className="form-grid">
              <div className="form-group"><label>Job title</label><input type="text" value={form.job_title} onChange={e => setForm(f => ({ ...f, job_title: e.target.value }))} placeholder="e.g. Senior Engineer" /></div>
              <div className="form-group"><label>Department</label><input type="text" value={form.department} onChange={e => setForm(f => ({ ...f, department: e.target.value }))} /></div>
              <div className="form-group"><label>Level</label><input type="text" value={form.level} onChange={e => setForm(f => ({ ...f, level: e.target.value }))} placeholder="IC3, Senior, Staff…" /></div>
              <div className="form-group"><label>Min salary ($) *</label><input type="number" value={form.min_salary} onChange={e => setForm(f => ({ ...f, min_salary: e.target.value }))} required /></div>
              <div className="form-group"><label>Mid salary ($)</label><input type="number" value={form.mid_salary} onChange={e => setForm(f => ({ ...f, mid_salary: e.target.value }))} placeholder="Market rate" /></div>
              <div className="form-group"><label>Max salary ($) *</label><input type="number" value={form.max_salary} onChange={e => setForm(f => ({ ...f, max_salary: e.target.value }))} required /></div>
              <div className="form-group" style={{ gridColumn: '1/-1' }}><label>Notes</label><input type="text" value={form.notes} onChange={e => setForm(f => ({ ...f, notes: e.target.value }))} /></div>
            </div>
            <button className="btn btn-primary" type="submit">Save band</button>
          </form>
        </div>
      )}

      {tab === 'analysis' && analysis && (
        <div className="card">
          <table className="table">
            <thead><tr><th>Employee</th><th>Dept</th><th>Title</th><th>Salary</th><th>Band range</th><th>Compa-ratio</th></tr></thead>
            <tbody>
              {analysis.employees.length === 0 && <tr><td colSpan={6} className="empty">No salaried employees</td></tr>}
              {analysis.employees.map(e => (
                <tr key={e.employee_id}>
                  <td style={{ fontWeight: 500 }}>{e.name}</td>
                  <td style={{ color: 'var(--text3)', fontSize: 12 }}>{e.department || '—'}</td>
                  <td style={{ fontSize: 12 }}>{e.job_title || '—'}</td>
                  <td style={{ fontWeight: 500 }}>{fmt(e.salary)}</td>
                  <td style={{ fontSize: 12, color: 'var(--text3)' }}>
                    {e.band_min ? `${fmt(e.band_min)} – ${fmt(e.band_max)}` : '—'}
                  </td>
                  <td><CompaRatioBadge ratio={e.compa_ratio} /></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {tab === 'bands' && (
        <div className="card">
          <table className="table">
            <thead><tr><th>Role</th><th>Department</th><th>Level</th><th>Min</th><th>Mid (market)</th><th>Max</th><th>Spread</th></tr></thead>
            <tbody>
              {bands.length === 0 && <tr><td colSpan={7} className="empty">No salary bands defined — add bands to enable pay equity analysis</td></tr>}
              {bands.map(b => (
                <tr key={b.id}>
                  <td style={{ fontWeight: 500 }}>{b.job_title || '—'}</td>
                  <td style={{ color: 'var(--text3)' }}>{b.department || '—'}</td>
                  <td><span className="badge badge-info">{b.level || '—'}</span></td>
                  <td>{fmt(b.min_salary)}</td>
                  <td style={{ color: 'var(--blue)' }}>{fmt(b.mid_salary)}</td>
                  <td>{fmt(b.max_salary)}</td>
                  <td style={{ color: 'var(--text3)', fontSize: 12 }}>{b.range_spread}%</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
