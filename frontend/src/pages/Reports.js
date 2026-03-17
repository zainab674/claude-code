import React, { useState, useEffect } from 'react';
import * as api from '../services/api';

const fmt = (n) => new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD' }).format(n || 0);
const pct = (n) => `${Number(n || 0).toFixed(2)}%`;

function MetricCard({ label, value, sub, accent }) {
  return (
    <div className="metric-card">
      <div className="metric-label">{label}</div>
      <div className="metric-value" style={accent ? { color: 'var(--green)' } : {}}>{value}</div>
      {sub && <div className="metric-delta">{sub}</div>}
    </div>
  );
}

export default function Reports() {
  const year = new Date().getFullYear();
  const [tab, setTab] = useState('ytd');
  const [ytd, setYtd] = useState(null);
  const [dept, setDept] = useState(null);
  const [empYtd, setEmpYtd] = useState(null);
  const [tax, setTax] = useState(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    setLoading(true);
    Promise.all([
      api.getYtdSummary(year),
      api.getByDepartment(year),
      api.getEmployeeYtd(year),
      api.getTaxLiability(year),
    ]).then(([y, d, e, t]) => {
      setYtd(y); setDept(d); setEmpYtd(e); setTax(t);
    }).finally(() => setLoading(false));
  }, [year]);

  const downloadCsv = async (type) => {
    const paths = {
      employees: '/export/employees',
      history: '/export/payroll-history',
      ytd: '/export/employee-ytd',
    };
    const token = localStorage.getItem('payroll_token');
    const res = await fetch(`${process.env.REACT_APP_API_URL || 'http://localhost:8000'}${paths[type]}`,
      { headers: { Authorization: `Bearer ${token}` } });
    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url; a.download = `${type}-${year}.csv`; a.click();
  };

  return (
    <div className="page">
      <div className="page-header">
        <h1>Reports</h1>
        <div style={{ display: 'flex', gap: 8 }}>
          {['employees','history','ytd'].map(t => (
            <button key={t} className="btn" onClick={() => downloadCsv(t)}>↓ {t.replace('_',' ')} CSV</button>
          ))}
        </div>
      </div>

      <div className="tab-bar">
        {[['ytd','YTD Summary'],['dept','By Department'],['emp','Employee YTD'],['tax','Tax Liability']].map(([id, label]) => (
          <button key={id} className={`tab-btn ${tab === id ? 'active' : ''}`} onClick={() => setTab(id)}>{label}</button>
        ))}
      </div>

      {loading && <div style={{ padding: 48, textAlign: 'center', color: 'var(--text3)' }}>Loading reports…</div>}

      {/* YTD Summary */}
      {!loading && tab === 'ytd' && ytd && (
        <>
          <div className="metrics-grid">
            <MetricCard label="Pay runs" value={ytd.run_count} sub={`${year} YTD`} />
            <MetricCard label="Total gross" value={fmt(ytd.total_gross)} />
            <MetricCard label="Total net paid" value={fmt(ytd.total_net)} accent />
            <MetricCard label="True total cost" value={fmt(ytd.true_total_cost)} sub="Wages + employer taxes" />
            <MetricCard label="Employee taxes" value={fmt(ytd.total_employee_taxes)} />
            <MetricCard label="Employer taxes" value={fmt(ytd.total_employer_taxes)} />
            <MetricCard label="Pre-tax deductions" value={fmt(ytd.total_deductions)} />
            <MetricCard label="Effective tax rate" value={pct(ytd.effective_tax_rate)} />
          </div>
          <div className="card">
            <div className="card-header"><h3>Cost breakdown</h3></div>
            <div style={{ padding: 16 }}>
              <div className="preview-box">
                {[
                  ['Gross wages', fmt(ytd.total_gross)],
                  ['Pre-tax deductions', `(${fmt(ytd.total_deductions)})`],
                  ['Employee taxes withheld', `(${fmt(ytd.total_employee_taxes)})`],
                  ['Net paid to employees', fmt(ytd.total_net)],
                  ['+ Employer FICA / FUTA', fmt(ytd.total_employer_taxes)],
                  ['= TRUE payroll cost', fmt(ytd.true_total_cost)],
                ].map(([l, v]) => (
                  <div key={l} className={`preview-row ${l.startsWith('=') ? 'total' : ''}`}>
                    <span style={{ color: 'var(--text2)' }}>{l}</span>
                    <span style={{ fontWeight: l.startsWith('=') ? 700 : 400 }}>{v}</span>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </>
      )}

      {/* By Department */}
      {!loading && tab === 'dept' && dept && (
        <div className="card">
          <table className="table">
            <thead><tr><th>Department</th><th>Employees</th><th>Gross wages</th><th>Avg salary</th><th>% of payroll</th></tr></thead>
            <tbody>
              {(dept.departments || []).map(d => {
                const pctPayroll = dept.total_gross ? (d.gross / dept.total_gross * 100).toFixed(1) : '0';
                const avg = d.headcount ? d.gross / d.headcount : 0;
                return (
                  <tr key={d.department}>
                    <td style={{ fontWeight: 500 }}>{d.department || 'Unassigned'}</td>
                    <td>{d.headcount}</td>
                    <td style={{ fontWeight: 600 }}>{fmt(d.gross)}</td>
                    <td style={{ color: 'var(--text3)' }}>{fmt(avg)}</td>
                    <td>
                      <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                        <div style={{ flex: 1, height: 6, background: 'var(--bg3)', borderRadius: 99, overflow: 'hidden', minWidth: 80 }}>
                          <div style={{ height: '100%', width: `${pctPayroll}%`, background: 'var(--blue)', borderRadius: 99 }} />
                        </div>
                        <span style={{ fontSize: 12, color: 'var(--text3)', minWidth: 35 }}>{pctPayroll}%</span>
                      </div>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}

      {/* Employee YTD */}
      {!loading && tab === 'emp' && empYtd && (
        <div className="card">
          <table className="table">
            <thead><tr><th>Employee</th><th>Dept</th><th>YTD Gross</th><th>Federal tax</th><th>State tax</th><th>SS</th><th>Medicare</th><th>YTD Net</th></tr></thead>
            <tbody>
              {(empYtd.employees || []).map(e => (
                <tr key={e.employee_id}>
                  <td style={{ fontWeight: 500 }}>{e.name}</td>
                  <td style={{ color: 'var(--text3)', fontSize: 12 }}>{e.department || '—'}</td>
                  <td>{fmt(e.ytd_gross)}</td>
                  <td style={{ color: 'var(--red)' }}>{fmt(e.ytd_federal)}</td>
                  <td style={{ color: 'var(--amber)' }}>{fmt(e.ytd_state)}</td>
                  <td style={{ color: 'var(--text2)' }}>{fmt(e.ytd_ss)}</td>
                  <td style={{ color: 'var(--text2)' }}>{fmt(e.ytd_medicare)}</td>
                  <td style={{ fontWeight: 600, color: 'var(--green)' }}>{fmt(e.ytd_net)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* Tax Liability */}
      {!loading && tab === 'tax' && tax && (
        <>
          <div className="metrics-grid" style={{ marginBottom: 16 }}>
            <MetricCard label="IRS 941 deposit" value={fmt(tax.irs_941_liability?.total_941_deposit)} sub="Federal income + FICA" />
            <MetricCard label="IRS 940 FUTA" value={fmt(tax.irs_940_futa)} sub="Annual FUTA deposit" />
            <MetricCard label="State withheld" value={fmt(tax.state_income_tax_withheld)} />
            <MetricCard label="Total liability" value={fmt(tax.total_tax_liability)} accent />
          </div>
          <div className="card">
            <div className="card-header"><h3>IRS 941 breakdown</h3></div>
            <div style={{ padding: 16 }}>
              <div className="preview-box">
                {[
                  ['Federal income tax withheld', fmt(tax.irs_941_liability?.federal_income_tax_withheld)],
                  ['Employee SS (6.2%)', fmt(tax.irs_941_liability?.employee_ss)],
                  ['Employer SS (6.2%)', fmt(tax.irs_941_liability?.employer_ss)],
                  ['Employee Medicare (1.45%)', fmt(tax.irs_941_liability?.employee_medicare)],
                  ['Employer Medicare (1.45%)', fmt(tax.irs_941_liability?.employer_medicare)],
                  ['= Total 941 deposit', fmt(tax.irs_941_liability?.total_941_deposit)],
                ].map(([l, v]) => (
                  <div key={l} className={`preview-row ${l.startsWith('=') ? 'total' : ''}`}>
                    <span style={{ color: 'var(--text2)' }}>{l}</span>
                    <span style={{ fontWeight: l.startsWith('=') ? 700 : 400 }}>{v}</span>
                  </div>
                ))}
              </div>
              <p style={{ fontSize: 12, color: 'var(--text3)', marginTop: 12 }}>
                ⚠ Deposit via IRS EFTPS. Semi-weekly depositor if prior lookback period tax liability &gt; $50,000; otherwise monthly.
              </p>
            </div>
          </div>
        </>
      )}
    </div>
  );
}
