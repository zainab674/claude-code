import React, { useState, useEffect, useCallback } from 'react';
import * as api from './services/api';
import './App.css';
import Reports from './pages/Reports';
import TimeTracking from './pages/TimeTracking';
import CompanySettings from './pages/CompanySettings';
import PayPeriods from './pages/PayPeriods';
import ExportImport from './pages/ExportImport';
import AuditLog from './pages/AuditLog';
import UserManagement from './pages/UserManagement';
import Webhooks from './pages/Webhooks';
import PTOTracker from './pages/PTOTracker';
import Onboarding from './pages/Onboarding';
import ApiKeys from './pages/ApiKeys';
import Analytics from './pages/Analytics';
import Benefits from './pages/BenefitsPage';
import DirectDeposit from './pages/DirectDeposit';
import LeaveManagement from './pages/LeaveManagement';
import Contractors from './pages/ContractorsPage';
import SalaryBands from './pages/SalaryBands';
import PerformancePage from './pages/PerformancePage';
import ExpensesPage from './pages/ExpensesPage';
import CompliancePage from './pages/CompliancePage';
import JobPostings from './pages/JobPostings';
import AdminSettings from './pages/AdminSettings';
import FilingCenter from './pages/FilingCenter';
import CalculatorsExtended from './pages/CalculatorsExtended';
import Reconciliation from './pages/Reconciliation';
import NotificationBell from './components/NotificationBell';
import GlobalSearch from './components/GlobalSearch';

// ─── Utilities ──────────────────────────────────────────────
const fmt = (n) => new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD' }).format(n || 0);
const fmtDate = (d) => d ? new Date(d).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' }) : '—';
const pct = (n) => `${(n * 100).toFixed(1)}%`;

function useAuth() {
  const [user, setUser] = useState(() => {
    try { return JSON.parse(localStorage.getItem('payroll_user')); } catch { return null; }
  });
  const login = async (email, password) => {
    const res = await api.login(email, password);
    localStorage.setItem('payroll_token', res.access_token);
    localStorage.setItem('payroll_user', JSON.stringify(res.user));
    setUser(res.user);
    return res;
  };
  const logout = () => {
    localStorage.removeItem('payroll_token');
    localStorage.removeItem('payroll_user');
    setUser(null);
  };
  return { user, login, logout };
}

// ─── Auth Page ──────────────────────────────────────────────
function LoginPage({ onLogin }) {
  const [email, setEmail] = useState('admin@acme.com');
  const [password, setPassword] = useState('Admin123!');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  const submit = async (e) => {
    e.preventDefault();
    setLoading(true); setError('');
    try { await onLogin(email, password); }
    catch (err) { setError(err.message); }
    finally { setLoading(false); }
  };

  return (
    <div className="auth-wrap">
      <div className="auth-card">
        <div className="auth-logo">PayrollOS</div>
        <p className="auth-sub">Sign in to your workspace</p>
        {error && <div className="alert alert-danger">{error}</div>}
        <form onSubmit={submit}>
          <div className="form-group">
            <label>Email</label>
            <input type="email" value={email} onChange={e => setEmail(e.target.value)} required />
          </div>
          <div className="form-group">
            <label>Password</label>
            <input type="password" value={password} onChange={e => setPassword(e.target.value)} required />
          </div>
          <button className="btn btn-primary full-width" disabled={loading}>
            {loading ? 'Signing in...' : 'Sign in'}
          </button>
        </form>
        <p style={{ marginTop: 16, fontSize: 12, color: '#666', textAlign: 'center' }}>
          Demo: admin@acme.com / Admin123!
        </p>
      </div>
    </div>
  );
}

// ─── Sidebar ────────────────────────────────────────────────
const NAV = [
  { id: 'dashboard', label: 'Dashboard', icon: '▦' },
  { id: 'employees', label: 'Employees', icon: '◉' },
  { id: 'run-payroll', label: 'Run Payroll', icon: '▶' },
  { id: 'history', label: 'History', icon: '◷' },
  { id: 'paystubs', label: 'Paystubs', icon: '◧' },
  { id: 'calculators', label: 'Calculators', icon: '⊞' },
  { id: 'time', label: 'Time Tracking', icon: '⌚' },
  { id: 'pay-periods', label: 'Pay Periods', icon: '📅' },
  { id: 'reports', label: 'Reports', icon: '◈' },
  { id: 'settings', label: 'Settings', icon: '⚙' },
  { id: 'export-import', label: 'Export/Import', icon: '⇅' },
  { id: 'audit', label: 'Audit Log', icon: '◎' },
  { id: 'users', label: 'Team', icon: '◈' },
  { id: 'webhooks', label: 'Webhooks', icon: '⇅' },
  { id: 'pto', label: 'PTO', icon: '◌' },
  { id: 'onboarding', label: 'Onboarding', icon: '☑' },
  { id: 'api-keys', label: 'API Keys', icon: '⚿' },
  { id: 'analytics', label: 'Analytics', icon: '▨' },
  { id: 'benefits', label: 'Benefits', icon: '♥' },
  { id: 'direct-deposit', label: 'Direct Deposit', icon: '⬡' },
  { id: 'leave', label: 'Leave', icon: '◫' },
  { id: 'contractors', label: 'Contractors', icon: '⊕' },
  { id: 'salary-bands', label: 'Salary Bands', icon: '≡' },
  { id: 'performance', label: 'Performance', icon: '◆' },
  { id: 'expenses', label: 'Expenses', icon: '$' },
  { id: 'compliance', label: 'Compliance', icon: '✓' },
  { id: 'jobs', label: 'Recruiting', icon: '⊕' },
  { id: 'reconciliation', label: 'Reconciliation', icon: '⇌' },
  { id: 'settings', label: 'Settings', icon: '⚙' },
  { id: 'filing', label: 'Filing Center', icon: '⊞' },
  { id: 'calc-advanced', label: 'Adv. Calculators', icon: '÷' },
];

