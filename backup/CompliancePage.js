import React, { useState, useEffect } from 'react';

const BASE = process.env.REACT_APP_API_URL || 'http://localhost:8000';
const tkn = () => localStorage.getItem('payroll_token');
async function req(path) {
  const res = await fetch(`${BASE}${path}`, { headers: { Authorization: `Bearer ${tkn()}` } });
  if (!res.ok) return null;
  return res.json();
}

const SEV_COLOR = { critical: 'danger', warning: 'warning', info: 'info' };
const SEV_ICON = { critical: '✗', warning: '⚠', info: 'ℹ' };

export default function CompliancePage() {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);

  const runCheck = async () => {
    setLoading(true);
    const r = await req('/compliance');
    setData(r);
    setLoading(false);
  };

  useEffect(() => { runCheck(); }, []);

  const grouped = data ? {
    critical: data.issues.filter(i => i.severity === 'critical'),
    warning: data.issues.filter(i => i.severity === 'warning'),
    info: data.issues.filter(i => i.severity === 'info'),
  } : {};

  return (
    <div className="page">
      <div className="page-header">
        <h1>Compliance</h1>
        <button className="btn" onClick={runCheck} disabled={loading}>↻ Re-run checks</button>
      </div>

      {loading && <div style={{ padding: 32, textAlign: 'center', color: 'var(--text3)' }}>Running compliance checks…</div>}

      {!loading && data && (
        <>
          {/* Status banner */}
          <div className="card" style={{ marginBottom: 16, border: `1px solid var(--color-border-${data.status === 'ok' ? 'success' : data.status === 'critical' ? 'danger' : 'warning'})`, background: `var(--${data.status === 'ok' ? 'green' : data.status === 'critical' ? 'red' : 'amber'}-bg)` }}>
            <div style={{ padding: '14px 20px', display: 'flex', alignItems: 'center', gap: 16 }}>
              <span style={{ fontSize: 28 }}>{data.status === 'ok' ? '✓' : data.status === 'critical' ? '✗' : '⚠'}</span>
              <div>
                <div style={{ fontWeight: 600, fontSize: 15, color: `var(--${data.status === 'ok' ? 'green' : data.status === 'critical' ? 'red' : 'amber'})` }}>
                  {data.status === 'ok' ? 'All compliance checks passed' : `${data.total_issues} issue${data.total_issues > 1 ? 's' : ''} found`}
                </div>
                <div style={{ fontSize: 12, color: 'var(--text3)', marginTop: 2 }}>Checked {data.checked_at}</div>
              </div>
              <div style={{ marginLeft: 'auto', display: 'flex', gap: 12, fontSize: 13 }}>
                {data.critical > 0 && <span style={{ color: 'var(--red)', fontWeight: 500 }}>✗ {data.critical} critical</span>}
                {data.warnings > 0 && <span style={{ color: 'var(--amber)', fontWeight: 500 }}>⚠ {data.warnings} warnings</span>}
                {data.info > 0 && <span style={{ color: 'var(--blue)', fontWeight: 500 }}>ℹ {data.info} info</span>}
              </div>
            </div>
          </div>

          {/* Issue groups */}
          {['critical', 'warning', 'info'].map(sev => {
            const issues = grouped[sev] || [];
            if (issues.length === 0) return null;
            return (
              <div key={sev} className="card" style={{ marginBottom: 12 }}>
                <div className="card-header">
                  <h3 style={{ textTransform: 'capitalize', display: 'flex', alignItems: 'center', gap: 8 }}>
                    <span className={`badge badge-${SEV_COLOR[sev]}`}>{issues.length}</span>
                    {sev === 'critical' ? 'Critical issues' : sev === 'warning' ? 'Warnings' : 'Informational'}
                  </h3>
                </div>
                {issues.map((issue, i) => (
                  <div key={i} style={{ padding: '12px 16px', borderBottom: i < issues.length - 1 ? '1px solid var(--border)' : 'none', display: 'flex', gap: 12 }}>
                    <span style={{ fontSize: 16, color: `var(--${SEV_COLOR[sev] === 'danger' ? 'red' : SEV_COLOR[sev] === 'warning' ? 'amber' : 'blue'})`, flexShrink: 0 }}>{SEV_ICON[sev]}</span>
                    <div style={{ flex: 1 }}>
                      <div style={{ fontWeight: 500, fontSize: 13 }}>{issue.message}</div>
                      {issue.employee_name && <div style={{ fontSize: 12, color: 'var(--text3)' }}>Employee: {issue.employee_name}</div>}
                      {issue.action && <div style={{ fontSize: 12, color: 'var(--blue)', marginTop: 3 }}>→ {issue.action}</div>}
                    </div>
                    <span style={{ fontSize: 11, color: 'var(--text3)', fontFamily: 'monospace', flexShrink: 0 }}>{issue.code}</span>
                  </div>
                ))}
              </div>
            );
          })}

          {data.total_issues === 0 && (
            <div className="card" style={{ padding: 48, textAlign: 'center' }}>
              <div style={{ fontSize: 48, marginBottom: 12 }}>✓</div>
              <div style={{ fontWeight: 500, color: 'var(--green)', fontSize: 16 }}>All checks passed</div>
              <div style={{ color: 'var(--text3)', marginTop: 6 }}>No compliance issues detected</div>
            </div>
          )}
        </>
      )}
    </div>
  );
}
