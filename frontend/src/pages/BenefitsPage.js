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
const fmt = n => `$${Number(n || 0).toFixed(2)}`;
const fmtAnn = n => `$${Math.round(Number(n || 0) * 26).toLocaleString()}/yr`;

const PLAN_ICONS = { health: '♥', dental: '◎', vision: '◉', life: '◈', disability: '⊡', '401k': '%', fsa: '💳', hsa: '🏥' };
const PLAN_COLORS = { health: 'danger', dental: 'info', vision: 'success', life: 'warning', disability: 'warning', '401k': 'success', fsa: 'info', hsa: 'info' };

export default function Benefits() {
  const [tab, setTab] = useState('plans');
  const [plans, setPlans] = useState([]);
  const [windows, setWindows] = useState([]);
  const [elections, setElections] = useState([]);
  const [employees, setEmployees] = useState([]);
  const [showPlanForm, setShowPlanForm] = useState(false);
  const [showWindowForm, setShowWindowForm] = useState(false);
  const [selectedEmp, setSelectedEmp] = useState('');
  const [empSummary, setEmpSummary] = useState(null);
  const [planForm, setPlanForm] = useState({ plan_type: 'health', plan_name: '', carrier: '', employee_cost_per_period: 0, employer_cost_per_period: 0, coverage_tier: 'employee_only' });
  const [windowForm, setWindowForm] = useState({ name: '', window_type: 'annual', start_date: '', end_date: '', effective_date: '' });
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(true);

  const load = async () => {
    setLoading(true);
    try {
      const [p, w, e, emps] = await Promise.all([
        req('/benefits/plans'), req('/benefits/windows'),
        req('/benefits/elections'), req('/employees?status=active'),
      ]);
      setPlans(p || []); setWindows(w || []);
      setElections(e || []); setEmployees(emps?.employees || []);
    } catch (err) { setError(err.message); }
    setLoading(false);
  };
  useEffect(() => { load(); }, []);

  const loadEmpSummary = async (id) => {
    if (!id) { setEmpSummary(null); return; }
    try { setEmpSummary(await req(`/benefits/summary/employee/${id}`)); }
    catch { setEmpSummary(null); }
  };

  const savePlan = async (e) => {
    e.preventDefault(); setError('');
    try { await req('/benefits/plans', { method: 'POST', body: JSON.stringify(planForm) }); setShowPlanForm(false); load(); }
    catch (err) { setError(err.message); }
  };

  const saveWindow = async (e) => {
    e.preventDefault(); setError('');
    try { await req('/benefits/windows', { method: 'POST', body: JSON.stringify(windowForm) }); setShowWindowForm(false); load(); }
    catch (err) { setError(err.message); }
  };

  const enroll = async (employeeId, planId) => {
    setError('');
    try { await req('/benefits/elections', { method: 'POST', body: JSON.stringify({ employee_id: employeeId, plan_id: planId, coverage_tier: 'employee_only' }) }); load(); loadEmpSummary(selectedEmp); }
    catch (err) { setError(err.message); }
  };

  const waive = async (electionId) => {
    try { await req(`/benefits/elections/${electionId}`, { method: 'DELETE' }); load(); loadEmpSummary(selectedEmp); }
    catch (err) { setError(err.message); }
  };

  const groupedPlans = plans.reduce((acc, p) => { (acc[p.plan_type] = acc[p.plan_type] || []).push(p); return acc; }, {});

  return (
    <div className="page">
      <div className="page-header">
        <h1>Benefits</h1>
        <div className="tab-bar" style={{ margin: 0 }}>
          {[['plans','Plans'],['windows','Enrollment'],['elections','Elections']].map(([id, label]) => (
            <button key={id} className={`tab-btn ${tab === id ? 'active' : ''}`} onClick={() => setTab(id)}>{label}</button>
          ))}
        </div>
      </div>
      {error && <div className="alert alert-danger">{error}</div>}

      {/* ── Plans tab ─────────────────── */}
      {tab === 'plans' && (
        <>
          <div style={{ display: 'flex', justifyContent: 'flex-end', marginBottom: 16 }}>
            <button className="btn btn-primary" onClick={() => setShowPlanForm(!showPlanForm)}>+ Add plan</button>
          </div>
          {showPlanForm && (
            <div className="card" style={{ marginBottom: 16 }}>
              <div className="card-header"><h3>New benefit plan</h3><button className="btn btn-sm" onClick={() => setShowPlanForm(false)}>Cancel</button></div>
              <form onSubmit={savePlan} style={{ padding: 16 }}>
                <div className="form-grid">
                  {[['Plan type','plan_type','select'],['Plan name *','plan_name','text'],['Carrier','carrier','text'],['Employee cost/period ($)','employee_cost_per_period','number'],['Employer cost/period ($)','employer_cost_per_period','number']].map(([label, key, type]) => (
                    <div className="form-group" key={key}>
                      <label>{label}</label>
                      {type === 'select'
                        ? <select value={planForm[key]} onChange={e => setPlanForm(f => ({ ...f, [key]: e.target.value }))}>
                            {['health','dental','vision','life','disability','401k','fsa','hsa'].map(t => <option key={t} value={t}>{t}</option>)}
                          </select>
                        : <input type={type} step={type==='number'?'0.01':undefined} value={planForm[key]} onChange={e => setPlanForm(f => ({ ...f, [key]: type==='number' ? Number(e.target.value) : e.target.value }))} required={label.includes('*')} />
                      }
                    </div>
                  ))}
                </div>
                <button className="btn btn-primary" type="submit">Save plan</button>
              </form>
            </div>
          )}
          {Object.keys(groupedPlans).length === 0 && !loading && (
            <div className="card" style={{ padding: 32, textAlign: 'center', color: 'var(--text3)' }}>No benefit plans yet — add plans to start enrolling employees</div>
          )}
          {Object.entries(groupedPlans).map(([type, typePlans]) => (
            <div key={type} className="card" style={{ marginBottom: 12 }}>
              <div className="card-header">
                <h3 style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                  <span>{PLAN_ICONS[type] || '◎'}</span>
                  <span style={{ textTransform: 'capitalize' }}>{type}</span>
                  <span className="count-badge">{typePlans.length}</span>
                </h3>
              </div>
              <table className="table">
                <thead><tr><th>Plan name</th><th>Carrier</th><th>Employee cost</th><th>Employer cost</th><th>Annual emp cost</th></tr></thead>
                <tbody>
                  {typePlans.map(p => (
                    <tr key={p.id}>
                      <td style={{ fontWeight: 500 }}>{p.plan_name}</td>
                      <td style={{ color: 'var(--text3)' }}>{p.carrier || '—'}</td>
                      <td>{fmt(p.employee_cost_per_period)}/period</td>
                      <td style={{ color: 'var(--text3)' }}>{fmt(p.employer_cost_per_period)}/period</td>
                      <td>{fmtAnn(p.employee_cost_per_period)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ))}
        </>
      )}

      {/* ── Enrollment windows tab ─────── */}
      {tab === 'windows' && (
        <>
          <div style={{ display: 'flex', justifyContent: 'flex-end', marginBottom: 16 }}>
            <button className="btn btn-primary" onClick={() => setShowWindowForm(!showWindowForm)}>+ Create window</button>
          </div>
          {showWindowForm && (
            <div className="card" style={{ marginBottom: 16 }}>
              <div className="card-header"><h3>Enrollment window</h3><button className="btn btn-sm" onClick={() => setShowWindowForm(false)}>Cancel</button></div>
              <form onSubmit={saveWindow} style={{ padding: 16 }}>
                <div className="form-grid">
                  <div className="form-group"><label>Name *</label><input type="text" value={windowForm.name} onChange={e => setWindowForm(f => ({ ...f, name: e.target.value }))} required /></div>
                  <div className="form-group"><label>Type</label>
                    <select value={windowForm.window_type} onChange={e => setWindowForm(f => ({ ...f, window_type: e.target.value }))}>
                      <option value="annual">Annual open enrollment</option>
                      <option value="new_hire">New hire (30 days)</option>
                      <option value="qualifying_event">Qualifying life event</option>
                    </select>
                  </div>
                  <div className="form-group"><label>Opens *</label><input type="date" value={windowForm.start_date} onChange={e => setWindowForm(f => ({ ...f, start_date: e.target.value }))} required /></div>
                  <div className="form-group"><label>Closes *</label><input type="date" value={windowForm.end_date} onChange={e => setWindowForm(f => ({ ...f, end_date: e.target.value }))} required /></div>
                  <div className="form-group"><label>Coverage effective *</label><input type="date" value={windowForm.effective_date} onChange={e => setWindowForm(f => ({ ...f, effective_date: e.target.value }))} required /></div>
                </div>
                <button className="btn btn-primary" type="submit">Create window</button>
              </form>
            </div>
          )}
          <div className="card">
            <table className="table">
              <thead><tr><th>Window</th><th>Type</th><th>Open</th><th>Close</th><th>Effective</th><th>Status</th></tr></thead>
              <tbody>
                {windows.length === 0 && <tr><td colSpan={6} className="empty">No enrollment windows</td></tr>}
                {windows.map(w => (
                  <tr key={w.id}>
                    <td style={{ fontWeight: 500 }}>{w.name}</td>
                    <td><span className="badge badge-info">{w.window_type}</span></td>
                    <td style={{ fontSize: 12 }}>{w.start_date}</td>
                    <td style={{ fontSize: 12 }}>{w.end_date}</td>
                    <td style={{ fontSize: 12 }}>{w.effective_date}</td>
                    <td>
                      {w.is_open
                        ? <span className="badge badge-success">Open · {w.days_remaining}d left</span>
                        : <span className="badge badge-danger">Closed</span>}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}

      {/* ── Elections tab ──────────────── */}
      {tab === 'elections' && (
        <div className="two-col">
          <div className="card">
            <div className="card-header"><h3>Enroll employee</h3></div>
            <div style={{ padding: 16 }}>
              <div className="form-group">
                <label>Select employee</label>
                <select value={selectedEmp} onChange={e => { setSelectedEmp(e.target.value); loadEmpSummary(e.target.value); }}>
                  <option value="">Select…</option>
                  {employees.map(e => <option key={e.id} value={e.id}>{e.full_name}</option>)}
                </select>
              </div>
              {selectedEmp && plans.length > 0 && (
                <>
                  <div style={{ fontWeight: 500, fontSize: 13, marginBottom: 8, marginTop: 12 }}>Available plans</div>
                  {Object.entries(groupedPlans).map(([type, typePlans]) => (
                    <div key={type} style={{ marginBottom: 12 }}>
                      <div style={{ fontSize: 11, textTransform: 'uppercase', color: 'var(--text3)', marginBottom: 4 }}>{type}</div>
                      {typePlans.map(p => (
                        <div key={p.id} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '6px 0', borderBottom: '1px solid var(--border)', fontSize: 13 }}>
                          <div>
                            <div>{p.plan_name}</div>
                            <div style={{ fontSize: 11, color: 'var(--text3)' }}>{fmt(p.employee_cost_per_period)}/period · {p.carrier}</div>
                          </div>
                          <button className="btn btn-sm" onClick={() => enroll(selectedEmp, p.id)}>Enroll</button>
                        </div>
                      ))}
                    </div>
                  ))}
                </>
              )}
            </div>
          </div>
          <div>
            {empSummary && (
              <div className="card">
                <div className="card-header"><h3>Current elections</h3></div>
                <div style={{ padding: 16 }}>
                  {empSummary.enrolled_plans.length === 0 && <div style={{ color: 'var(--text3)', fontSize: 13 }}>No active elections</div>}
                  {empSummary.enrolled_plans.map((p, i) => (
                    <div key={i} style={{ display: 'flex', justifyContent: 'space-between', padding: '8px 0', borderBottom: '1px solid var(--border)', fontSize: 13 }}>
                      <div>
                        <div style={{ fontWeight: 500 }}>{p.plan_name}</div>
                        <div style={{ fontSize: 11, color: 'var(--text3)' }}>{p.carrier} · {p.coverage_tier}</div>
                      </div>
                      <div style={{ textAlign: 'right' }}>
                        <div>{fmt(p.employee_cost)}/period</div>
                        <span className={`badge badge-${PLAN_COLORS[p.plan_type] || 'info'}`}>{p.plan_type}</span>
                      </div>
                    </div>
                  ))}
                  {empSummary.enrolled_plans.length > 0 && (
                    <div style={{ marginTop: 12, padding: '8px 0', display: 'flex', justifyContent: 'space-between', fontWeight: 600 }}>
                      <span>Total/period</span>
                      <span>{fmt(empSummary.total_employee_cost_per_period)}</span>
                    </div>
                  )}
                </div>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
