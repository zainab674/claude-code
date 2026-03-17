import React, { useState, useEffect } from 'react';

const BASE = process.env.REACT_APP_API_URL || 'http://localhost:8000';
const tkn = () => localStorage.getItem('payroll_token');
async function req(path, opts = {}) {
  const res = await fetch(`${BASE}${path}`, {
    ...opts,
    headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${tkn()}`, ...opts.headers },
  });
  if (!res.ok) { const e = await res.json().catch(() => ({ detail: res.statusText })); throw new Error(e.detail); }
  return res.json();
}
const fmt = n => `$${Number(n || 0).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
const diffColor = n => Number(n) > 0 ? 'var(--green)' : Number(n) < 0 ? 'var(--red)' : 'var(--text3)';

export default function Reconciliation() {
  const [tab, setTab] = useState('variance');
  const [runs, setRuns] = useState([]);
  const [variance, setVariance] = useState(null);
  const [ytdCheck, setYtdCheck] = useState(null);
  const [compare, setCompare] = useState(null);
  const [runA, setRunA] = useState('');
  const [runB, setRunB] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const year = new Date().getFullYear();

  useEffect(() => {
    req('/payroll/history?limit=20').then(d => setRuns(d?.runs || []));
    req(`/reconciliation/ytd-check/${year}`).then(setYtdCheck);
  }, []);

  const loadVariance = async (runId) => {
    if (!runId) return;
    setLoading(true); setError('');
    try { setVariance(await req(`/reconciliation/variance/${runId}`)); }
    catch (err) { setError(err.message); }
    setLoading(false);
  };

  const loadCompare = async () => {
    if (!runA || !runB) return;
    setLoading(true); setError('');
    try { setCompare(await req(`/reconciliation/compare?run_a=${runA}&run_b=${runB}`)); }
    catch (err) { setError(err.message); }
    setLoading(false);
  };

  return (
    <div className="page">
      <div className="page-header"><h1>Payroll Reconciliation</h1></div>
      {error && <div className="alert alert-danger">{error}</div>}

      <div className="tab-bar">
        {[['variance','Variance Analysis'],['compare','Compare Runs'],['ytd','YTD Check']].map(([id, label]) => (
          <button key={id} className={`tab-btn ${tab === id ? 'active' : ''}`} onClick={() => setTab(id)}>{label}</button>
        ))}
      </div>

      {/* ── VARIANCE ─── */}
      {tab === 'variance' && (
        <>
          <div className="card" style={{ marginBottom: 16 }}>
            <div style={{ padding: 16, display: 'flex', gap: 12, alignItems: 'flex-end' }}>
              <div className="form-group" style={{ flex: 1, margin: 0 }}>
                <label>Select pay run to compare with previous</label>
                <select value={variance?.run_a_id || ''} onChange={e => loadVariance(e.target.value)}>
                  <option value="">Select run…</option>
                  {runs.map(r => <option key={r.id} value={r.id}>{r.created_at?.slice(0,10)} — {r.employee_count} emp — ${Number(r.total_gross||0).toLocaleString()}</option>)}
                </select>
              </div>
            </div>
          </div>
          {loading && <div style={{ padding: 32, textAlign: 'center', color: 'var(--text3)' }}>Analyzing…</div>}
          {variance && !loading && (
            <>
              {variance.message ? (
                <div className="card" style={{ padding: 24, textAlign: 'center', color: 'var(--text3)' }}>{variance.message}</div>
              ) : (
                <>
                  <div className="metrics-grid" style={{ marginBottom: 16 }}>
                    <div className="metric-card"><div className="metric-label">Gross diff</div><div className="metric-value" style={{ color: diffColor(variance.total_diff?.gross) }}>{fmt(variance.total_diff?.gross)}</div></div>
                    <div className="metric-card"><div className="metric-label">Net diff</div><div className="metric-value" style={{ color: diffColor(variance.total_diff?.net) }}>{fmt(variance.total_diff?.net)}</div></div>
                    <div className="metric-card"><div className="metric-label">Flagged employees</div><div className="metric-value" style={{ color: variance.flagged_employees > 0 ? 'var(--red)' : 'var(--green)' }}>{variance.flagged_employees}</div><div className="metric-delta">&gt;{variance.threshold_pct}% change</div></div>
                    <div className="metric-card"><div className="metric-label">Headcount diff</div><div className="metric-value" style={{ color: diffColor(variance.total_diff?.employees) }}>{(variance.total_diff?.employees || 0) >= 0 ? '+' : ''}{variance.total_diff?.employees}</div></div>
                  </div>
                  <div className="card">
                    <table className="table">
                      <thead><tr><th>Employee</th><th>Previous gross</th><th>Current gross</th><th>Diff</th><th>Change %</th><th>Flag</th></tr></thead>
                      <tbody>
                        {(variance.employees || []).map(e => (
                          <tr key={e.employee_id} style={{ background: e.flagged ? 'var(--red-bg)' : '' }}>
                            <td style={{ fontWeight: 500 }}>{e.employee_name}</td>
                            <td>{e.only_in_b ? '—' : fmt(e.gross_a)}</td>
                            <td>{e.only_in_a ? '—' : fmt(e.gross_b)}</td>
                            <td style={{ color: diffColor(e.gross_diff), fontWeight: 500 }}>{e.gross_diff >= 0 ? '+' : ''}{fmt(e.gross_diff)}</td>
                            <td style={{ color: diffColor(e.gross_pct_change) }}>{e.gross_pct_change !== null ? `${e.gross_pct_change >= 0 ? '+' : ''}${e.gross_pct_change}%` : '—'}</td>
                            <td>{e.flagged ? <span className="badge badge-danger">⚠</span> : <span className="badge badge-success">✓</span>}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </>
              )}
            </>
          )}
        </>
      )}

      {/* ── COMPARE ─── */}
      {tab === 'compare' && (
        <>
          <div className="card" style={{ marginBottom: 16 }}>
            <div style={{ padding: 16, display: 'flex', gap: 12, alignItems: 'flex-end', flexWrap: 'wrap' }}>
              <div className="form-group" style={{ flex: 1, minWidth: 200, margin: 0 }}>
                <label>Run A (baseline)</label>
                <select value={runA} onChange={e => setRunA(e.target.value)}>
                  <option value="">Select…</option>
                  {runs.map(r => <option key={r.id} value={r.id}>{r.created_at?.slice(0,10)} — ${Number(r.total_gross||0).toLocaleString()}</option>)}
                </select>
              </div>
              <div className="form-group" style={{ flex: 1, minWidth: 200, margin: 0 }}>
                <label>Run B (compare)</label>
                <select value={runB} onChange={e => setRunB(e.target.value)}>
                  <option value="">Select…</option>
                  {runs.filter(r => r.id !== runA).map(r => <option key={r.id} value={r.id}>{r.created_at?.slice(0,10)} — ${Number(r.total_gross||0).toLocaleString()}</option>)}
                </select>
              </div>
              <button className="btn btn-primary" onClick={loadCompare} disabled={!runA || !runB || loading}>Compare</button>
            </div>
          </div>
          {compare && !loading && (
            <>
              <div className="metrics-grid" style={{ marginBottom: 16 }}>
                {[['Gross A', fmt(compare.totals_a?.gross)], ['Gross B', fmt(compare.totals_b?.gross)], ['Gross diff', fmt(compare.total_diff?.gross)], ['Flagged', compare.flagged_employees]].map(([l, v]) => (
                  <div key={l} className="metric-card"><div className="metric-label">{l}</div><div className="metric-value">{v}</div></div>
                ))}
              </div>
              <div className="card">
                <table className="table">
                  <thead><tr><th>Employee</th><th>Gross A</th><th>Gross B</th><th>Net A</th><th>Net B</th><th>Gross diff</th><th></th></tr></thead>
                  <tbody>
                    {(compare.employees || []).map(e => (
                      <tr key={e.employee_id} style={{ background: e.flagged ? 'var(--red-bg)' : '' }}>
                        <td style={{ fontWeight: 500 }}>{e.employee_name}</td>
                        <td style={{ color: 'var(--text2)' }}>{e.only_in_b ? '—' : fmt(e.gross_a)}</td>
                        <td>{e.only_in_a ? '—' : fmt(e.gross_b)}</td>
                        <td style={{ color: 'var(--text2)' }}>{e.only_in_b ? '—' : fmt(e.net_a)}</td>
                        <td>{e.only_in_a ? '—' : fmt(e.net_b)}</td>
                        <td style={{ color: diffColor(e.gross_diff), fontWeight: 600 }}>{e.gross_diff >= 0 ? '+' : ''}{fmt(e.gross_diff)}</td>
                        <td>{e.flagged ? <span className="badge badge-danger">⚠ flagged</span> : ''}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </>
          )}
        </>
      )}

      {/* ── YTD CHECK ─── */}
      {tab === 'ytd' && ytdCheck && (
        <>
          <div className="card" style={{ marginBottom: 16, border: `1px solid ${ytdCheck.status === 'ok' ? 'var(--green)' : 'var(--red)'}` }}>
            <div style={{ padding: '14px 20px', display: 'flex', alignItems: 'center', gap: 16 }}>
              <span style={{ fontSize: 24, color: ytdCheck.status === 'ok' ? 'var(--green)' : 'var(--red)' }}>{ytdCheck.status === 'ok' ? '✓' : '✗'}</span>
              <div>
                <div style={{ fontWeight: 600 }}>{ytdCheck.status === 'ok' ? 'YTD totals are consistent' : 'Discrepancy detected'}</div>
                <div style={{ fontSize: 12, color: 'var(--text3)' }}>{ytdCheck.notes} · {ytdCheck.run_count} completed runs in {ytdCheck.year}</div>
              </div>
            </div>
          </div>
          <div className="card">
            <div className="card-header"><h3>Sum of all {ytdCheck.year} runs</h3></div>
            <div style={{ padding: 16 }}>
              <div className="preview-box">
                {[
                  ['Total runs', ytdCheck.run_count],
                  ['Sum of gross wages', fmt(ytdCheck.sum_of_runs?.gross)],
                  ['Sum of net pay', fmt(ytdCheck.sum_of_runs?.net)],
                  ['Sum of employee taxes', fmt(ytdCheck.sum_of_runs?.employee_taxes)],
                  ['Sum of employer taxes', fmt(ytdCheck.sum_of_runs?.employer_taxes)],
                ].map(([l, v]) => (
                  <div key={l} className="preview-row">
                    <span style={{ color: 'var(--text2)' }}>{l}</span>
                    <span style={{ fontWeight: 500 }}>{v}</span>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </>
      )}
    </div>
  );
}
