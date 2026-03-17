import React, { useState, useEffect } from 'react';

const BASE = process.env.REACT_APP_API_URL || 'http://localhost:8000';
const tkn = () => localStorage.getItem('payroll_token');
async function req(path) {
  const res = await fetch(`${BASE}${path}`, { headers: { Authorization: `Bearer ${tkn()}` } });
  if (!res.ok) return null;
  return res.json();
}
const fmt = n => `$${Number(n || 0).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
const year = new Date().getFullYear();

const PORTAL_COLORS = {
  'SSA BSO': { bg: 'var(--blue-bg)', text: 'var(--blue)', border: 'var(--blue)' },
  'IRS IRIS': { bg: 'var(--red-bg)', text: 'var(--red)', border: 'var(--red)' },
  'EFTPS': { bg: 'var(--green-bg)', text: 'var(--green)', border: 'var(--green)' },
  'State': { bg: 'var(--amber-bg)', text: 'var(--amber)', border: 'var(--amber)' },
};

function StepCard({ step, number }) {
  const [open, setOpen] = useState(number === 1);
  return (
    <div style={{ border: '1px solid var(--border)', borderRadius: 8, marginBottom: 8, overflow: 'hidden' }}>
      <div
        onClick={() => setOpen(!open)}
        style={{ padding: '12px 16px', cursor: 'pointer', display: 'flex', justifyContent: 'space-between', alignItems: 'center', background: open ? 'var(--bg2)' : 'transparent' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
          <div style={{ width: 24, height: 24, borderRadius: '50%', background: 'var(--blue-bg)', color: 'var(--blue)', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 12, fontWeight: 600, flexShrink: 0 }}>{number}</div>
          <span style={{ fontWeight: 500, fontSize: 13 }}>{step.title}</span>
          {step.one_time && <span className="badge badge-info" style={{ fontSize: 10 }}>one-time setup</span>}
        </div>
        <span style={{ color: 'var(--text3)', fontSize: 14 }}>{open ? '▾' : '▸'}</span>
      </div>
      {open && (
        <div style={{ padding: '12px 16px', borderTop: '1px solid var(--border)', fontSize: 13, color: 'var(--text2)', lineHeight: 1.7 }}>
          <div>{step.detail}</div>
          {step.url && (
            <a href={step.url} target="_blank" rel="noreferrer"
              style={{ display: 'inline-block', marginTop: 10, padding: '6px 14px', background: 'var(--blue-bg)', color: 'var(--blue)', borderRadius: 6, textDecoration: 'none', fontSize: 12, fontWeight: 500 }}>
              Open portal →
            </a>
          )}
          {step.download_url && (
            <a href={`${BASE}${step.download_url}?token=${tkn()}`}
              style={{ display: 'inline-block', marginTop: 10, marginLeft: 8, padding: '6px 14px', background: 'var(--green-bg)', color: 'var(--green)', borderRadius: 6, textDecoration: 'none', fontSize: 12, fontWeight: 500 }}>
              ↓ Download file
            </a>
          )}
        </div>
      )}
    </div>
  );
}

export default function FilingCenter() {
  const [tab, setTab] = useState('checklist');
  const [checklist, setChecklist] = useState(null);
  const [ssaGuide, setSsaGuide] = useState(null);
  const [irisGuide, setIrisGuide] = useState(null);
  const [stateGuide, setStateGuide] = useState(null);
  const [deadlines, setDeadlines] = useState(null);
  const [nacha, setNacha] = useState(null);
  const [runs, setRuns] = useState([]);
  const [selectedRun, setSelectedRun] = useState('');
  const [loading, setLoading] = useState(false);
  const [nachaPreview, setNachaPreview] = useState(null);
  const [nachaResult, setNachaResult] = useState(null);

  useEffect(() => {
    req(`/auto-filing/checklist/${year}`).then(setChecklist);
    req(`/auto-filing/status`).then(d => {});
    req(`/filing/deadlines/${year}`).then(setDeadlines);
    req('/payroll/history?limit=10').then(d => setRuns(d?.runs || []));
  }, []);

  const loadTab = async (t) => {
    setTab(t);
    if (t === 'ssa' && !ssaGuide) setSsaGuide(await req(`/filing/ssa-w2/${year}`));
    if (t === 'iris' && !irisGuide) setIrisGuide(await req(`/filing/irs-iris/${year}`));
    if (t === 'state' && !stateGuide) setStateGuide(await req(`/filing/state-ach/${year}`));
  };

  const previewNacha = async () => {
    if (!selectedRun) return;
    const r = await req(`/nacha/preview/${selectedRun}`);
    setNachaPreview(r);
  };

  const generateNacha = async () => {
    if (!selectedRun) return;
    setLoading(true);
    const res = await fetch(`${BASE}/nacha/generate`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${tkn()}` },
      body: JSON.stringify({ pay_run_id: selectedRun }),
    });
    const r = await res.json();
    setNachaResult(r);
    setLoading(false);
  };

  const STATUS_ICON = { complete: '✓', action_needed: '→', manual: '⊡', pending: '○' };
  const STATUS_COLOR = { complete: 'var(--green)', action_needed: 'var(--blue)', manual: 'var(--amber)', pending: 'var(--text3)' };

  return (
    <div className="page">
      <div className="page-header"><h1>Filing Center</h1></div>

      <div className="tab-bar">
        {[['checklist','Year-end checklist'],['ssa','W-2 / SSA BSO'],['iris','1099 / IRS IRIS'],['state','State tax portals'],['nacha','ACH / NACHA'],['deadlines','Deadlines']].map(([id, label]) => (
          <button key={id} className={`tab-btn ${tab === id ? 'active' : ''}`} onClick={() => loadTab(id)}>{label}</button>
        ))}
      </div>

      {/* ── CHECKLIST ─── */}
      {tab === 'checklist' && checklist && (
        <>
          <div className="metrics-grid" style={{ gridTemplateColumns: 'repeat(3,1fr)', marginBottom: 16 }}>
            <div className="metric-card"><div className="metric-label">Complete</div><div className="metric-value" style={{ color: 'var(--green)' }}>{checklist.summary.complete}</div></div>
            <div className="metric-card"><div className="metric-label">Action needed</div><div className="metric-value" style={{ color: 'var(--blue)' }}>{checklist.summary.action_needed}</div></div>
            <div className="metric-card"><div className="metric-label">Manual portal steps</div><div className="metric-value" style={{ color: 'var(--amber)' }}>{checklist.summary.manual_portal_steps}</div></div>
          </div>
          <div className="card">
            {Object.entries(
              checklist.checklist.reduce((acc, t) => {
                (acc[t.category] = acc[t.category] || []).push(t);
                return acc;
              }, {})
            ).map(([cat, tasks]) => (
              <div key={cat}>
                <div style={{ padding: '8px 16px 4px', fontSize: 11, fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.06em', color: 'var(--text3)', borderBottom: '1px solid var(--border)' }}>{cat}</div>
                {tasks.map((t, i) => (
                  <div key={i} style={{ padding: '10px 16px', borderBottom: '1px solid var(--border)', display: 'flex', alignItems: 'flex-start', gap: 12 }}>
                    <span style={{ fontSize: 14, color: STATUS_COLOR[t.status], flexShrink: 0, marginTop: 1 }}>{STATUS_ICON[t.status]}</span>
                    <div style={{ flex: 1 }}>
                      <div style={{ fontWeight: 500, fontSize: 13 }}>{t.task}</div>
                      <div style={{ fontSize: 12, color: 'var(--text3)', marginTop: 2 }}>{t.detail}</div>
                      {t.deadline && <div style={{ fontSize: 11, color: 'var(--red)', marginTop: 2 }}>Due: {t.deadline}</div>}
                    </div>
                    {(t.url) && (
                      <a href={t.url.startsWith('http') ? t.url : '#'}
                        onClick={t.url.startsWith('/') ? (e) => { e.preventDefault(); } : undefined}
                        target={t.url.startsWith('http') ? '_blank' : undefined}
                        rel="noreferrer"
                        style={{ fontSize: 11, color: 'var(--blue)', textDecoration: 'none', flexShrink: 0 }}>
                        {t.url.startsWith('http') ? 'Open ↗' : 'View →'}
                      </a>
                    )}
                  </div>
                ))}
              </div>
            ))}
          </div>
          <div className="card" style={{ marginTop: 16 }}>
            <div className="card-header"><h3>External links</h3></div>
            <div style={{ padding: 16, display: 'flex', flexWrap: 'wrap', gap: 8 }}>
              {Object.entries(checklist.external_links || {}).map(([name, url]) => (
                <a key={name} href={url} target="_blank" rel="noreferrer"
                  style={{ padding: '6px 12px', border: '1px solid var(--border)', borderRadius: 6, fontSize: 12, textDecoration: 'none', color: 'var(--blue)' }}>
                  {name} ↗
                </a>
              ))}
            </div>
          </div>
        </>
      )}

      {/* ── SSA BSO GUIDE ─── */}
      {tab === 'ssa' && ssaGuide && (
        <>
          <div className="card" style={{ marginBottom: 16, border: '1px solid var(--blue)', background: 'var(--blue-bg)' }}>
            <div style={{ padding: '14px 20px' }}>
              <div style={{ fontWeight: 600, color: 'var(--blue)', marginBottom: 4 }}>SSA Business Services Online — W-2 Filing</div>
              <div style={{ fontSize: 13, color: 'var(--text2)' }}>
                <strong>Deadline:</strong> {ssaGuide.deadline} &nbsp;·&nbsp;
                <strong>Employees:</strong> {ssaGuide.your_data.employees_with_wages} &nbsp;·&nbsp;
                <strong>Total wages:</strong> {fmt(ssaGuide.your_data.total_wages)} &nbsp;·&nbsp;
                <a href={ssaGuide.url} target="_blank" rel="noreferrer" style={{ color: 'var(--blue)' }}>Open SSA BSO ↗</a>
              </div>
            </div>
          </div>
          <div style={{ marginBottom: 12, display: 'flex', gap: 8 }}>
            <a href={`${BASE}/w2/${year}/xml`} download className="btn btn-primary" style={{ textDecoration: 'none', display: 'inline-block', padding: '7px 14px', fontSize: 13 }}>↓ Download W-2 EFW2 XML</a>
            <a href={`${BASE}/w2/${year}`} target="_blank" rel="noreferrer" className="btn" style={{ textDecoration: 'none', fontSize: 13 }}>View W-2 data</a>
          </div>
          <div className="card" style={{ marginBottom: 16 }}>
            <div className="card-header"><h3>Step-by-step instructions</h3></div>
            <div style={{ padding: 16 }}>
              {ssaGuide.steps.map((s, i) => <StepCard key={i} step={s} number={s.step} />)}
            </div>
          </div>
          <div className="two-col">
            <div className="card"><div className="card-header"><h3>Common errors</h3></div><div style={{ padding: 16 }}>{ssaGuide.common_errors.map((e, i) => <div key={i} style={{ fontSize: 13, padding: '4px 0', borderBottom: '1px solid var(--border)', color: 'var(--text2)' }}>⚠ {e}</div>)}</div></div>
            <div className="card">
              <div className="card-header"><h3>Late filing penalties</h3></div>
              <div style={{ padding: 16 }}>
                {Object.entries(ssaGuide.penalties).map(([when, penalty]) => (
                  <div key={when} style={{ display: 'flex', justifyContent: 'space-between', padding: '4px 0', fontSize: 13, borderBottom: '1px solid var(--border)' }}>
                    <span style={{ color: 'var(--text2)', textTransform: 'capitalize' }}>{when.replace(/_/g, ' ')}</span>
                    <span style={{ fontWeight: 500 }}>{penalty}</span>
                  </div>
                ))}
                <div style={{ marginTop: 10, fontSize: 12, color: 'var(--text3)' }}>Phone: {ssaGuide.help.ssa_employer_helpline} · {ssaGuide.help.hours}</div>
              </div>
            </div>
          </div>
        </>
      )}

      {/* ── IRS IRIS GUIDE ─── */}
      {tab === 'iris' && irisGuide && (
        <>
          <div className="card" style={{ marginBottom: 16, border: '1px solid var(--red)', background: 'var(--red-bg)' }}>
            <div style={{ padding: '14px 20px' }}>
              <div style={{ fontWeight: 600, color: 'var(--red)', marginBottom: 4 }}>IRS IRIS — 1099-NEC Filing</div>
              <div style={{ fontSize: 13, color: 'var(--text2)' }}>
                <strong>Deadline:</strong> {irisGuide.deadline_to_irs} &nbsp;·&nbsp;
                <strong>Contractors requiring 1099:</strong> {irisGuide.your_data.contractors_requiring_1099} &nbsp;·&nbsp;
                <strong>Total payments:</strong> {fmt(irisGuide.your_data.total_payments)} &nbsp;·&nbsp;
                <a href={irisGuide.url} target="_blank" rel="noreferrer" style={{ color: 'var(--red)' }}>Open IRIS ↗</a>
              </div>
            </div>
          </div>
          <div style={{ marginBottom: 12, display: 'flex', gap: 8 }}>
            <a href={`${BASE}/1099/xml?year=${year}`} download className="btn btn-primary" style={{ textDecoration: 'none', display: 'inline-block', padding: '7px 14px', fontSize: 13 }}>↓ Download 1099 XML</a>
            <a href={`${BASE}/1099/report?year=${year}`} target="_blank" rel="noreferrer" className="btn" style={{ textDecoration: 'none', fontSize: 13 }}>View 1099 report</a>
          </div>
          <div className="card" style={{ marginBottom: 16 }}>
            <div style={{ padding: '12px 16px', background: 'var(--amber-bg)', borderBottom: '1px solid var(--border)', fontSize: 13, color: 'var(--amber)' }}>
              ⚠ <strong>Apply for TCC early</strong> — IRS takes up to 45 days to issue a Transmitter Control Code. Apply by December 1 for January filing.
            </div>
            <div className="card-header"><h3>Step-by-step instructions</h3></div>
            <div style={{ padding: 16 }}>
              {irisGuide.steps.map((s, i) => <StepCard key={i} step={s} number={s.step} />)}
            </div>
          </div>
          <div className="card">
            <div className="card-header"><h3>Important notes</h3></div>
            <div style={{ padding: 16 }}>
              {irisGuide.important_notes.map((n, i) => <div key={i} style={{ padding: '4px 0', fontSize: 13, color: 'var(--text2)' }}>• {n}</div>)}
              <div style={{ marginTop: 10, fontSize: 12, color: 'var(--text3)' }}>Phone: {irisGuide.help.irs_helpline} · {irisGuide.help.hours}</div>
            </div>
          </div>
        </>
      )}

      {/* ── STATE PORTALS ─── */}
      {tab === 'state' && stateGuide && (
        <>
          <div className="card" style={{ marginBottom: 16 }}>
            <div style={{ padding: '14px 16px', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <div><div style={{ fontWeight: 600 }}>Total state tax liability {year}</div><div style={{ fontSize: 13, color: 'var(--text3)' }}>Withholding + SUTA across all states</div></div>
              <div style={{ fontSize: 22, fontWeight: 700, color: 'var(--amber)' }}>{fmt(stateGuide.total_state_tax_liability)}</div>
            </div>
          </div>
          {stateGuide.states.length === 0 && (
            <div className="card" style={{ padding: 32, textAlign: 'center', color: 'var(--text3)' }}>No state tax data found — run payroll first</div>
          )}
          {stateGuide.states.map(s => (
            <div key={s.state} className="card" style={{ marginBottom: 12 }}>
              <div style={{ padding: '12px 16px', display: 'flex', justifyContent: 'space-between', alignItems: 'center', borderBottom: '1px solid var(--border)' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
                  <div style={{ width: 40, height: 40, borderRadius: 8, background: 'var(--amber-bg)', color: 'var(--amber)', display: 'flex', alignItems: 'center', justifyContent: 'center', fontWeight: 700, fontSize: 14 }}>{s.state}</div>
                  <div>
                    <div style={{ fontWeight: 600 }}>{s.state_name}</div>
                    <div style={{ fontSize: 12, color: 'var(--text3)' }}>{s.employees} employees</div>
                  </div>
                </div>
                <div style={{ textAlign: 'right' }}>
                  <div style={{ fontWeight: 700, fontSize: 16 }}>{fmt(s.total_owed)}</div>
                  <div style={{ fontSize: 11, color: 'var(--text3)' }}>Withheld: {fmt(s.state_income_tax_withheld)} · SUTA: {fmt(s.suta_owed)}</div>
                </div>
              </div>
              <div style={{ padding: '10px 16px', fontSize: 13 }}>
                <div style={{ display: 'flex', gap: 24, flexWrap: 'wrap', marginBottom: 8 }}>
                  <span><span style={{ color: 'var(--text3)' }}>Portal:</span> <a href={s.portal.url} target="_blank" rel="noreferrer" style={{ color: 'var(--blue)' }}>{s.portal.name} ↗</a></span>
                  <span><span style={{ color: 'var(--text3)' }}>Form:</span> {s.portal.form}</span>
                  <span><span style={{ color: 'var(--text3)' }}>Frequency:</span> {s.portal.frequency}</span>
                  {s.portal.phone && <span><span style={{ color: 'var(--text3)' }}>Phone:</span> {s.portal.phone}</span>}
                </div>
                {s.portal.suta_portal && s.portal.suta_rate && (
                  <div style={{ fontSize: 12, color: 'var(--text3)' }}>
                    SUTA rate: {s.portal.suta_rate} · <a href={s.portal.suta_portal} target="_blank" rel="noreferrer" style={{ color: 'var(--blue)' }}>SUTA portal ↗</a>
                  </div>
                )}
                {s.portal.note && <div style={{ fontSize: 12, color: 'var(--amber)', marginTop: 4 }}>ℹ {s.portal.note}</div>}
              </div>
            </div>
          ))}
        </>
      )}

      {/* ── NACHA ─── */}
      {tab === 'nacha' && (
        <>
          <div className="card" style={{ marginBottom: 16 }}>
            <div className="card-header"><h3>Generate ACH / NACHA file</h3></div>
            <div style={{ padding: 16 }}>
              <p style={{ fontSize: 13, color: 'var(--text2)', marginBottom: 12 }}>
                Select a completed pay run to generate a NACHA-format .ach file. Upload this file to your bank's ACH origination portal to initiate direct deposit.
              </p>
              <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap', alignItems: 'flex-end' }}>
                <div className="form-group" style={{ flex: 1, minWidth: 250, margin: 0 }}>
                  <label>Pay run</label>
                  <select value={selectedRun} onChange={e => { setSelectedRun(e.target.value); setNachaPreview(null); setNachaResult(null); }}>
                    <option value="">Select completed pay run…</option>
                    {runs.filter(r => r.status === 'completed').map(r => (
                      <option key={r.id} value={r.id}>
                        {r.created_at?.slice(0,10)} — {r.employee_count} employees — ${Number(r.total_net||0).toLocaleString()}
                      </option>
                    ))}
                  </select>
                </div>
                <button className="btn" onClick={previewNacha} disabled={!selectedRun}>Preview entries</button>
                <button className="btn btn-primary" onClick={generateNacha} disabled={!selectedRun || loading}>{loading ? 'Generating…' : '↓ Generate NACHA file'}</button>
              </div>
            </div>
          </div>

          {nachaPreview && (
            <div className="card" style={{ marginBottom: 16 }}>
              <div className="card-header">
                <h3>Preview — {nachaPreview.will_include.length} employees included</h3>
                <span style={{ fontWeight: 600 }}>{fmt(nachaPreview.total_amount)}</span>
              </div>
              <table className="table">
                <thead><tr><th>Employee</th><th>Bank</th><th>Account</th><th>Net pay</th></tr></thead>
                <tbody>
                  {nachaPreview.will_include.map((e, i) => (
                    <tr key={i}><td style={{ fontWeight: 500 }}>{e.name}</td><td style={{ color: 'var(--text3)', fontSize: 12 }}>{e.bank_name || '—'}</td><td style={{ fontFamily: 'monospace', fontSize: 12 }}>{e.account_display}</td><td style={{ fontWeight: 600 }}>{fmt(e.net_pay)}</td></tr>
                  ))}
                  {nachaPreview.will_skip.map((e, i) => (
                    <tr key={`s${i}`} style={{ opacity: 0.5 }}>
                      <td>{e.name}</td><td colSpan={2} style={{ color: 'var(--amber)', fontSize: 12 }}>⚠ {e.reason}</td><td>—</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}

          {nachaResult && (
            <div className="card" style={{ border: `1px solid ${nachaResult.success ? 'var(--green)' : 'var(--red)'}` }}>
              <div style={{ padding: '14px 16px', background: nachaResult.success ? 'var(--green-bg)' : 'var(--red-bg)' }}>
                <div style={{ fontWeight: 600, color: nachaResult.success ? 'var(--green)' : 'var(--red)' }}>
                  {nachaResult.success ? `✓ NACHA file generated — ${nachaResult.employee_count} employees, ${fmt(nachaResult.total_amount)}` : '✗ ' + nachaResult.message}
                </div>
              </div>
              {nachaResult.success && (
                <div style={{ padding: 16 }}>
                  <a href={`${BASE}${nachaResult.download_url}`} download
                    style={{ display: 'inline-block', marginBottom: 16, padding: '8px 16px', background: 'var(--blue)', color: '#fff', borderRadius: 6, textDecoration: 'none', fontWeight: 500 }}>
                    ↓ Download {nachaResult.filename}
                  </a>
                  <div style={{ fontSize: 13, fontWeight: 500, marginBottom: 8 }}>Next steps:</div>
                  {nachaResult.next_steps.map((s, i) => (
                    <div key={i} style={{ padding: '4px 0', fontSize: 13, color: 'var(--text2)' }}>{i + 1}. {s}</div>
                  ))}
                </div>
              )}
            </div>
          )}

          <div className="card" style={{ marginTop: 16 }}>
            <div className="card-header"><h3>About NACHA files</h3></div>
            <div style={{ padding: 16, fontSize: 13, color: 'var(--text2)', lineHeight: 1.8 }}>
              <div>The .ach file follows the NACHA standard (94-character fixed-width records) used by all US banks.</div>
              <div>Employees must have a <strong>verified bank account</strong> on file (set up under Direct Deposit).</div>
              <div>Upload the file to your bank's ACH origination portal — usually under <em>Payments → ACH → Upload File</em>.</div>
              <div>Submit at least 1–2 business days before pay date for on-time delivery.</div>
            </div>
          </div>
        </>
      )}

      {/* ── DEADLINES ─── */}
      {tab === 'deadlines' && deadlines && (
        <>
          <div className="card" style={{ marginBottom: 16 }}>
            <div className="card-header"><h3>Federal deadlines {year}</h3></div>
            <table className="table">
              <thead><tr><th>Date</th><th>Form / Action</th><th>Portal</th><th></th></tr></thead>
              <tbody>
                {deadlines.federal.map((d, i) => (
                  <tr key={i}>
                    <td style={{ fontWeight: 500, fontSize: 12, whiteSpace: 'nowrap' }}>{d.date}</td>
                    <td style={{ fontSize: 13 }}>{d.form}</td>
                    <td><span className="badge badge-info">{d.portal}</span></td>
                    <td>{d.url && <a href={d.url} target="_blank" rel="noreferrer" style={{ fontSize: 12, color: 'var(--blue)' }}>Open ↗</a>}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="card" style={{ marginBottom: 16 }}>
            <div className="card-header"><h3>EFTPS deposit schedule</h3></div>
            <div style={{ padding: 16, fontSize: 13, lineHeight: 1.8, color: 'var(--text2)' }}>
              <div><strong>Semi-weekly:</strong> {deadlines.eftps_deposits.semi_weekly}</div>
              <div><strong>Monthly:</strong> {deadlines.eftps_deposits.monthly}</div>
              <div><strong>Which applies to you:</strong> {deadlines.eftps_deposits.rule}</div>
              <a href={deadlines.eftps_deposits.url} target="_blank" rel="noreferrer" style={{ display: 'inline-block', marginTop: 10, color: 'var(--blue)' }}>Open EFTPS ↗</a>
              &nbsp;&nbsp;
              <a href={deadlines.eftps_deposits.enrollment_url} target="_blank" rel="noreferrer" style={{ color: 'var(--blue)' }}>Enroll in EFTPS ↗</a>
            </div>
          </div>
          <div className="card">
            <div className="card-header"><h3>Key links</h3></div>
            <div style={{ padding: 16, display: 'flex', flexWrap: 'wrap', gap: 8 }}>
              {Object.entries(deadlines.key_external_links || {}).map(([name, url]) => (
                <a key={name} href={url} target="_blank" rel="noreferrer"
                  style={{ padding: '6px 12px', border: '1px solid var(--border)', borderRadius: 6, fontSize: 12, textDecoration: 'none', color: 'var(--blue)' }}>
                  {name} ↗
                </a>
              ))}
            </div>
          </div>
        </>
      )}
    </div>
  );
}
