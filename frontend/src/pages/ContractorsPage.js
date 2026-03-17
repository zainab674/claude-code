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
const fmt = n => `$${Number(n || 0).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
const year = new Date().getFullYear();

export default function Contractors() {
  const [tab, setTab] = useState('contractors');
  const [contractors, setContractors] = useState([]);
  const [report, setReport] = useState(null);
  const [selected, setSelected] = useState(null);
  const [payments, setPayments] = useState(null);
  const [showContractorForm, setShowContractorForm] = useState(false);
  const [showPaymentForm, setShowPaymentForm] = useState(false);
  const [cForm, setCForm] = useState({ first_name: '', last_name: '', business_name: '', email: '', contractor_type: 'individual', ein_or_ssn_last4: '', address_line1: '', city: '', state: '', zip: '' });
  const [pForm, setPForm] = useState({ payment_date: new Date().toISOString().split('T')[0], amount: '', description: '', payment_method: 'check' });
  const [error, setError] = useState('');

  const load = async () => {
    const [c, r] = await Promise.all([req('/contractors'), req(`/1099/report?year=${year}`)]);
    setContractors(c || []);
    setReport(r);
  };

  useEffect(() => { load(); }, []);

  const loadPayments = async (id) => {
    setSelected(id);
    setPayments(await req(`/contractors/${id}/payments?year=${year}`));
  };

  const saveContractor = async (e) => {
    e.preventDefault(); setError('');
    try { await req('/contractors', { method: 'POST', body: JSON.stringify(cForm) }); setShowContractorForm(false); load(); }
    catch (err) { setError(err.message); }
  };

  const savePayment = async (e) => {
    e.preventDefault(); setError('');
    try {
      await req(`/contractors/${selected}/payments`, { method: 'POST', body: JSON.stringify({ ...pForm, amount: Number(pForm.amount) }) });
      setShowPaymentForm(false);
      setPForm({ payment_date: new Date().toISOString().split('T')[0], amount: '', description: '', payment_method: 'check' });
      loadPayments(selected);
    } catch (err) { setError(err.message); }
  };

  const downloadXml = async () => {
    const res = await fetch(`${BASE}/1099/xml?year=${year}`, { headers: { Authorization: `Bearer ${tkn()}` } });
    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a'); a.href = url; a.download = `1099-nec-${year}.xml`; a.click();
  };

  const selectedContractor = contractors.find(c => c.id === selected);

  return (
    <div className="page">
      <div className="page-header">
        <h1>Contractors & 1099</h1>
        <div style={{ display: 'flex', gap: 8 }}>
          <button className="btn" onClick={downloadXml}>↓ 1099 XML {year}</button>
          <button className="btn btn-primary" onClick={() => setShowContractorForm(!showContractorForm)}>+ Add contractor</button>
        </div>
      </div>
      {error && <div className="alert alert-danger">{error}</div>}

      {/* 1099 summary */}
      {report && (
        <div className="metrics-grid" style={{ gridTemplateColumns: 'repeat(3,1fr)', marginBottom: 16 }}>
          <div className="metric-card"><div className="metric-label">Require 1099-NEC</div><div className="metric-value">{report.total_contractors_requiring_1099}</div><div className="metric-delta">Paid ≥ ${report.threshold}</div></div>
          <div className="metric-card"><div className="metric-label">Total 1099 payments</div><div className="metric-value">{fmt(report.total_payments)}</div><div className="metric-delta">{year} YTD</div></div>
          <div className="metric-card"><div className="metric-label">Total contractors</div><div className="metric-value">{contractors.length}</div><div className="metric-delta">Active</div></div>
        </div>
      )}

      <div className="tab-bar">
        {[['contractors','Contractors'],['1099','1099 Report']].map(([id, label]) => (
          <button key={id} className={`tab-btn ${tab === id ? 'active' : ''}`} onClick={() => setTab(id)}>{label}</button>
        ))}
      </div>

      {/* Add contractor form */}
      {showContractorForm && (
        <div className="card" style={{ marginBottom: 16 }}>
          <div className="card-header"><h3>New contractor</h3><button className="btn btn-sm" onClick={() => setShowContractorForm(false)}>Cancel</button></div>
          <form onSubmit={saveContractor} style={{ padding: 16 }}>
            <div className="form-grid">
              <div className="form-group"><label>Type</label><select value={cForm.contractor_type} onChange={e => setCForm(f => ({ ...f, contractor_type: e.target.value }))}><option value="individual">Individual</option><option value="business">Business</option></select></div>
              <div className="form-group"><label>Business name</label><input type="text" value={cForm.business_name} onChange={e => setCForm(f => ({ ...f, business_name: e.target.value }))} /></div>
              <div className="form-group"><label>First name *</label><input type="text" value={cForm.first_name} onChange={e => setCForm(f => ({ ...f, first_name: e.target.value }))} required /></div>
              <div className="form-group"><label>Last name *</label><input type="text" value={cForm.last_name} onChange={e => setCForm(f => ({ ...f, last_name: e.target.value }))} required /></div>
              <div className="form-group"><label>Email</label><input type="email" value={cForm.email} onChange={e => setCForm(f => ({ ...f, email: e.target.value }))} /></div>
              <div className="form-group"><label>TIN last 4 digits</label><input type="text" maxLength={4} value={cForm.ein_or_ssn_last4} onChange={e => setCForm(f => ({ ...f, ein_or_ssn_last4: e.target.value }))} placeholder="1234" /></div>
              <div className="form-group"><label>Address</label><input type="text" value={cForm.address_line1} onChange={e => setCForm(f => ({ ...f, address_line1: e.target.value }))} /></div>
              <div className="form-group"><label>City</label><input type="text" value={cForm.city} onChange={e => setCForm(f => ({ ...f, city: e.target.value }))} /></div>
              <div className="form-group"><label>State</label><input type="text" maxLength={2} value={cForm.state} onChange={e => setCForm(f => ({ ...f, state: e.target.value.toUpperCase() }))} /></div>
              <div className="form-group"><label>ZIP</label><input type="text" value={cForm.zip} onChange={e => setCForm(f => ({ ...f, zip: e.target.value }))} /></div>
            </div>
            <button className="btn btn-primary" type="submit">Save contractor</button>
          </form>
        </div>
      )}

      {tab === 'contractors' && (
        <div className="two-col">
          <div className="card">
            <table className="table">
              <thead><tr><th>Name</th><th>Type</th><th>Email</th><th></th></tr></thead>
              <tbody>
                {contractors.length === 0 && <tr><td colSpan={4} className="empty">No contractors yet</td></tr>}
                {contractors.map(c => (
                  <tr key={c.id} onClick={() => loadPayments(c.id)} style={{ cursor: 'pointer', background: selected === c.id ? 'var(--blue-bg)' : '' }}>
                    <td style={{ fontWeight: 500 }}>{c.name}</td>
                    <td><span className="badge badge-info">{c.contractor_type}</span></td>
                    <td style={{ fontSize: 12, color: 'var(--text3)' }}>{c.email || '—'}</td>
                    <td style={{ color: 'var(--text3)', fontSize: 11 }}>›</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div>
            {!selected && <div className="card" style={{ padding: 32, textAlign: 'center', color: 'var(--text3)' }}>← Select a contractor</div>}
            {selected && payments && (
              <div className="card">
                <div className="card-header">
                  <div>
                    <h3>{selectedContractor?.name}</h3>
                    <div style={{ fontSize: 12, color: 'var(--text3)' }}>
                      {year} payments: {fmt(payments.total_paid)}
                      {payments.requires_1099 && <span className="badge badge-warning" style={{ marginLeft: 8 }}>1099 required</span>}
                    </div>
                  </div>
                  <button className="btn btn-sm btn-primary" onClick={() => setShowPaymentForm(!showPaymentForm)}>+ Payment</button>
                </div>
                {showPaymentForm && (
                  <form onSubmit={savePayment} style={{ padding: 16, borderBottom: '1px solid var(--border)' }}>
                    <div className="form-grid">
                      <div className="form-group"><label>Date *</label><input type="date" value={pForm.payment_date} onChange={e => setPForm(f => ({ ...f, payment_date: e.target.value }))} required /></div>
                      <div className="form-group"><label>Amount ($) *</label><input type="number" step="0.01" value={pForm.amount} onChange={e => setPForm(f => ({ ...f, amount: e.target.value }))} required /></div>
                      <div className="form-group"><label>Method</label><select value={pForm.payment_method} onChange={e => setPForm(f => ({ ...f, payment_method: e.target.value }))}>{['check','ach','wire','paypal','other'].map(m => <option key={m} value={m}>{m}</option>)}</select></div>
                      <div className="form-group"><label>Description</label><input type="text" value={pForm.description} onChange={e => setPForm(f => ({ ...f, description: e.target.value }))} /></div>
                    </div>
                    <button className="btn btn-primary btn-sm" type="submit">Record payment</button>
                  </form>
                )}
                <table className="table">
                  <thead><tr><th>Date</th><th>Amount</th><th>Method</th><th>Description</th></tr></thead>
                  <tbody>
                    {payments.payments.length === 0 && <tr><td colSpan={4} className="empty">No payments yet</td></tr>}
                    {payments.payments.map(p => (
                      <tr key={p.id}>
                        <td style={{ fontSize: 12 }}>{p.date}</td>
                        <td style={{ fontWeight: 500 }}>{fmt(p.amount)}</td>
                        <td><span className="badge badge-info">{p.method}</span></td>
                        <td style={{ fontSize: 12, color: 'var(--text3)' }}>{p.description || '—'}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        </div>
      )}

      {tab === '1099' && report && (
        <div className="card">
          <div className="card-header">
            <h3>1099-NEC Report — {year}</h3>
            <button className="btn" onClick={downloadXml}>↓ Download XML</button>
          </div>
          <table className="table">
            <thead><tr><th>Contractor</th><th>Address</th><th>TIN last 4</th><th>Total paid</th><th>1099-NEC</th></tr></thead>
            <tbody>
              {report.contractors.length === 0 && <tr><td colSpan={5} className="empty">No contractors reached the $600 threshold</td></tr>}
              {report.contractors.map(c => (
                <tr key={c.contractor_id}>
                  <td style={{ fontWeight: 500 }}>{c.name}</td>
                  <td style={{ fontSize: 12, color: 'var(--text3)' }}>{c.address}</td>
                  <td style={{ fontFamily: 'monospace', fontSize: 12 }}>***{c.tin_last4}</td>
                  <td style={{ fontWeight: 600 }}>{fmt(c.total_paid)}</td>
                  <td><span className="badge badge-warning">Required</span></td>
                </tr>
              ))}
            </tbody>
          </table>
          <div style={{ padding: '12px 16px', fontSize: 12, color: 'var(--amber)', background: 'var(--amber-bg)' }}>
            ⚠ 1099-NEC forms due to contractors by January 31. File with IRS via FIRE system or licensed tax preparer.
          </div>
        </div>
      )}
    </div>
  );
}