function Sidebar({ page, setPage, user, logout }) {
  return (
    <aside className="sidebar">
      <div className="sidebar-logo">
        <span className="logo-mark">P</span>
        <div>
          <div className="logo-name">PayrollOS</div>
          <div className="logo-company">{user?.email?.split('@')[1] || 'acme.com'}</div>
        </div>
      </div>
      <nav className="sidebar-nav">
        {NAV.map(n => (
          <button
            key={n.id}
            className={`nav-btn ${page === n.id ? 'active' : ''}`}
            onClick={() => setPage(n.id)}
          >
            <span className="nav-icon">{n.icon}</span>
            {n.label}
          </button>
        ))}
      </nav>
      <div className="sidebar-footer">
        <button className="nav-btn" onClick={logout}>⊗ Sign out</button>
      </div>
    </aside>
  );
}

// ─── Dashboard ──────────────────────────────────────────────
function Dashboard({ setPage }) {
  const [stats, setStats] = useState(null);
  const [runs, setRuns] = useState([]);

  useEffect(() => {
    api.getEmployees({ status: 'active' }).then(r => setStats(r));
    api.getPayrollHistory({ limit: 5 }).then(r => setRuns(r.runs || []));
  }, []);

  return (
    <div className="page">
      <div className="page-header">
        <h1>Dashboard</h1>
        <button className="btn btn-primary" onClick={() => setPage('run-payroll')}>▶ Run Payroll</button>
      </div>
      <div className="metrics-grid">
        <MetricCard label="Active Employees" value={stats?.total || '—'} delta="+2 this month" positive />
        <MetricCard label="Last Payroll" value={runs[0] ? fmt(runs[0].total_gross) : '—'} delta="Gross wages" />
        <MetricCard label="Net Paid" value={runs[0] ? fmt(runs[0].total_net) : '—'} delta="After taxes" />
        <MetricCard label="Employer Taxes" value={runs[0] ? fmt(runs[0].total_employer_taxes) : '—'} delta="FICA + FUTA" />
      </div>
      <div className="two-col">
        <div className="card">
          <div className="card-header"><h3>Recent Pay Runs</h3></div>
          <table className="table">
            <thead><tr><th>Period</th><th>Emp</th><th>Gross</th><th>Net</th><th>Status</th></tr></thead>
            <tbody>
              {runs.length === 0 && <tr><td colSpan={5} className="empty">No runs yet</td></tr>}
              {runs.map(r => (
                <tr key={r.id}>
                  <td>{fmtDate(r.created_at)}</td>
                  <td>{r.employee_count}</td>
                  <td>{fmt(r.total_gross)}</td>
                  <td>{fmt(r.total_net)}</td>
                  <td><Badge status={r.status} /></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <div className="card">
          <div className="card-header"><h3>Quick Actions</h3></div>
          <div style={{ padding: '16px', display: 'flex', flexDirection: 'column', gap: 8 }}>
            {[
              ['▶ Run payroll for all employees', 'run-payroll'],
              ['◉ Add a new employee', 'employees'],
              ['◷ View payroll history', 'history'],
              ['◧ Download paystubs', 'paystubs'],
              ['⊞ Paycheck calculator', 'calculators'],
            ].map(([label, target]) => (
              <button key={target} className="btn" onClick={() => setPage(target)}
                style={{ textAlign: 'left', justifyContent: 'flex-start' }}>
                {label}
              </button>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}

function MetricCard({ label, value, delta, positive }) {
  return (
    <div className="metric-card">
      <div className="metric-label">{label}</div>
      <div className="metric-value">{value}</div>
      {delta && <div className={`metric-delta ${positive ? 'pos' : ''}`}>{delta}</div>}
    </div>
  );
}

function Badge({ status }) {
  const map = {
    active: 'success', completed: 'success', approved: 'success',
    pending: 'warning', processing: 'warning', draft: 'warning',
    terminated: 'danger', failed: 'danger', inactive: 'danger',
  };
  return <span className={`badge badge-${map[status] || 'info'}`}>{status}</span>;
}

// ─── Employees ──────────────────────────────────────────────
function Employees() {
  const [employees, setEmployees] = useState([]);
  const [total, setTotal] = useState(0);
  const [search, setSearch] = useState('');
  const [showForm, setShowForm] = useState(false);
  const [editing, setEditing] = useState(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    const r = await api.getEmployees({ search: search || undefined });
    setEmployees(r.employees || []);
    setTotal(r.total || 0);
    setLoading(false);
  }, [search]);

  useEffect(() => { load(); }, [load]);

  const handleSave = async (data) => {
    if (editing) await api.updateEmployee(editing.id, data);
    else await api.createEmployee(data);
    setShowForm(false);
    setEditing(null);
    load();
  };

  const handleTerminate = async (emp) => {
    if (window.confirm(`Terminate ${emp.full_name}?`)) {
      await api.deleteEmployee(emp.id);
      load();
    }
  };

  return (
    <div className="page">
      <div className="page-header">
        <h1>Employees <span className="count-badge">{total}</span></h1>
        <div style={{ display: 'flex', gap: 8 }}>
          <input className="search-input" placeholder="Search..." value={search}
            onChange={e => setSearch(e.target.value)} />
          <button className="btn btn-primary" onClick={() => { setEditing(null); setShowForm(true); }}>
            + Add Employee
          </button>
        </div>
      </div>

      {showForm && (
        <EmployeeForm
          initial={editing}
          onSave={handleSave}
          onCancel={() => { setShowForm(false); setEditing(null); }}
        />
      )}

      <div className="card">
        <table className="table">
          <thead>
            <tr>
              <th>Name</th><th>Title</th><th>Department</th>
              <th>Pay Type</th><th>Pay Rate</th><th>Status</th><th></th>
            </tr>
          </thead>
          <tbody>
            {loading && <tr><td colSpan={7} className="empty">Loading...</td></tr>}
            {!loading && employees.length === 0 && <tr><td colSpan={7} className="empty">No employees found</td></tr>}
            {employees.map(emp => (
              <tr key={emp.id}>
                <td>
                  <div style={{ fontWeight: 500 }}>{emp.full_name}</div>
                  <div style={{ fontSize: 12, color: '#666' }}>{emp.email}</div>
                </td>
                <td>{emp.job_title || '—'}</td>
                <td>{emp.department || '—'}</td>
                <td><span className="badge badge-info">{emp.pay_type}</span></td>
                <td>
                  {emp.pay_type === 'salary'
                    ? `${fmt(emp.pay_rate)}/yr`
                    : `${fmt(emp.pay_rate)}/hr`}
                </td>
                <td><Badge status={emp.status} /></td>
                <td>
                  <button className="btn btn-sm" onClick={() => { setEditing(emp); setShowForm(true); }}>Edit</button>
                  {emp.status === 'active' && (
                    <button className="btn btn-sm btn-danger" onClick={() => handleTerminate(emp)}>×</button>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function EmployeeForm({ initial, onSave, onCancel }) {
  const [form, setForm] = useState(initial || {
    first_name: '', last_name: '', email: '', phone: '',
    hire_date: new Date().toISOString().split('T')[0],
    pay_type: 'salary', pay_rate: '', pay_frequency: 'biweekly',
    department: '', job_title: '',
    filing_status: 'single', state_code: 'NY',
    federal_allowances: 0, additional_federal_withholding: 0,
    health_insurance_deduction: 0, dental_deduction: 0, vision_deduction: 0,
    retirement_401k_pct: 0, hsa_deduction: 0, garnishment_amount: 0,
  });
  const [tab, setTab] = useState('basic');
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');

  const set = (k, v) => setForm(f => ({ ...f, [k]: v }));

  const submit = async (e) => {
    e.preventDefault();
    setSaving(true); setError('');
    try { await onSave(form); }
    catch (err) { setError(err.message); setSaving(false); }
  };

  return (
    <div className="card" style={{ marginBottom: 16 }}>
      <div className="card-header">
        <h3>{initial ? 'Edit Employee' : 'New Employee'}</h3>
        <button className="btn" onClick={onCancel}>Cancel</button>
      </div>
      <div style={{ padding: 16 }}>
        {error && <div className="alert alert-danger">{error}</div>}
        <div className="tab-bar">
          {['basic', 'tax', 'benefits'].map(t => (
            <button key={t} className={`tab-btn ${tab === t ? 'active' : ''}`} onClick={() => setTab(t)}>
              {t.charAt(0).toUpperCase() + t.slice(1)}
            </button>
          ))}
        </div>
        <form onSubmit={submit}>
          {tab === 'basic' && (
            <div className="form-grid">
              <Field label="First name *" value={form.first_name} onChange={v => set('first_name', v)} required />
              <Field label="Last name *" value={form.last_name} onChange={v => set('last_name', v)} required />
              <Field label="Email" value={form.email} onChange={v => set('email', v)} type="email" />
              <Field label="Phone" value={form.phone} onChange={v => set('phone', v)} />
              <Field label="Hire date *" value={form.hire_date} onChange={v => set('hire_date', v)} type="date" required />
              <SelectField label="Pay type" value={form.pay_type} onChange={v => set('pay_type', v)}
                options={[['salary','Salary'],['hourly','Hourly'],['contract','Contract']]} />
              <Field label={form.pay_type === 'salary' ? 'Annual salary ($) *' : 'Hourly rate ($) *'}
                value={form.pay_rate} onChange={v => set('pay_rate', v)} type="number" step="0.01" required />
              <SelectField label="Pay frequency" value={form.pay_frequency} onChange={v => set('pay_frequency', v)}
                options={[['biweekly','Bi-weekly'],['weekly','Weekly'],['semimonthly','Semi-monthly'],['monthly','Monthly']]} />
              <Field label="Department" value={form.department} onChange={v => set('department', v)} />
              <Field label="Job title" value={form.job_title} onChange={v => set('job_title', v)} />
            </div>
          )}
          {tab === 'tax' && (
            <div className="form-grid">
              <SelectField label="Filing status" value={form.filing_status} onChange={v => set('filing_status', v)}
                options={[['single','Single'],['married','Married'],['head_of_household','Head of household']]} />
              <SelectField label="State" value={form.state_code} onChange={v => set('state_code', v)}
                options={['NY','CA','TX','FL','IL','PA','OH','GA','NC','MI','NJ','VA','WA','MA','AZ'].map(s => [s, s])} />
              <Field label="Federal allowances" value={form.federal_allowances} onChange={v => set('federal_allowances', Number(v))} type="number" />
              <Field label="Extra federal withholding ($)" value={form.additional_federal_withholding}
                onChange={v => set('additional_federal_withholding', Number(v))} type="number" step="0.01" />
            </div>
          )}
          {tab === 'benefits' && (
            <div className="form-grid">
              <Field label="Health insurance ($/period)" value={form.health_insurance_deduction}
                onChange={v => set('health_insurance_deduction', Number(v))} type="number" step="0.01" />
              <Field label="Dental ($/period)" value={form.dental_deduction}
                onChange={v => set('dental_deduction', Number(v))} type="number" step="0.01" />
              <Field label="Vision ($/period)" value={form.vision_deduction}
                onChange={v => set('vision_deduction', Number(v))} type="number" step="0.01" />
              <Field label="401(k) contribution %" value={(form.retirement_401k_pct * 100).toFixed(1)}
                onChange={v => set('retirement_401k_pct', Number(v) / 100)} type="number" step="0.1" max="100" />
              <Field label="HSA ($/period)" value={form.hsa_deduction}
                onChange={v => set('hsa_deduction', Number(v))} type="number" step="0.01" />
              <Field label="Garnishment ($/period)" value={form.garnishment_amount}
                onChange={v => set('garnishment_amount', Number(v))} type="number" step="0.01" />
            </div>
          )}
          <div style={{ marginTop: 16 }}>
            <button className="btn btn-primary" type="submit" disabled={saving}>
              {saving ? 'Saving...' : 'Save employee'}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

function Field({ label, value, onChange, type = 'text', ...rest }) {
  return (
    <div className="form-group">
      <label>{label}</label>
      <input type={type} value={value ?? ''} onChange={e => onChange(e.target.value)} {...rest} />
    </div>
  );
}

function SelectField({ label, value, onChange, options }) {
  return (
    <div className="form-group">
      <label>{label}</label>
      <select value={value} onChange={e => onChange(e.target.value)}>
        {options.map(o => Array.isArray(o)
          ? <option key={o[0]} value={o[0]}>{o[1]}</option>
          : <option key={o} value={o}>{o}</option>
        )}
      </select>
    </div>
  );
}

// ─── Run Payroll ─────────────────────────────────────────────
function RunPayroll() {
  const [step, setStep] = useState(1);
  const [periodStart, setPeriodStart] = useState(new Date().toISOString().split('T')[0]);
  const [periodEnd, setPeriodEnd] = useState(new Date().toISOString().split('T')[0]);
  const [payDate, setPayDate] = useState('');
  const [employees, setEmployees] = useState([]);
  const [hours, setHours] = useState({});
  const [preview, setPreview] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [result, setResult] = useState(null);

  useEffect(() => {
    api.getEmployees({ status: 'active' }).then(r => {
      setEmployees(r.employees || []);
      const h = {};
      (r.employees || []).forEach(e => {
        h[e.id] = { employee_id: e.id, regular_hours: 80, overtime_hours: 0, bonus_pay: 0 };
      });
      setHours(h);
    });
  }, []);

  const doPreview = async () => {
    setLoading(true); setError('');
    try {
      const res = await api.previewPayroll({
        period_start: periodStart,
        period_end: periodEnd,
        hours_overrides: Object.values(hours),
      });
      setPreview(res);
      setStep(3);
    } catch (e) { setError(e.message); }
    finally { setLoading(false); }
  };

  const doRun = async () => {
    setLoading(true); setError('');
    try {
      const res = await api.runPayroll({
        period_start: periodStart,
        period_end: periodEnd,
        pay_date: payDate || periodEnd,
        hours_overrides: Object.values(hours),
      });
      setResult(res);
      setStep(4);
    } catch (e) { setError(e.message); }
    finally { setLoading(false); }
  };

  const setHour = (id, field, val) =>
    setHours(h => ({ ...h, [id]: { ...h[id], [field]: Number(val) } }));

  return (
    <div className="page">
      <div className="page-header"><h1>Run Payroll</h1></div>
      <div className="steps-bar">
        {['Period', 'Hours & Extras', 'Preview', 'Done'].map((s, i) => (
          <div key={s} className={`step ${step > i + 1 ? 'done' : step === i + 1 ? 'active' : ''}`}>
            <span className="step-num">{step > i + 1 ? '✓' : i + 1}</span> {s}
          </div>
        ))}
      </div>

      {error && <div className="alert alert-danger">{error}</div>}

      {step === 1 && (
        <div className="card" style={{ maxWidth: 500 }}>
          <div className="card-header"><h3>Pay period</h3></div>
          <div style={{ padding: 16 }}>
            <div className="form-grid">
              <Field label="Period start" value={periodStart} onChange={setPeriodStart} type="date" />
              <Field label="Period end" value={periodEnd} onChange={setPeriodEnd} type="date" />
              <Field label="Pay date" value={payDate} onChange={setPayDate} type="date" />
            </div>
            <button className="btn btn-primary" onClick={() => setStep(2)}>Next →</button>
          </div>
        </div>
      )}

      {step === 2 && (
        <div className="card">
          <div className="card-header"><h3>Hours & adjustments ({employees.length} employees)</h3></div>
          <table className="table">
            <thead>
              <tr>
                <th>Employee</th><th>Reg. hours</th><th>OT hours</th><th>Bonus ($)</th>
              </tr>
            </thead>
            <tbody>
              {employees.map(e => (
                <tr key={e.id}>
                  <td>
                    <div style={{ fontWeight: 500 }}>{e.full_name}</div>
                    <div style={{ fontSize: 12, color: '#666' }}>{e.job_title} · {e.pay_type}</div>
                  </td>
                  <td>
                    <input type="number" className="inline-input" value={hours[e.id]?.regular_hours || 80}
                      onChange={ev => setHour(e.id, 'regular_hours', ev.target.value)} />
                  </td>
                  <td>
                    <input type="number" className="inline-input" value={hours[e.id]?.overtime_hours || 0}
                      onChange={ev => setHour(e.id, 'overtime_hours', ev.target.value)} />
                  </td>
                  <td>
                    <input type="number" className="inline-input" value={hours[e.id]?.bonus_pay || 0}
                      onChange={ev => setHour(e.id, 'bonus_pay', ev.target.value)} />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          <div style={{ padding: 16, display: 'flex', gap: 8 }}>
            <button className="btn" onClick={() => setStep(1)}>← Back</button>
            <button className="btn btn-primary" onClick={doPreview} disabled={loading}>
              {loading ? 'Calculating...' : '↻ Preview payroll'}
            </button>
          </div>
        </div>
      )}

      {step === 3 && preview && (
        <>
          <div className="metrics-grid">
            <MetricCard label="Employees" value={preview.employee_count} />
            <MetricCard label="Total Gross" value={fmt(preview.totals.gross)} />
            <MetricCard label="Total Taxes" value={fmt(preview.totals.employee_taxes)} />
            <MetricCard label="Total Net Pay" value={fmt(preview.totals.net)} />
          </div>
          <div className="card">
            <div className="card-header"><h3>Per-employee breakdown</h3></div>
            <table className="table">
              <thead>
                <tr>
                  <th>Employee</th><th>Gross</th><th>Fed Tax</th><th>SS+Med</th>
                  <th>State</th><th>Deductions</th><th>Net Pay</th>
                </tr>
              </thead>
              <tbody>
                {preview.items.map(item => (
                  <tr key={item.employee_id}>
                    <td>
                      <div style={{ fontWeight: 500 }}>{item.employee_name}</div>
                      <div style={{ fontSize: 12, color: '#666' }}>{item.department}</div>
                    </td>
                    <td>{fmt(item.gross_pay)}</td>
                    <td>{fmt(item.federal_income_tax)}</td>
                    <td>{fmt(item.social_security_tax + item.medicare_tax)}</td>
                    <td>{fmt(item.state_income_tax)}</td>
                    <td>{fmt(item.total_pretax_deductions)}</td>
                    <td style={{ fontWeight: 600, color: '#1a7a3c' }}>{fmt(item.net_pay)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div style={{ display: 'flex', gap: 8 }}>
            <button className="btn" onClick={() => setStep(2)}>← Back</button>
            <button className="btn btn-primary" onClick={doRun} disabled={loading}>
              {loading ? 'Running...' : '✓ Approve & Run Payroll'}
            </button>
          </div>
        </>
      )}

      {step === 4 && result && (
        <div className="card" style={{ maxWidth: 500, textAlign: 'center', padding: 32 }}>
          <div style={{ fontSize: 48, marginBottom: 16 }}>✓</div>
          <h2>Payroll Complete!</h2>
          <p style={{ color: '#666', margin: '8px 0 24px' }}>
            {result.employee_count} employees · {fmt(result.totals.gross)} gross · {fmt(result.totals.net)} net
          </p>
          <div className="metrics-grid" style={{ marginBottom: 16 }}>
            <MetricCard label="Gross" value={fmt(result.totals.gross)} />
            <MetricCard label="Taxes" value={fmt(result.totals.employee_taxes)} />
            <MetricCard label="Employer Cost" value={fmt(result.totals.employer_taxes)} />
            <MetricCard label="Net Paid" value={fmt(result.totals.net)} />
          </div>
          <p style={{ fontSize: 12, color: '#888' }}>
            Pay run ID: {result.pay_run_id}<br />
            Paystub PDFs are being generated in the background.
          </p>
        </div>
      )}
    </div>
  );
}

// ─── History ─────────────────────────────────────────────────
function History() {
  const [runs, setRuns] = useState([]);
  const [total, setTotal] = useState(0);
  const [selected, setSelected] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setLoading(true);
    api.getPayrollHistory().then(r => {
      setRuns(r.runs || []);
      setTotal(r.total || 0);
      setLoading(false);
    });
  }, []);

  const viewRun = async (id) => {
    const r = await api.getPayRun(id);
    setSelected(r);
  };

  return (
    <div className="page">
      <div className="page-header">
        <h1>Payroll History <span className="count-badge">{total}</span></h1>
      </div>

      <div className={selected ? 'two-col' : ''}>
        <div className="card">
          <table className="table">
            <thead>
              <tr><th>Date</th><th>Employees</th><th>Gross</th><th>Emp Taxes</th><th>Net</th><th>Status</th><th></th></tr>
            </thead>
            <tbody>
              {loading && <tr><td colSpan={7} className="empty">Loading...</td></tr>}
              {!loading && runs.length === 0 && <tr><td colSpan={7} className="empty">No payroll runs yet</td></tr>}
              {runs.map(r => (
                <tr key={r.id} className={selected?.id === r.id ? 'row-selected' : ''}>
                  <td>{fmtDate(r.created_at)}</td>
                  <td>{r.employee_count}</td>
                  <td>{fmt(r.total_gross)}</td>
                  <td>{fmt(r.total_employee_taxes)}</td>
                  <td style={{ fontWeight: 600, color: '#1a7a3c' }}>{fmt(r.total_net)}</td>
                  <td><Badge status={r.status} /></td>
                  <td><button className="btn btn-sm" onClick={() => viewRun(r.id)}>View</button></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        {selected && (
          <div className="card">
            <div className="card-header">
              <h3>Pay Run Detail</h3>
              <button className="btn btn-sm" onClick={() => setSelected(null)}>✕</button>
            </div>
            <div style={{ padding: '0 16px 16px' }}>
              <div className="preview-box">
                {[
                  ['Gross wages', fmt(selected.total_gross)],
                  ['Employee taxes', `(${fmt(selected.total_employee_taxes)})`],
                  ['Pre-tax deductions', `(${fmt(selected.total_deductions)})`],
                  ['Employer taxes (cost)', fmt(selected.total_employer_taxes)],
                  ['Net pay', fmt(selected.total_net)],
                ].map(([l, v]) => (
                  <div key={l} className="preview-row">
                    <span>{l}</span><span style={{ fontWeight: l === 'Net pay' ? 600 : 400 }}>{v}</span>
                  </div>
                ))}
              </div>
              {selected.items && (
                <table className="table" style={{ marginTop: 12 }}>
                  <thead><tr><th>Employee</th><th>Gross</th><th>Net</th></tr></thead>
                  <tbody>
                    {selected.items.map(i => (
                      <tr key={i.id}>
                        <td>{i.employee_id.slice(0, 8)}…</td>
                        <td>{fmt(i.gross_pay)}</td>
                        <td>{fmt(i.net_pay)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

// ─── Paystubs ─────────────────────────────────────────────────
function Paystubs() {
  const [stubs, setStubs] = useState([]);
  const [selected, setSelected] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api.getPaystubs().then(r => { setStubs(r || []); setLoading(false); });
  }, []);

  const view = async (id) => {
    const r = await api.getPaystub(id);
    setSelected(r);
  };

  return (
    <div className="page">
      <div className="page-header"><h1>Paystubs</h1></div>
      <div className="two-col">
        <div className="card">
          <table className="table">
            <thead><tr><th>Employee ID</th><th>Pay Run</th><th>Date</th><th></th></tr></thead>
            <tbody>
              {loading && <tr><td colSpan={4} className="empty">Loading...</td></tr>}
              {!loading && stubs.length === 0 && <tr><td colSpan={4} className="empty">No paystubs yet — run payroll first</td></tr>}
              {stubs.map(s => (
                <tr key={s.id}>
                  <td style={{ fontFamily: 'monospace', fontSize: 11 }}>{s.employee_id.slice(0, 12)}…</td>
                  <td style={{ fontFamily: 'monospace', fontSize: 11 }}>{s.pay_run_id.slice(0, 8)}…</td>
                  <td>{fmtDate(s.created_at)}</td>
                  <td>
                    <button className="btn btn-sm" onClick={() => view(s.id)}>View</button>
                    <a className="btn btn-sm" href={api.downloadPaystub(s.id)} target="_blank" rel="noreferrer">PDF</a>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        {selected && (
          <div className="card">
            <div className="card-header">
              <h3>Paystub Preview</h3>
              <div style={{ display: 'flex', gap: 8 }}>
                <a className="btn btn-primary" href={api.downloadPaystub(selected.paystub_id)}
                  target="_blank" rel="noreferrer">↓ Download PDF</a>
                <button className="btn btn-sm" onClick={() => setSelected(null)}>✕</button>
              </div>
            </div>
            <div style={{ padding: 16 }}>
              <div style={{ marginBottom: 16, padding: 12, background: '#f8f8f8', borderRadius: 8 }}>
                <div style={{ fontWeight: 600, fontSize: 15 }}>
                  {selected.employee.first_name} {selected.employee.last_name}
                </div>
                <div style={{ color: '#666', fontSize: 12 }}>{selected.employee.job_title}</div>
                <div style={{ fontSize: 12, marginTop: 4 }}>
                  {selected.pay_period.period_start} – {selected.pay_period.period_end}
                </div>
              </div>
              <div className="preview-box">
                {[
                  ['Regular pay', fmt(selected.earnings.regular_pay)],
                  ['Overtime', fmt(selected.earnings.overtime_pay)],
                  ['Bonus', fmt(selected.earnings.bonus_pay)],
                  ['Gross pay', fmt(selected.earnings.gross_pay)],
                  ['– Health/Dental/Vision', `(${fmt(selected.deductions.health_insurance + selected.deductions.dental_insurance + selected.deductions.vision_insurance)})`],
                  ['– 401(k)', `(${fmt(selected.deductions.retirement_401k)})`],
                  ['– Federal income tax', `(${fmt(selected.taxes.federal_income_tax)})`],
                  ['– State income tax', `(${fmt(selected.taxes.state_income_tax)})`],
                  ['– Social Security', `(${fmt(selected.taxes.social_security_tax)})`],
                  ['– Medicare', `(${fmt(selected.taxes.medicare_tax)})`],
                  ['NET PAY', fmt(selected.net_pay)],
                ].map(([l, v]) => (
                  <div key={l} className={`preview-row ${l === 'NET PAY' ? 'total' : ''}`}>
                    <span>{l}</span><span>{v}</span>
                  </div>
                ))}
              </div>
              <div style={{ marginTop: 12, padding: 10, background: '#f0f8f0', borderRadius: 6, fontSize: 12 }}>
                <strong>YTD:</strong> Gross {fmt(selected.ytd.gross)} · Fed {fmt(selected.ytd.federal_tax)} · SS {fmt(selected.ytd.social_security)}
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

// ─── Calculators ─────────────────────────────────────────────
function Calculators() {
  const [form, setForm] = useState({
    pay_type: 'salary', annual_salary: 75000, hourly_rate: 25,
    pay_frequency: 'biweekly', filing_status: 'single', state_code: 'NY',
    regular_hours: 80, overtime_hours: 0, health_insurance: 0,
    retirement_401k_pct: 0, bonus_pay: 0,
  });
  const [result, setResult] = useState(null);
  const [loading, setLoading] = useState(false);

  const set = (k, v) => setForm(f => ({ ...f, [k]: v }));

  const calculate = async () => {
    setLoading(true);
    try {
      const res = await api.calculatePaycheck(form);
      setResult(res);
    } catch (e) { alert(e.message); }
    finally { setLoading(false); }
  };

  return (
    <div className="page">
      <div className="page-header"><h1>Payroll Calculators</h1></div>
      <div className="two-col">
        <div className="card">
          <div className="card-header"><h3>Paycheck calculator</h3></div>
          <div style={{ padding: 16 }}>
            <div className="form-grid">
              <SelectField label="Pay type" value={form.pay_type} onChange={v => set('pay_type', v)}
                options={[['salary','Salary'],['hourly','Hourly']]} />
              {form.pay_type === 'salary'
                ? <Field label="Annual salary ($)" value={form.annual_salary} onChange={v => set('annual_salary', Number(v))} type="number" />
                : <Field label="Hourly rate ($)" value={form.hourly_rate} onChange={v => set('hourly_rate', Number(v))} type="number" step="0.01" />
              }
              <SelectField label="Pay frequency" value={form.pay_frequency} onChange={v => set('pay_frequency', v)}
                options={[['biweekly','Bi-weekly (26)'],['weekly','Weekly (52)'],['semimonthly','Semi-monthly (24)'],['monthly','Monthly (12)']]} />
              <SelectField label="Filing status" value={form.filing_status} onChange={v => set('filing_status', v)}
                options={[['single','Single'],['married','Married'],['head_of_household','Head of household']]} />
              <SelectField label="State" value={form.state_code} onChange={v => set('state_code', v)}
                options={[['NY','New York (6.85%)'],['CA','California (9.3%)'],['TX','Texas (0%)'],['FL','Florida (0%)'],['WA','Washington (0%)'],['IL','Illinois (4.95%)'],['MA','Massachusetts (5%)']] } />
              <Field label="Regular hours (per period)" value={form.regular_hours} onChange={v => set('regular_hours', Number(v))} type="number" />
              <Field label="Overtime hours" value={form.overtime_hours} onChange={v => set('overtime_hours', Number(v))} type="number" />
              <Field label="Health insurance ($/period)" value={form.health_insurance} onChange={v => set('health_insurance', Number(v))} type="number" step="0.01" />
              <Field label="401(k) %" value={(form.retirement_401k_pct * 100).toFixed(1)}
                onChange={v => set('retirement_401k_pct', Number(v) / 100)} type="number" step="0.1" />
              <Field label="Bonus this period ($)" value={form.bonus_pay} onChange={v => set('bonus_pay', Number(v))} type="number" />
            </div>
            <button className="btn btn-primary" onClick={calculate} disabled={loading} style={{ marginTop: 8 }}>
              {loading ? 'Calculating...' : '⊞ Calculate'}
            </button>
          </div>
        </div>

        {result && (
          <div className="card">
            <div className="card-header"><h3>Results</h3></div>
            <div style={{ padding: 16 }}>
              <div style={{ fontSize: 28, fontWeight: 600, color: '#1a7a3c', marginBottom: 16 }}>
                {fmt(result.net_pay)} <span style={{ fontSize: 14, color: '#666', fontWeight: 400 }}>/ paycheck</span>
              </div>
              <div className="preview-box">
                {[
                  ['Gross pay', fmt(result.gross_pay)],
                  ['Pre-tax deductions', `(${fmt(result.pretax_deductions)})`],
                  ['Taxable gross', fmt(result.taxable_gross)],
                  [`Federal income tax (${result.effective_federal_rate}%)`, `(${fmt(result.federal_income_tax)})`],
                  [`State income tax (${result.effective_state_rate}%)`, `(${fmt(result.state_income_tax)})`],
                  ['Social Security (6.2%)', `(${fmt(result.social_security_tax)})`],
                  ['Medicare (1.45%)', `(${fmt(result.medicare_tax)})`],
                  ['Total taxes', `(${fmt(result.total_employee_taxes)})`],
                  ['NET PAY', fmt(result.net_pay)],
                ].map(([l, v]) => (
                  <div key={l} className={`preview-row ${l === 'NET PAY' ? 'total' : ''}`}>
                    <span>{l}</span><span>{v}</span>
                  </div>
                ))}
              </div>
              <div style={{ marginTop: 12, padding: 12, background: '#fff8e6', borderRadius: 8, fontSize: 12 }}>
                <strong>Employer true cost:</strong> {fmt(result.true_cost)}/period<br />
                <span style={{ color: '#666' }}>Includes employer FICA: {fmt(result.employer_total)}</span>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

// ─── App Shell ──────────────────────────────────────────────
export default function App() {
  const { user, login, logout } = useAuth();
  const [page, setPage] = useState('dashboard');

  if (!user) return <LoginPage onLogin={login} />;

  const pages = {
    dashboard: <Dashboard setPage={setPage} />,
    employees: <Employees />,
    'run-payroll': <RunPayroll />,
    history: <History />,
    paystubs: <Paystubs />,
    calculators: <Calculators />,
    time: <TimeTracking />,
    'pay-periods': <PayPeriods />,
    reports: <Reports />,
    settings: <CompanySettings />,
    'export-import': <ExportImport />,
    audit: <AuditLog />,
    users: <UserManagement />,
    webhooks: <Webhooks />,
    pto: <PTOTracker />,
    onboarding: <Onboarding />,
    'api-keys': <ApiKeys />,
    analytics: <Analytics />,
    benefits: <Benefits />,
    'direct-deposit': <DirectDeposit />,
    leave: <LeaveManagement />,
    contractors: <Contractors />,
    'salary-bands': <SalaryBands />,
    performance: <PerformancePage />,
    expenses: <ExpensesPage />,
    compliance: <CompliancePage />,
    jobs: <JobPostings />,
    reconciliation: <Reconciliation />,
    settings: <AdminSettings />,
    filing: <FilingCenter />,
    'calc-advanced': <CalculatorsExtended />,
  };

  return (
    <div className="app">
      <Sidebar page={page} setPage={setPage} user={user} logout={logout} />
      <div style={{ display: 'flex', flexDirection: 'column', flex: 1, minWidth: 0 }}>
        <header style={{
          display: 'flex', alignItems: 'center', gap: 12, padding: '10px 20px',
          borderBottom: '1px solid var(--border)', background: 'var(--bg)',
          position: 'sticky', top: 0, zIndex: 50,
        }}>
          <GlobalSearch onNavigate={setPage} />
          <NotificationBell onNavigate={setPage} />
          <div style={{ fontSize: 12, color: 'var(--text3)', whiteSpace: 'nowrap' }}>
            {user?.email}
          </div>
        </header>
        <main className="main">{pages[page] || <Dashboard setPage={setPage} />}</main>
      </div>
    </div>
  );
}
