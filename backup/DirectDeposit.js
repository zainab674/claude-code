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

export default function DirectDeposit() {
  const [summary, setSummary] = useState(null);
  const [employees, setEmployees] = useState([]);
  const [selected, setSelected] = useState('');
  const [bankInfo, setBankInfo] = useState(null);
  const [form, setForm] = useState({ routing_number: '', account_number: '', account_type: 'checking', bank_name: '' });
  const [showForm, setShowForm] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [success, setSuccess] = useState('');

  useEffect(() => {
    Promise.all([req('/direct-deposit/summary'), req('/employees?status=active')]).then(([s, e]) => {
      setSummary(s); setEmployees(e?.employees || []);
    });
  }, []);

  const loadBank = async (id) => {
    if (!id) { setBankInfo(null); return; }
    try { setBankInfo(await req(`/direct-deposit/employees/${id}`)); }
    catch { setBankInfo(null); }
  };

  const save = async (e) => {
    e.preventDefault(); setError(''); setSuccess('');
    setLoading(true);
    try {
      await req(`/direct-deposit/employees/${selected}`, { method: 'POST', body: JSON.stringify(form) });
      setSuccess('Bank account saved'); setShowForm(false);
      setForm({ routing_number: '', account_number: '', account_type: 'checking', bank_name: '' });
      loadBank(selected);
    } catch (err) { setError(err.message); }
    setLoading(false);
  };

  const verify = async () => {
    try { await req(`/direct-deposit/employees/${selected}/verify`, { method: 'PUT' }); loadBank(selected); setSuccess('Verified'); }
    catch (err) { setError(err.message); }
  };

  const remove = async () => {
    if (!window.confirm('Remove bank account?')) return;
    try { await req(`/direct-deposit/employees/${selected}`, { method: 'DELETE' }); setBankInfo(null); setSuccess('Removed'); }
    catch (err) { setError(err.message); }
  };

  const enrollPct = summary ? Math.round((summary.enrolled / Math.max(summary.total_employees, 1)) * 100) : 0;

  return (
    <div className="page">
      <div className="page-header"><h1>Direct Deposit</h1></div>
      {error && <div className="alert alert-danger">{error}</div>}
      {success && <div className="alert" style={{ background: 'var(--green-bg)', color: 'var(--green)', border: '1px solid #b2dfb2', padding: '10px 14px', borderRadius: 6, marginBottom: 12, fontSize: 13 }}>✓ {success}</div>}

      {/* Summary */}
      {summary && (
        <div className="metrics-grid" style={{ gridTemplateColumns: 'repeat(4,1fr)', marginBottom: 16 }}>
          {[
            ['Total employees', summary.total_employees],
            ['Enrolled', summary.enrolled],
            ['Verified', summary.verified],
            ['Not enrolled', summary.not_enrolled],
          ].map(([label, val]) => (
            <div key={label} className="metric-card">
              <div className="metric-label">{label}</div>
              <div className="metric-value">{val}</div>
            </div>
          ))}
        </div>
      )}
      {summary && (
        <div className="card" style={{ marginBottom: 16 }}>
          <div style={{ padding: 16 }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 12, marginBottom: 6 }}>
              <span style={{ color: 'var(--text2)' }}>Enrollment rate</span>
              <span style={{ fontWeight: 500 }}>{enrollPct}%</span>
            </div>
            <div style={{ height: 8, background: 'var(--bg3)', borderRadius: 99, overflow: 'hidden' }}>
              <div style={{ height: '100%', width: `${enrollPct}%`, background: enrollPct === 100 ? 'var(--green)' : 'var(--blue)', borderRadius: 99, transition: 'width 0.4s' }} />
            </div>
          </div>
        </div>
      )}

      <div className="two-col">
        {/* Employee selector + form */}
        <div className="card">
          <div className="card-header"><h3>Manage bank account</h3></div>
          <div style={{ padding: 16 }}>
            <div className="form-group">
              <label>Employee</label>
              <select value={selected} onChange={e => { setSelected(e.target.value); loadBank(e.target.value); setBankInfo(null); setShowForm(false); }}>
                <option value="">Select employee…</option>
                {employees.map(e => <option key={e.id} value={e.id}>{e.full_name}</option>)}
              </select>
            </div>

            {selected && bankInfo && !bankInfo.has_direct_deposit && (
              <div style={{ marginTop: 12 }}>
                <p style={{ fontSize: 13, color: 'var(--text3)', marginBottom: 12 }}>No bank account on file</p>
                <button className="btn btn-primary" onClick={() => setShowForm(true)}>+ Add bank account</button>
              </div>
            )}

            {selected && bankInfo?.has_direct_deposit && !showForm && (
              <div style={{ marginTop: 12 }}>
                <div className="preview-box" style={{ marginBottom: 12 }}>
                  {[
                    ['Bank', bankInfo.bank_name || '—'],
                    ['Account type', bankInfo.account_type],
                    ['Account number', bankInfo.account_display],
                    ['Routing number', bankInfo.routing_display],
                    ['Status', bankInfo.is_verified ? '✓ Verified' : '⚠ Pending verification'],
                  ].map(([l, v]) => (
                    <div key={l} className="preview-row">
                      <span style={{ color: 'var(--text2)' }}>{l}</span>
                      <span style={{ color: v.startsWith('✓') ? 'var(--green)' : v.startsWith('⚠') ? 'var(--amber)' : 'inherit' }}>{v}</span>
                    </div>
                  ))}
                </div>
                <div style={{ display: 'flex', gap: 8 }}>
                  {!bankInfo.is_verified && <button className="btn" onClick={verify}>✓ Mark verified</button>}
                  <button className="btn" onClick={() => setShowForm(true)}>Update account</button>
                  <button className="btn btn-danger" onClick={remove}>Remove</button>
                </div>
              </div>
            )}

            {showForm && (
              <form onSubmit={save} style={{ marginTop: 16 }}>
                <div className="form-group"><label>Bank name</label><input type="text" value={form.bank_name} onChange={e => setForm(f => ({ ...f, bank_name: e.target.value }))} placeholder="Chase, Wells Fargo, etc." /></div>
                <div className="form-group">
                  <label>Account type</label>
                  <select value={form.account_type} onChange={e => setForm(f => ({ ...f, account_type: e.target.value }))}>
                    <option value="checking">Checking</option>
                    <option value="savings">Savings</option>
                  </select>
                </div>
                <div className="form-group"><label>Routing number (9 digits) *</label><input type="text" value={form.routing_number} onChange={e => setForm(f => ({ ...f, routing_number: e.target.value }))} placeholder="021000021" maxLength={9} required /></div>
                <div className="form-group"><label>Account number *</label><input type="text" value={form.account_number} onChange={e => setForm(f => ({ ...f, account_number: e.target.value }))} placeholder="4-17 digits" required /></div>
                <div style={{ display: 'flex', gap: 8, marginTop: 8 }}>
                  <button className="btn btn-primary" type="submit" disabled={loading}>{loading ? 'Saving…' : 'Save bank account'}</button>
                  <button className="btn" type="button" onClick={() => setShowForm(false)}>Cancel</button>
                </div>
              </form>
            )}
          </div>
        </div>

        {/* Instructions */}
        <div className="card">
          <div className="card-header"><h3>About direct deposit</h3></div>
          <div style={{ padding: 16, fontSize: 13, color: 'var(--text2)', lineHeight: 1.8 }}>
            <div style={{ fontWeight: 500, marginBottom: 8 }}>How it works:</div>
            <div>1. Collect employee bank account info here</div>
            <div>2. Verify routing number via ABA checksum</div>
            <div>3. Send micro-deposits for verification (2–3 business days)</div>
            <div>4. Employee confirms micro-deposit amounts</div>
            <div>5. Account marked verified — ready for ACH payroll</div>
            <div style={{ marginTop: 16, padding: 12, background: 'var(--amber-bg)', borderRadius: 6, fontSize: 12, color: 'var(--amber)' }}>
              ⚠ Actual ACH transfers require a banking partner (Dwolla, Stripe Payouts, or payroll processor). This system securely stores account info for when you integrate one.
            </div>
            <div style={{ marginTop: 12, fontSize: 12, color: 'var(--text3)' }}>
              Bank routing and account numbers are encrypted at rest using AES-256-GCM. Set SSN_ENCRYPTION_KEY in .env to enable encryption.
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
