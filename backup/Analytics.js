import React, { useState, useEffect, useRef } from 'react';

const BASE = process.env.REACT_APP_API_URL || 'http://localhost:8000';
const tkn = () => localStorage.getItem('payroll_token');
async function req(path) {
  const res = await fetch(`${BASE}${path}`, { headers: { Authorization: `Bearer ${tkn()}` } });
  if (!res.ok) return null;
  return res.json();
}
const fmt = n => new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD', maximumFractionDigits: 0 }).format(n || 0);

function BarChart({ data, color = 'var(--blue)', label = '' }) {
  if (!data || data.length === 0) return null;
  const max = Math.max(...data.map(d => d.value), 1);
  return (
    <div style={{ display: 'flex', alignItems: 'flex-end', gap: 4, height: 120, padding: '0 4px' }}>
      {data.map((d, i) => (
        <div key={i} style={{ flex: 1, display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 4 }}>
          <div style={{ fontSize: 9, color: 'var(--text3)', whiteSpace: 'nowrap' }}>
            {fmt(d.value).replace('$', '').replace(',000', 'k')}
          </div>
          <div style={{
            width: '100%', background: color, borderRadius: '3px 3px 0 0',
            height: `${Math.max((d.value / max) * 90, 2)}px`,
            opacity: i === data.length - 1 ? 1 : 0.6,
            transition: 'height 0.4s ease',
          }} />
          <div style={{ fontSize: 9, color: 'var(--text3)', whiteSpace: 'nowrap' }}>{d.label}</div>
        </div>
      ))}
    </div>
  );
}

