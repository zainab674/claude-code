import React, { useState, useEffect, useCallback } from 'react';
import * as api from '../services/api';

const fmtDate = (d) => d ? new Date(d + 'T00:00:00').toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' }) : '—';

function Badge({ status }) {
  const map = { open: 'info', processing: 'warning', completed: 'success', cancelled: 'danger' };
  return <span className={`badge badge-${map[status] || 'info'}`}>{status}</span>;
}

export default function PayPeriods() {
  const [periods, setPeriods] = useState([]);
  const [loading, setLoading] = useState(true);
  const [genFreq, setGenFreq] = useState('biweekly');
  const [genCount, setGenCount] = useState(26);
  const [genStart, setGenStart] = useState(new Date().getFullYear() + '-01-01');
  const [generating, setGenerating] = useState(false);
  const [showManual, setShowManual] = useState(false);
  const [manualForm, setManualForm] = useState({ period_start: '', period_end: '', pay_date: '' });
  const [error, setError] = useState('');
  const [success, setSuccess] = useState('');

  const load = useCallback(() => {
    setLoading(true);
    api.getPayPeriods({ limit: 52 }).then(r => { setPeriods(r || []); setLoading(false); });
  }, []);

  useEffect(() => { load(); }, [load]);

  const generate = async () => {
    setGenerating(true); setError(''); setSuccess('');
    try {
      const r = await api.generatePayPeriods(genFreq, genCount, genStart);
      setSuccess(`Created ${r.created} pay periods`);
      load();
    } catch (e) { setError(e.message); }
    finally { setGenerating(false); }
  };

  const addManual = async (e) => {
    e.preventDefault();
    setError('');
    try {
      await api.createPayPeriod(manualForm);
      setShowManual(false);
      setManualForm({ period_start: '', period_end: '', pay_date: '' });
      load();
    } catch (err) { setError(err.message); }
  };

  const open = periods.filter(p => p.status === 'open').length;
  const completed = periods.filter(p => p.status === 'completed').length;

  return (
    <div className="page">
      <div className="page-header">
        <h1>Pay Periods <span className="count-badge">{periods.length}</span></h1>
        <div style={{ display: 'flex', gap: 8 }}>
          <button className="btn" onClick={() => setShowManual(!showManual)}>+ Manual</button>
        </div>
      </div>

      {error && <div className="alert alert-danger">{error}</div>}
      {success && <div className="alert" style={{ background: 'var(--green-bg)', color: 'var(--green)', border: '1px solid #b2dfb2', padding: '10px 14px', borderRadius: 6, marginBottom: 12, fontSize: 13 }}>✓ {success}</div>}

      {/* ── Generator ─────────────────────────── */}
      <div className="card" style={{ marginBottom: 16 }}>
        <div className="card-header"><h3>Auto-generate pay periods</h3></div>
        <div style={{ padding: 16, display: 'flex', gap: 12, flexWrap: 'wrap', alignItems: 'flex-end' }}>
          <div className="form-group" style={{ margin: 0 }}>
            <label>Frequency</label>
            <select value={genFreq} onChange={e => setGenFreq(e.target.value)}>
              <option value="weekly">Weekly</option>
              <option value="biweekly">Bi-weekly</option>
              <option value="semimonthly">Semi-monthly</option>
              <option value="monthly">Monthly</option>
            </select>
          </div>
          <div className="form-group" style={{ margin: 0 }}>
            <label>Number of periods</label>
            <input type="number" min="1" max="52" value={genCount}
              onChange={e => setGenCount(Number(e.target.value))} style={{ width: 80 }} />
          </div>
          <div className="form-group" style={{ margin: 0 }}>
            <label>Starting from</label>
            <input type="date" value={genStart} onChange={e => setGenStart(e.target.value)} />
          </div>
          <button className="btn btn-primary" onClick={generate} disabled={generating}>
            {generating ? 'Generating...' : '⊞ Generate'}
          </button>
        </div>
      </div>

      {/* ── Manual form ───────────────────────── */}
      {showManual && (
        <div className="card" style={{ marginBottom: 16 }}>
          <div className="card-header"><h3>Add pay period manually</h3><button className="btn btn-sm" onClick={() => setShowManual(false)}>Cancel</button></div>
          <form onSubmit={addManual} style={{ padding: 16 }}>
            <div className="form-grid">
              <div className="form-group">
                <label>Period start *</label>
                <input type="date" value={manualForm.period_start}
                  onChange={e => setManualForm(f => ({ ...f, period_start: e.target.value }))} required />
              </div>
              <div className="form-group">
                <label>Period end *</label>
                <input type="date" value={manualForm.period_end}
                  onChange={e => setManualForm(f => ({ ...f, period_end: e.target.value }))} required />
              </div>
              <div className="form-group">
                <label>Pay date *</label>
                <input type="date" value={manualForm.pay_date}
                  onChange={e => setManualForm(f => ({ ...f, pay_date: e.target.value }))} required />
              </div>
            </div>
            <button className="btn btn-primary" type="submit">Add period</button>
          </form>
        </div>
      )}

      {/* ── Stats ─────────────────────────────── */}
      <div className="metrics-grid" style={{ gridTemplateColumns: 'repeat(3,1fr)', marginBottom: 16 }}>
        <div className="metric-card"><div className="metric-label">Total periods</div><div className="metric-value">{periods.length}</div></div>
        <div className="metric-card"><div className="metric-label">Open</div><div className="metric-value" style={{ color: 'var(--blue)' }}>{open}</div></div>
        <div className="metric-card"><div className="metric-label">Completed</div><div className="metric-value" style={{ color: 'var(--green)' }}>{completed}</div></div>
      </div>

      {/* ── Table ─────────────────────────────── */}
      <div className="card">
        <table className="table">
          <thead>
            <tr><th>Period start</th><th>Period end</th><th>Pay date</th><th>Status</th></tr>
          </thead>
          <tbody>
            {loading && <tr><td colSpan={4} className="empty">Loading...</td></tr>}
            {!loading && periods.length === 0 && (
              <tr><td colSpan={4} className="empty">No pay periods — use the generator above</td></tr>
            )}
            {periods.map(p => (
              <tr key={p.id}>
                <td>{fmtDate(p.period_start)}</td>
                <td>{fmtDate(p.period_end)}</td>
                <td>{fmtDate(p.pay_date)}</td>
                <td><Badge status={p.status} /></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
