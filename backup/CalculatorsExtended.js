import React, { useState } from 'react';

const BASE = process.env.REACT_APP_API_URL || 'http://localhost:8000';
const tkn = () => localStorage.getItem('payroll_token');
const fmt = n => `$${Number(n || 0).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
const fmtPct = n => `${Number(n || 0).toFixed(1)}%`;

async function post(path, body) {
  const res = await fetch(`${BASE}${path}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${tkn()}` },
    body: JSON.stringify(body),
  });
  if (!res.ok) { const e = await res.json().catch(() => ({ detail: res.statusText })); throw new Error(e.detail); }
  return res.json();
}

const STATES = ['AL','AK','AZ','AR','CA','CO','CT','DE','FL','GA','HI','ID','IL','IN','IA','KS','KY','LA','ME','MD','MA','MI','MN','MS','MO','MT','NE','NV','NH','NJ','NM','NY','NC','ND','OH','OK','OR','PA','RI','SC','SD','TN','TX','UT','VT','VA','WA','WV','WI','WY','DC'];

function ResultRow({ label, value, accent, total }) {
  return (
    <div className={`preview-row ${total ? 'total' : ''}`}>
      <span style={{ color: accent ? 'var(--text)' : 'var(--text2)', fontWeight: total ? 600 : 400 }}>{label}</span>
      <span style={{ fontWeight: total ? 700 : 500, color: accent }}>{value}</span>
    </div>
  );
}

export default function CalculatorsExtended() {
  const [tab, setTab] = useState('net-gross');

  // Net-to-gross state
  const [ntg, setNtg] = useState({ target_net: 3000, filing_status: 'single', state_code: 'NY', pay_frequency: 'biweekly', health_insurance_deduction: 0, retirement_401k_pct: 0 });
  const [ntgResult, setNtgResult] = useState(null);
  const [ntgLoading, setNtgLoading] = useState(false);

  // Multi-state state
  const [ms, setMs] = useState({ annual_salary: 80000, work_state: 'NY', residence_state: 'NJ', pay_frequency: 'biweekly', filing_status: 'single' });
  const [msResult, setMsResult] = useState(null);
  const [msLoading, setMsLoading] = useState(false);

  // Funding state
  const [fund, setFund] = useState({ employee_count: 10, avg_gross: 3000, avg_net: 2100, avg_emp_tax: 700, avg_er_tax: 280, ach_fee_per_employee: 0.25, buffer_pct: 2 });
  const [fundResult, setFundResult] = useState(null);

  // Pricing state
  const [price, setPrice] = useState({ employee_count: 25, payroll_frequency: 'biweekly', ach_cost_per_transaction: 0.25, monthly_platform_cost: 20, filing_cost_per_quarter: 0, support_hours_per_month: 2, support_hourly_rate: 50, desired_margin_pct: 40 });
  const [priceResult, setPriceResult] = useState(null);
  const [priceLoading, setPriceLoading] = useState(false);

  const [error, setError] = useState('');

  const calcNtg = async () => {
    setNtgLoading(true); setError('');
    try { setNtgResult(await post('/calculator/net-to-gross', ntg)); }
    catch (e) { setError(e.message); }
    setNtgLoading(false);
  };

  const calcMs = async () => {
    setMsLoading(true); setError('');
    try { setMsResult(await post('/calculator/multi-state', ms)); }
    catch (e) { setError(e.message); }
    setMsLoading(false);
  };

  const calcFund = () => {
    const items = Array.from({ length: fund.employee_count }, () => ({
      gross_pay: fund.avg_gross, net_pay: fund.avg_net,
      employee_taxes: fund.avg_emp_tax, employer_taxes: fund.avg_er_tax,
    }));
    post('/calculator/funding', {
      pay_run_preview_items: items,
      ach_fee_per_employee: fund.ach_fee_per_employee,
      buffer_pct: fund.buffer_pct,
    }).then(setFundResult).catch(e => setError(e.message));
  };

  const calcPrice = async () => {
    setPriceLoading(true); setError('');
    try { setPriceResult(await post('/calculator/pricing', price)); }
    catch (e) { setError(e.message); }
    setPriceLoading(false);
  };

  return (
    <div className="page">
      <div className="page-header"><h1>Advanced Calculators</h1></div>
      {error && <div className="alert alert-danger">{error}</div>}

      <div className="tab-bar">
        {[['net-gross','Net-to-gross'],['multi-state','Multi-state'],['funding','Funding'],['pricing','Pricing']].map(([id, label]) => (
          <button key={id} className={`tab-btn ${tab === id ? 'active' : ''}`} onClick={() => setTab(id)}>{label}</button>
        ))}
      </div>

      {/* ── NET-TO-GROSS ─── */}
      {tab === 'net-gross' && (
        <div className="two-col">
          <div className="card">
            <div className="card-header"><h3>Net-to-gross calculator</h3></div>
            <div style={{ padding: 16 }}>
              <p style={{ fontSize: 12, color: 'var(--text3)', marginBottom: 14 }}>Enter the exact net amount an employee must receive — we calculate the gross pay needed.</p>
              <div className="form-grid">
                <div className="form-group"><label>Target net pay ($) *</label><input type="number" step="0.01" value={ntg.target_net} onChange={e => setNtg(f => ({ ...f, target_net: Number(e.target.value) }))} /></div>
                <div className="form-group"><label>State</label><select value={ntg.state_code} onChange={e => setNtg(f => ({ ...f, state_code: e.target.value }))}>{STATES.map(s => <option key={s} value={s}>{s}</option>)}</select></div>
                <div className="form-group"><label>Filing status</label><select value={ntg.filing_status} onChange={e => setNtg(f => ({ ...f, filing_status: e.target.value }))}><option value="single">Single</option><option value="married">Married</option><option value="head_of_household">Head of household</option></select></div>
                <div className="form-group"><label>Pay frequency</label><select value={ntg.pay_frequency} onChange={e => setNtg(f => ({ ...f, pay_frequency: e.target.value }))}>{['weekly','biweekly','semimonthly','monthly'].map(f => <option key={f} value={f}>{f}</option>)}</select></div>
                <div className="form-group"><label>Health ins. deduction ($)</label><input type="number" value={ntg.health_insurance_deduction} onChange={e => setNtg(f => ({ ...f, health_insurance_deduction: Number(e.target.value) }))} /></div>
                <div className="form-group"><label>401(k) %</label><input type="number" step="0.01" max="1" value={ntg.retirement_401k_pct} onChange={e => setNtg(f => ({ ...f, retirement_401k_pct: Number(e.target.value) }))} placeholder="0.05 = 5%" /></div>
              </div>
              <button className="btn btn-primary" onClick={calcNtg} disabled={ntgLoading}>{ntgLoading ? 'Calculating…' : 'Calculate gross pay'}</button>
            </div>
          </div>
          <div>
            {ntgResult && (
              <div className="card">
                <div className="card-header"><h3>Result</h3></div>
                <div style={{ padding: 16 }}>
                  <div style={{ textAlign: 'center', marginBottom: 16 }}>
                    <div style={{ fontSize: 12, color: 'var(--text3)' }}>Required gross pay</div>
                    <div style={{ fontSize: 32, fontWeight: 700, color: 'var(--blue)' }}>{fmt(ntgResult.required_gross)}</div>
                    <div style={{ fontSize: 12, color: 'var(--text3)' }}>to deliver {fmt(ntgResult.target_net)} net</div>
                  </div>
                  <div className="preview-box">
                    <ResultRow label="Required gross" value={fmt(ntgResult.required_gross)} accent="var(--blue)" />
                    <ResultRow label="Federal income tax" value={fmt(ntgResult.federal_income_tax)} />
                    <ResultRow label="State income tax" value={fmt(ntgResult.state_income_tax)} />
                    <ResultRow label="Social security" value={fmt(ntgResult.social_security)} />
                    <ResultRow label="Medicare" value={fmt(ntgResult.medicare)} />
                    <ResultRow label="Pre-tax deductions" value={fmt(ntgResult.pretax_deductions)} />
                    <ResultRow label="Actual net pay" value={fmt(ntgResult.actual_net)} total accent="var(--green)" />
                  </div>
                  <div style={{ fontSize: 12, color: 'var(--text3)', marginTop: 10 }}>
                    Gross-up factor: +{fmtPct(ntgResult.effective_gross_up_pct)} · Converged in {ntgResult.iterations} iterations
                  </div>
                </div>
              </div>
            )}
          </div>
        </div>
      )}

      {/* ── MULTI-STATE ─── */}
      {tab === 'multi-state' && (
        <div className="two-col">
          <div className="card">
            <div className="card-header"><h3>Multi-state withholding</h3></div>
            <div style={{ padding: 16 }}>
              <p style={{ fontSize: 12, color: 'var(--text3)', marginBottom: 14 }}>Employee works in one state, lives in another. Calculates correct withholding and checks for reciprocity agreements.</p>
              <div className="form-grid">
                <div className="form-group"><label>Annual salary ($) *</label><input type="number" value={ms.annual_salary} onChange={e => setMs(f => ({ ...f, annual_salary: Number(e.target.value) }))} /></div>
                <div className="form-group"><label>Pay frequency</label><select value={ms.pay_frequency} onChange={e => setMs(f => ({ ...f, pay_frequency: e.target.value }))}>{['weekly','biweekly','semimonthly','monthly'].map(f => <option key={f} value={f}>{f}</option>)}</select></div>
                <div className="form-group"><label>Work state *</label><select value={ms.work_state} onChange={e => setMs(f => ({ ...f, work_state: e.target.value }))}>{STATES.map(s => <option key={s} value={s}>{s}</option>)}</select></div>
                <div className="form-group"><label>Residence state *</label><select value={ms.residence_state} onChange={e => setMs(f => ({ ...f, residence_state: e.target.value }))}>{STATES.map(s => <option key={s} value={s}>{s}</option>)}</select></div>
                <div className="form-group"><label>Filing status</label><select value={ms.filing_status} onChange={e => setMs(f => ({ ...f, filing_status: e.target.value }))}><option value="single">Single</option><option value="married">Married</option></select></div>
              </div>
              <button className="btn btn-primary" onClick={calcMs} disabled={msLoading}>{msLoading ? 'Calculating…' : 'Calculate withholding'}</button>
            </div>
          </div>
          <div>
            {msResult && (
              <div className="card">
                <div className="card-header">
                  <h3>Result: {msResult.work_state} / {msResult.residence_state}</h3>
                  {msResult.has_reciprocity && <span className="badge badge-success">Reciprocity ✓</span>}
                </div>
                <div style={{ padding: 16 }}>
                  <div style={{ padding: 10, background: 'var(--blue-bg)', borderRadius: 6, fontSize: 12, marginBottom: 14, color: 'var(--blue)' }}>
                    ℹ {msResult.rule_applied}
                  </div>
                  <div className="preview-box">
                    <ResultRow label="Gross pay" value={fmt(msResult.per_paycheck.gross_pay)} />
                    <ResultRow label="Federal income tax" value={fmt(msResult.per_paycheck.federal_income_tax)} />
                    <ResultRow label="Social security" value={fmt(msResult.per_paycheck.social_security)} />
                    <ResultRow label="Medicare" value={fmt(msResult.per_paycheck.medicare)} />
                    <ResultRow label={`${msResult.work_state} withholding`} value={fmt(msResult.per_paycheck.work_state_withholding)} />
                    <ResultRow label={`${msResult.residence_state} withholding`} value={fmt(msResult.per_paycheck.residence_state_withholding)} />
                    <ResultRow label="Net pay" value={fmt(msResult.per_paycheck.net_pay)} total accent="var(--green)" />
                  </div>
                  <div style={{ fontSize: 11, color: 'var(--amber)', marginTop: 10 }}>⚠ {msResult.disclaimer}</div>
                </div>
              </div>
            )}
          </div>
        </div>
      )}

      {/* ── FUNDING ─── */}
      {tab === 'funding' && (
        <div className="two-col">
          <div className="card">
            <div className="card-header"><h3>Payroll funding calculator</h3></div>
            <div style={{ padding: 16 }}>
              <p style={{ fontSize: 12, color: 'var(--text3)', marginBottom: 14 }}>How much must be in your bank account before approving payroll?</p>
              <div className="form-grid">
                <div className="form-group"><label>Number of employees</label><input type="number" value={fund.employee_count} onChange={e => setFund(f => ({ ...f, employee_count: Number(e.target.value) }))} /></div>
                <div className="form-group"><label>Avg gross pay/employee ($)</label><input type="number" value={fund.avg_gross} onChange={e => setFund(f => ({ ...f, avg_gross: Number(e.target.value) }))} /></div>
                <div className="form-group"><label>Avg net pay/employee ($)</label><input type="number" value={fund.avg_net} onChange={e => setFund(f => ({ ...f, avg_net: Number(e.target.value) }))} /></div>
                <div className="form-group"><label>Avg employee taxes ($)</label><input type="number" value={fund.avg_emp_tax} onChange={e => setFund(f => ({ ...f, avg_emp_tax: Number(e.target.value) }))} /></div>
                <div className="form-group"><label>ACH fee/employee ($)</label><input type="number" step="0.01" value={fund.ach_fee_per_employee} onChange={e => setFund(f => ({ ...f, ach_fee_per_employee: Number(e.target.value) }))} /></div>
                <div className="form-group"><label>Safety buffer (%)</label><input type="number" value={fund.buffer_pct} onChange={e => setFund(f => ({ ...f, buffer_pct: Number(e.target.value) }))} /></div>
              </div>
              <button className="btn btn-primary" onClick={calcFund}>Calculate funding needed</button>
            </div>
          </div>
          <div>
            {fundResult && (
              <div className="card">
                <div className="card-header"><h3>Funding required</h3></div>
                <div style={{ padding: 16 }}>
                  <div style={{ textAlign: 'center', marginBottom: 16 }}>
                    <div style={{ fontSize: 12, color: 'var(--text3)' }}>Recommended balance before payroll</div>
                    <div style={{ fontSize: 32, fontWeight: 700, color: 'var(--amber)' }}>{fmt(fundResult.recommended_with_buffer)}</div>
                  </div>
                  <div className="preview-box">
                    <ResultRow label="Net wages to employees" value={fmt(fundResult.breakdown.net_wages_to_employees)} />
                    <ResultRow label="Employee taxes withheld" value={fmt(fundResult.breakdown.employee_taxes_withheld)} />
                    <ResultRow label="Employer FICA" value={fmt(fundResult.breakdown.employer_fica_liability)} />
                    <ResultRow label="Est. IRS 941 deposit" value={fmt(fundResult.breakdown.estimated_irs_941_deposit)} />
                    <ResultRow label="ACH fees" value={fmt(fundResult.breakdown.ach_fees)} />
                    <ResultRow label={`${fundResult.buffer_pct}% safety buffer`} value={fmt(fundResult.breakdown.safety_buffer)} />
                    <ResultRow label="Minimum required" value={fmt(fundResult.minimum_required)} />
                    <ResultRow label="Recommended" value={fmt(fundResult.recommended_with_buffer)} total accent="var(--amber)" />
                  </div>
                  <div style={{ fontSize: 11, color: 'var(--text3)', marginTop: 10 }}>{fundResult.note}</div>
                </div>
              </div>
            )}
          </div>
        </div>
      )}

      {/* ── PRICING ─── */}
      {tab === 'pricing' && (
        <div className="two-col">
          <div className="card">
            <div className="card-header"><h3>Payroll service pricing calculator</h3></div>
            <div style={{ padding: 16 }}>
              <p style={{ fontSize: 12, color: 'var(--text3)', marginBottom: 14 }}>Calculate what to charge your customers based on your actual costs and desired margin.</p>
              <div className="form-grid">
                <div className="form-group"><label>Customer employees</label><input type="number" value={price.employee_count} onChange={e => setPrice(f => ({ ...f, employee_count: Number(e.target.value) }))} /></div>
                <div className="form-group"><label>Pay frequency</label><select value={price.payroll_frequency} onChange={e => setPrice(f => ({ ...f, payroll_frequency: e.target.value }))}>{['weekly','biweekly','semimonthly','monthly'].map(f => <option key={f} value={f}>{f}</option>)}</select></div>
                <div className="form-group"><label>ACH cost/transaction ($)</label><input type="number" step="0.01" value={price.ach_cost_per_transaction} onChange={e => setPrice(f => ({ ...f, ach_cost_per_transaction: Number(e.target.value) }))} /></div>
                <div className="form-group"><label>Monthly platform cost ($)</label><input type="number" value={price.monthly_platform_cost} onChange={e => setPrice(f => ({ ...f, monthly_platform_cost: Number(e.target.value) }))} /></div>
                <div className="form-group"><label>Filing cost/quarter ($)</label><input type="number" value={price.filing_cost_per_quarter} onChange={e => setPrice(f => ({ ...f, filing_cost_per_quarter: Number(e.target.value) }))} /></div>
                <div className="form-group"><label>Support hrs/month</label><input type="number" step="0.5" value={price.support_hours_per_month} onChange={e => setPrice(f => ({ ...f, support_hours_per_month: Number(e.target.value) }))} /></div>
                <div className="form-group"><label>Support rate ($/hr)</label><input type="number" value={price.support_hourly_rate} onChange={e => setPrice(f => ({ ...f, support_hourly_rate: Number(e.target.value) }))} /></div>
                <div className="form-group"><label>Target margin (%)</label><input type="number" value={price.desired_margin_pct} onChange={e => setPrice(f => ({ ...f, desired_margin_pct: Number(e.target.value) }))} /></div>
              </div>
              <button className="btn btn-primary" onClick={calcPrice} disabled={priceLoading}>{priceLoading ? 'Calculating…' : 'Calculate pricing'}</button>
            </div>
          </div>
          <div>
            {priceResult && (
              <>
                <div className="card" style={{ marginBottom: 12 }}>
                  <div className="card-header"><h3>Your pricing</h3></div>
                  <div style={{ padding: 16 }}>
                    <div className="metrics-grid" style={{ gridTemplateColumns: 'repeat(2,1fr)', marginBottom: 12 }}>
                      <div className="metric-card"><div className="metric-label">Price/employee/mo</div><div className="metric-value" style={{ color: 'var(--blue)' }}>{fmt(priceResult.pricing.price_per_employee_per_month)}</div></div>
                      <div className="metric-card"><div className="metric-label">Monthly revenue</div><div className="metric-value" style={{ color: 'var(--green)' }}>{fmt(priceResult.pricing.total_monthly_revenue)}</div></div>
                      <div className="metric-card"><div className="metric-label">Monthly profit</div><div className="metric-value">{fmt(priceResult.pricing.total_monthly_profit)}</div></div>
                      <div className="metric-card"><div className="metric-label">Margin</div><div className="metric-value">{fmtPct(priceResult.pricing.actual_margin_pct)}</div></div>
                    </div>
                    <div style={{ fontSize: 13, fontWeight: 500, marginBottom: 8 }}>vs competitors</div>
                    <div style={{ fontSize: 13, padding: '6px 0', color: 'var(--text2)' }}>Gusto: {fmt(priceResult.market_comparison.gusto_estimated_monthly)}/mo · {priceResult.market_comparison.vs_gusto}</div>
                  </div>
                </div>
                <div className="card">
                  <div className="card-header"><h3>Suggested tier pricing</h3></div>
                  <div style={{ padding: 16 }}>
                    {priceResult.suggested_tiers.map(t => (
                      <div key={t.name} style={{ display: 'flex', justifyContent: 'space-between', padding: '8px 0', borderBottom: '1px solid var(--border)', fontSize: 13 }}>
                        <div><span style={{ fontWeight: 500 }}>{t.name}</span> <span style={{ color: 'var(--text3)' }}>{t.employees} employees</span></div>
                        <span style={{ fontWeight: 600 }}>{t.price}</span>
                      </div>
                    ))}
                  </div>
                </div>
              </>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