function DonutChart({ segments, size = 100 }) {
  if (!segments || segments.length === 0) return null;
  const total = segments.reduce((s, x) => s + x.value, 0);
  if (total === 0) return null;

  let currentAngle = -90;
  const cx = size / 2, cy = size / 2, r = size * 0.38, innerR = size * 0.24;

  const arcs = segments.map(seg => {
    const pct = seg.value / total;
    const angle = pct * 360;
    const startAngle = (currentAngle * Math.PI) / 180;
    currentAngle += angle;
    const endAngle = (currentAngle * Math.PI) / 180;
    const x1 = cx + r * Math.cos(startAngle), y1 = cy + r * Math.sin(startAngle);
    const x2 = cx + r * Math.cos(endAngle), y2 = cy + r * Math.sin(endAngle);
    const ix1 = cx + innerR * Math.cos(startAngle), iy1 = cy + innerR * Math.sin(startAngle);
    const ix2 = cx + innerR * Math.cos(endAngle), iy2 = cy + innerR * Math.sin(endAngle);
    const large = angle > 180 ? 1 : 0;
    const path = `M ${x1} ${y1} A ${r} ${r} 0 ${large} 1 ${x2} ${y2} L ${ix2} ${iy2} A ${innerR} ${innerR} 0 ${large} 0 ${ix1} ${iy1} Z`;
    return { path, color: seg.color, label: seg.label, value: seg.value, pct: Math.round(pct * 100) };
  });

  return (
    <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`}>
      {arcs.map((arc, i) => (
        <path key={i} d={arc.path} fill={arc.color} opacity="0.85" />
      ))}
    </svg>
  );
}

function StatCard({ label, value, sub, color }) {
  return (
    <div className="metric-card">
      <div className="metric-label">{label}</div>
      <div className="metric-value" style={color ? { color } : {}}>{value}</div>
      {sub && <div className="metric-delta">{sub}</div>}
    </div>
  );
}

export default function Analytics() {
  const year = new Date().getFullYear();
  const [ytd, setYtd] = useState(null);
  const [dept, setDept] = useState(null);
  const [history, setHistory] = useState([]);
  const [taxData, setTaxData] = useState(null);
  const [employees, setEmployees] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    Promise.all([
      req(`/reports/ytd-summary?year=${year}`),
      req(`/reports/by-department?year=${year}`),
      req('/payroll/history?limit=12'),
      req(`/reports/tax-liability?year=${year}`),
      req('/employees?status=active'),
    ]).then(([y, d, h, t, e]) => {
      setYtd(y); setDept(d);
      setHistory((h?.runs || []).slice(0, 10).reverse());
      setTaxData(t);
      setEmployees(e);
      setLoading(false);
    });
  }, [year]);

  if (loading) return (
    <div className="page">
      <div style={{ padding: 48, textAlign: 'center', color: 'var(--text3)' }}>Loading analytics…</div>
    </div>
  );

  // Build bar chart data from history
  const barData = history.map(r => ({
    label: r.created_at ? new Date(r.created_at).toLocaleDateString('en-US', { month: 'short', day: 'numeric' }) : '',
    value: r.total_gross || 0,
  }));

  // Build donut from dept
  const deptColors = ['var(--blue)', 'var(--green)', 'var(--amber)', 'var(--red)', 'var(--text3)'];
  const deptSegments = (dept?.departments || []).slice(0, 5).map((d, i) => ({
    label: d.department, value: d.gross, color: deptColors[i],
  }));

  // Tax breakdown donut
  const taxSegments = taxData ? [
    { label: 'Federal Income', value: taxData.irs_941_liability?.federal_income_tax_withheld || 0, color: 'var(--red)' },
    { label: 'SS (both sides)', value: (taxData.irs_941_liability?.total_941_deposit || 0) - (taxData.irs_941_liability?.federal_income_tax_withheld || 0), color: 'var(--blue)' },
    { label: 'State', value: taxData.state_income_tax_withheld || 0, color: 'var(--amber)' },
    { label: 'FUTA/SUTA', value: (taxData.irs_940_futa || 0) + (taxData.suta || 0), color: 'var(--text3)' },
  ].filter(s => s.value > 0) : [];

  const empCount = employees?.total || 0;
  const avgGross = ytd && ytd.run_count ? ytd.total_gross / ytd.run_count : 0;
  const avgNet = ytd && ytd.run_count ? ytd.total_net / ytd.run_count : 0;

  return (
    <div className="page">
      <div className="page-header">
        <h1>Analytics <span className="count-badge">{year}</span></h1>
      </div>

      {/* Top metrics */}
      <div className="metrics-grid">
        <StatCard label="YTD gross wages"    value={fmt(ytd?.total_gross)}       sub={`${ytd?.run_count || 0} pay runs`} />
        <StatCard label="YTD net paid"        value={fmt(ytd?.total_net)}          sub={`${ytd?.effective_tax_rate || 0}% effective rate`} accent />
        <StatCard label="Total employer cost" value={fmt(ytd?.true_total_cost)}    sub="Wages + FICA + FUTA" />
        <StatCard label="Active employees"    value={empCount}                     sub={`${fmt(avgGross)} avg gross/run`} />
      </div>

      {/* Payroll trend chart */}
      <div className="card" style={{ marginBottom: 16 }}>
        <div className="card-header">
          <h3>Gross payroll per run</h3>
          <span style={{ fontSize: 12, color: 'var(--text3)' }}>Last {barData.length} runs</span>
        </div>
        <div style={{ padding: '16px 16px 8px' }}>
          {barData.length === 0
            ? <div style={{ textAlign: 'center', color: 'var(--text3)', padding: 24, fontSize: 13 }}>No payroll runs yet</div>
            : <BarChart data={barData} color="var(--blue)" />
          }
        </div>
      </div>

      <div className="two-col">
        {/* Department breakdown */}
        <div className="card">
          <div className="card-header"><h3>Payroll by department</h3></div>
          <div style={{ padding: 16, display: 'flex', gap: 20, alignItems: 'center' }}>
            <DonutChart segments={deptSegments} size={110} />
            <div style={{ flex: 1 }}>
              {(dept?.departments || []).slice(0, 5).map((d, i) => (
                <div key={d.department} style={{ display: 'flex', justifyContent: 'space-between', padding: '5px 0', fontSize: 13, borderBottom: '1px solid var(--border)' }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                    <div style={{ width: 8, height: 8, borderRadius: '50%', background: deptColors[i], flexShrink: 0 }} />
                    <span>{d.department}</span>
                    <span style={{ fontSize: 11, color: 'var(--text3)' }}>{d.headcount} emp</span>
                  </div>
                  <span style={{ fontWeight: 500 }}>{fmt(d.gross)}</span>
                </div>
              ))}
              {(dept?.departments || []).length === 0 && (
                <div style={{ color: 'var(--text3)', fontSize: 13 }}>No department data yet</div>
              )}
            </div>
          </div>
        </div>

        {/* Tax liability donut */}
        <div className="card">
          <div className="card-header"><h3>Tax liability breakdown</h3></div>
          <div style={{ padding: 16, display: 'flex', gap: 20, alignItems: 'center' }}>
            <DonutChart segments={taxSegments} size={110} />
            <div style={{ flex: 1 }}>
              {taxSegments.map(s => (
                <div key={s.label} style={{ display: 'flex', justifyContent: 'space-between', padding: '5px 0', fontSize: 13, borderBottom: '1px solid var(--border)' }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                    <div style={{ width: 8, height: 8, borderRadius: '50%', background: s.color, flexShrink: 0 }} />
                    <span>{s.label}</span>
                  </div>
                  <span style={{ fontWeight: 500 }}>{fmt(s.value)}</span>
                </div>
              ))}
              {taxSegments.length === 0 && (
                <div style={{ color: 'var(--text3)', fontSize: 13 }}>Run payroll to see tax data</div>
              )}
              {taxData && (
                <div style={{ marginTop: 12, padding: '8px 0', display: 'flex', justifyContent: 'space-between', fontSize: 13, fontWeight: 600 }}>
                  <span>Total liability</span>
                  <span style={{ color: 'var(--red)' }}>{fmt(taxData.total_tax_liability)}</span>
                </div>
              )}
            </div>
          </div>
        </div>
      </div>

      {/* Cost breakdown table */}
      <div className="card">
        <div className="card-header"><h3>YTD cost breakdown</h3></div>
        <div style={{ padding: 16 }}>
          <div className="preview-box">
            {[
              ['Gross wages', fmt(ytd?.total_gross), 'var(--text)'],
              ['Pre-tax deductions', `(${fmt(ytd?.total_deductions)})`, 'var(--text2)'],
              ['Employee taxes withheld', `(${fmt(ytd?.total_employee_taxes)})`, 'var(--text2)'],
              ['Net paid to employees', fmt(ytd?.total_net), 'var(--green)'],
              ['+ Employer FICA/FUTA', fmt(ytd?.total_employer_taxes), 'var(--text2)'],
              ['= TRUE total payroll cost', fmt(ytd?.true_total_cost), 'var(--text)'],
            ].map(([l, v, c]) => (
              <div key={l} className={`preview-row ${l.startsWith('=') ? 'total' : ''}`}>
                <span style={{ color: 'var(--text2)' }}>{l}</span>
                <span style={{ fontWeight: l.startsWith('=') ? 700 : 400, color: c }}>{v}</span>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* Per-employee cost metrics */}
      <div className="metrics-grid">
        <StatCard label="Avg gross per paycheck" value={fmt(avgGross)}        sub="All employees, per run" />
        <StatCard label="Avg net per paycheck"    value={fmt(avgNet)}          sub="After taxes + deductions" />
        <StatCard label="Avg cost per employee"   value={fmt(ytd && empCount ? ytd.true_total_cost / empCount : 0)} sub="Annual true cost" />
        <StatCard label="Payroll as % of revenue" value="—" sub="Set revenue in settings" />
      </div>
    </div>
  );
}
