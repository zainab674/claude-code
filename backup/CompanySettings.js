import React, { useState, useEffect } from 'react';
import * as api from '../services/api';

const STATES = ['AL','AK','AZ','AR','CA','CO','CT','DE','FL','GA','HI','ID','IL','IN','IA',
'KS','KY','LA','ME','MD','MA','MI','MN','MS','MO','MT','NE','NV','NH','NJ','NM','NY','NC',
'ND','OH','OK','OR','PA','RI','SC','SD','TN','TX','UT','VT','VA','WA','WV','WI','WY'];

export default function CompanySettings() {
  const [form, setForm] = useState(null);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState('');

  useEffect(() => {
    api.getCompany().then(c => setForm(c || {})).catch(e => setError(e.message));
  }, []);

  const set = (k, v) => setForm(f => ({ ...f, [k]: v }));

  const save = async (e) => {
    e.preventDefault();
    setSaving(true); setError(''); setSaved(false);
    try {
      const updated = await api.updateCompany(form);
      setForm(updated || form);
      setSaved(true);
      setTimeout(() => setSaved(false), 3000);
    } catch (err) { setError(err.message); }
    setSaving(false);
  };

  if (!form) return <div className="page"><div style={{ padding: 48, textAlign: 'center', color: 'var(--text3)' }}>Loading…</div></div>;

  const F = ({ label, k, type = 'text', placeholder = '' }) => (
    <div className="form-group">
      <label>{label}</label>
      <input type={type} value={form[k] || ''} onChange={e => set(k, e.target.value)} placeholder={placeholder} />
    </div>
  );

  return (
    <div className="page">
      <div className="page-header"><h1>Company Settings</h1></div>
      {error && <div className="alert alert-danger">{error}</div>}
      {saved && (
        <div style={{ background: 'var(--green-bg)', color: 'var(--green)', border: '1px solid #b2dfb2', padding: '10px 14px', borderRadius: 6, marginBottom: 16, fontSize: 13 }}>
          ✓ Company settings saved
        </div>
      )}

      <form onSubmit={save}>
        <div className="card" style={{ marginBottom: 16 }}>
          <div className="card-header"><h3>Company information</h3></div>
          <div style={{ padding: 16 }}>
            <div className="form-grid">
              <F label="Company name *" k="name" />
              <F label="EIN (XX-XXXXXXX)" k="ein" placeholder="12-3456789" />
              <F label="Phone" k="phone" type="tel" />
              <F label="Email" k="email" type="email" />
              <F label="Website" k="website" placeholder="https://yourcompany.com" />
            </div>
          </div>
        </div>

        <div className="card" style={{ marginBottom: 16 }}>
          <div className="card-header"><h3>Mailing address</h3></div>
          <div style={{ padding: 16 }}>
            <div className="form-grid">
              <div className="form-group" style={{ gridColumn: '1/-1' }}>
                <label>Street address</label>
                <input type="text" value={form.address_line1 || ''} onChange={e => set('address_line1', e.target.value)} />
              </div>
              <div className="form-group" style={{ gridColumn: '1/-1' }}>
                <label>Address line 2</label>
                <input type="text" value={form.address_line2 || ''} onChange={e => set('address_line2', e.target.value)} />
              </div>
              <F label="City" k="city" />
              <div className="form-group">
                <label>State</label>
                <select value={form.state || ''} onChange={e => set('state', e.target.value)}>
                  <option value="">Select…</option>
                  {STATES.map(s => <option key={s} value={s}>{s}</option>)}
                </select>
              </div>
              <F label="ZIP code" k="zip" placeholder="10001" />
            </div>
          </div>
        </div>

        <div className="card" style={{ marginBottom: 16 }}>
          <div className="card-header"><h3>Payroll defaults</h3></div>
          <div style={{ padding: 16 }}>
            <div className="form-grid">
              <div className="form-group">
                <label>Default pay frequency</label>
                <select value={form.default_pay_frequency || 'biweekly'} onChange={e => set('default_pay_frequency', e.target.value)}>
                  {['weekly','biweekly','semimonthly','monthly'].map(f => (
                    <option key={f} value={f}>{f.charAt(0).toUpperCase() + f.slice(1)}</option>
                  ))}
                </select>
              </div>
              <div className="form-group">
                <label>Default state for new employees</label>
                <select value={form.default_state || ''} onChange={e => set('default_state', e.target.value)}>
                  <option value="">Select…</option>
                  {STATES.map(s => <option key={s} value={s}>{s}</option>)}
                </select>
              </div>
              <div className="form-group">
                <label>Notification email</label>
                <input type="email" value={form.notification_email || ''} onChange={e => set('notification_email', e.target.value)}
                  placeholder="Receives payroll summaries" />
              </div>
            </div>
          </div>
        </div>

        <div style={{ display: 'flex', gap: 12 }}>
          <button className="btn btn-primary" type="submit" disabled={saving}>
            {saving ? 'Saving…' : 'Save company settings'}
          </button>
        </div>
      </form>
    </div>
  );
}
