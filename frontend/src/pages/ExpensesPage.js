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
const STATUS_COLOR = { pending: 'warning', approved: 'success', denied: 'danger', reimbursed: 'info' };

export default function ExpensesPage() {
  const [tab, setTab] = useState('list');
  const [data, setData] = useState(null);
  const [pending, setPending] = useState(null);
  const [report, setReport] = useState(null);
  const [employees, setEmployees] = useState([]);
  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState({ employee_id: '', expense_date: new Date().toISOString().split('T')[0], category: 'travel', description: '', amount: '', vendor: '', is_billable: false, notes: '' });
  const [error, setError] = useState('');

  const load = async () => {
    const [d, p, r, e] = await Promise.all([
      req('/expenses'), req('/expenses/pending-payroll'),
      req('/expenses/report'), req('/employees?status=active'),
    ]);
    setData(d); setPending(p); setReport(r); setEmployees(e?.employees || []);
  };
  useEffect(() => { load(); }, []);

  const submit = async (ev) => {
    ev.preventDefault(); setError('');
    try {
      await req(`/expenses?employee_id=${form.employee_id}`, { method: 'POST', body: JSON.stringify({ ...form, amount: Number(form.amount) }) });
      setShowForm(false);
      setForm({ employee_id: '', expense_date: new Date().toISOString().split('T')[0], category: 'travel', description: '', amount: '', vendor: '', is_billable: false, notes: '' });
      load();
    } catch (err) { setError(err.message); }
  };

  const approve = async (id) => { try { await req(`/expenses/${id}/approve`, { method: 'PUT' }); load(); } catch (err) { setError(err.message); } };
  const deny = async (id) => { try { await req(`/expenses/${id}/deny`, { method: 'PUT', body: JSON.stringify({ denied_reason: 'Not approved' }) }); load(); } catch (err) { setError(err.message); } };

  const reimburseAll = async () => {
    if (!pending?.by_employee?.length) return;
    const ids = pending.by_employee.flatMap(e => e.expenses.map(x => x.id));
    try { const r = await req('/expenses/batch-reimburse', { method: 'POST', body: JSON.stringify(ids) }); alert(`Reimbursed ${r.reimbursed} expenses (${fmt(r.total_amount)})`); load(); }
    catch (err) { setError(err.message); }
  };

  const empMap = Object.fromEntries(employees.map(e => [e.id, e.full_name]));
  const expenses = data?.expenses || [];

  return (
    <div className="page">
      <div className="page-header">
        <h1>Expenses</h1>
        <button className="btn btn-primary" onClick={() => setShowForm(!showForm)}>+ Submit expense</button>
      </div>
      {error && <div className="alert alert-danger">{error}</div>}

      {pending && pending.total_amount > 0 && (
        <div className="card" style={{ marginBottom: 16, border: '1px solid var(--blue)' }}>
          <div style={{ padding: '12px 16px', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <div>
              <span style={{ fontWeight: 500 }}>Pending reimbursement: {fmt(pending.total_amount)}</span>
              <span style={{ fontSize: 12, color: 'var(--text3)', marginLeft: 12 }}>{pending.total_employees} employees · {pending.by_employee?.reduce((s,e) => s + e.expenses.length, 0)} approved expenses</span>
            </div>
            <button className="btn btn-primary" onClick={reimburseAll}>✓ Mark all reimbursed</button>
          </div>
        </div>
      )}

      <div className="tab-bar">
        {[['list','All Expenses'],['report','Report']].map(([id, label]) => (
          <button key={id} className={`tab-btn ${tab === id ? 'active' : ''}`} onClick={() => setTab(id)}>{label}</button>
        ))}
      </div>

      {showForm && (
        <div className="card" style={{ marginBottom: 16 }}>
          <div className="card-header"><h3>Submit expense</h3><button className="btn btn-sm" onClick={() => setShowForm(false)}>Cancel</button></div>
          <form onSubmit={submit} style={{ padding: 16 }}>
            <div className="form-grid">
              <div className="form-group"><label>Employee *</label><select value={form.employee_id} onChange={e => setForm(f => ({ ...f, employee_id: e.target.value }))} required><option value="">Select…</option>{employees.map(e => <option key={e.id} value={e.id}>{e.full_name}</option>)}</select></div>
              <div className="form-group"><label>Date *</label><input type="date" value={form.expense_date} onChange={e => setForm(f => ({ ...f, expense_date: e.target.value }))} required /></div>
              <div className="form-group"><label>Category *</label><select value={form.category} onChange={e => setForm(f => ({ ...f, category: e.target.value }))}>{['travel','meals','accommodation','supplies','software','equipment','training','marketing','other'].map(c => <option key={c} value={c}>{c}</option>)}</select></div>
              <div className="form-group"><label>Amount ($) *</label><input type="number" step="0.01" value={form.amount} onChange={e => setForm(f => ({ ...f, amount: e.target.value }))} required /></div>
              <div className="form-group" style={{ gridColumn: '1/-1' }}><label>Description *</label><input type="text" value={form.description} onChange={e => setForm(f => ({ ...f, description: e.target.value }))} required /></div>
              <div className="form-group"><label>Vendor</label><input type="text" value={form.vendor} onChange={e => setForm(f => ({ ...f, vendor: e.target.value }))} /></div>
            </div>
            <button className="btn btn-primary" type="submit">Submit</button>
          </form>
        </div>
      )}

      {tab === 'list' && (
        <div className="card">
          <table className="table">
            <thead><tr><th>Employee</th><th>Date</th><th>Category</th><th>Description</th><th>Amount</th><th>Status</th><th></th></tr></thead>
            <tbody>
              {expenses.length === 0 && <tr><td colSpan={7} className="empty">No expenses</td></tr>}
              {expenses.map(e => (
                <tr key={e.id}>
                  <td style={{ fontWeight: 500 }}>{empMap[e.employee_id] || '—'}</td>
                  <td style={{ fontSize: 12 }}>{e.expense_date}</td>
                  <td><span className="badge badge-info">{e.category}</span></td>
                  <td style={{ fontSize: 12 }}>{e.description}</td>
                  <td style={{ fontWeight: 500 }}>{fmt(e.amount)}</td>
                  <td><span className={`badge badge-${STATUS_COLOR[e.status]}`}>{e.status}</span></td>
                  <td>
                    {e.status === 'pending' && (
                      <div style={{ display: 'flex', gap: 4 }}>
                        <button className="btn btn-sm" style={{ color: 'var(--green)' }} onClick={() => approve(e.id)}>✓</button>
                        <button className="btn btn-sm btn-danger" onClick={() => deny(e.id)}>✗</button>
                      </div>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {tab === 'report' && report && (
        <>
          <div className="metrics-grid" style={{ gridTemplateColumns: 'repeat(2,1fr)', marginBottom: 16 }}>
            <div className="metric-card"><div className="metric-label">Total approved {report.year}</div><div className="metric-value">{fmt(report.grand_total)}</div></div>
            <div className="metric-card"><div className="metric-label">Categories</div><div className="metric-value">{report.by_category.length}</div></div>
          </div>
          <div className="card">
            <table className="table">
              <thead><tr><th>Category</th><th>Count</th><th>Total</th><th>% of spend</th></tr></thead>
              <tbody>
                {report.by_category.map(c => (
                  <tr key={c.category}>
                    <td style={{ fontWeight: 500, textTransform: 'capitalize' }}>{c.category}</td>
                    <td>{c.count}</td>
                    <td style={{ fontWeight: 600 }}>{fmt(c.total)}</td>
                    <td>
                      <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                        <div style={{ flex: 1, height: 6, background: 'var(--bg3)', borderRadius: 99, overflow: 'hidden', minWidth: 80 }}>
                          <div style={{ height: '100%', width: `${c.pct}%`, background: 'var(--blue)', borderRadius: 99 }} />
                        </div>
                        <span style={{ fontSize: 12, minWidth: 35 }}>{c.pct}%</span>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}
    </div>
  );
}
