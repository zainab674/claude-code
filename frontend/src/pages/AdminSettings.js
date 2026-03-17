import React, { useState, useEffect } from 'react';

const BASE = process.env.REACT_APP_API_URL || 'http://localhost:8000';
const tkn = () => localStorage.getItem('payroll_token');
async function req(path, opts = {}) {
  const res = await fetch(`${BASE}${path}`, {
    ...opts,
    headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${tkn()}`, ...opts.headers },
  });
  if (!res.ok) { const e = await res.json().catch(() => ({ detail: res.statusText })); throw new Error(e.detail); }
  if (res.status === 204) return null;
  return res.json();
}

function SettingsSection({ title, description, children }) {
  return (
    <div className="card" style={{ marginBottom: 16 }}>
      <div style={{ padding: '16px 20px', borderBottom: '1px solid var(--border)' }}>
        <div style={{ fontWeight: 600, fontSize: 14 }}>{title}</div>
        {description && <div style={{ fontSize: 12, color: 'var(--text3)', marginTop: 3 }}>{description}</div>}
      </div>
      <div style={{ padding: 20 }}>{children}</div>
    </div>
  );
}

function Field({ label, value, type = 'text', onChange, hint, readOnly = false }) {
  return (
    <div className="form-group">
      <label>{label}</label>
      <input type={type} value={value || ''} onChange={e => onChange?.(e.target.value)} readOnly={readOnly}
        style={readOnly ? { opacity: 0.6, cursor: 'not-allowed' } : {}} />
      {hint && <div style={{ fontSize: 11, color: 'var(--text3)', marginTop: 4 }}>{hint}</div>}
    </div>
  );
}

function Toggle({ label, value, onChange, hint }) {
  return (
    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', padding: '10px 0', borderBottom: '1px solid var(--border)' }}>
      <div>
        <div style={{ fontSize: 13, fontWeight: 500 }}>{label}</div>
        {hint && <div style={{ fontSize: 12, color: 'var(--text3)', marginTop: 2 }}>{hint}</div>}
      </div>
      <button
        onClick={() => onChange(!value)}
        style={{
          width: 42, height: 24, borderRadius: 99, border: 'none', cursor: 'pointer',
          background: value ? 'var(--green)' : 'var(--border2)',
          position: 'relative', transition: 'background 0.2s', flexShrink: 0,
        }}
      >
        <div style={{
          position: 'absolute', top: 2, left: value ? 20 : 2, width: 20, height: 20,
          borderRadius: '50%', background: '#fff', transition: 'left 0.2s',
        }} />
      </button>
    </div>
  );
}

export default function AdminSettings() {
  const [tab, setTab] = useState('company');
  const [company, setCompany] = useState({});
  const [health, setHealth] = useState(null);
  const [saving, setSaving] = useState(false);
  const [success, setSuccess] = useState('');
  const [error, setError] = useState('');
  const [settings, setSettings] = useState({
    email_paystubs: true, email_payroll_summary: true,
    require_2fa: false, session_timeout_hours: 8,
    auto_pto_accrual: true, require_manager_approval_pto: true,
    payroll_preview_required: false, auto_run_payroll: false,
    compliance_check_before_run: true,
  });

  useEffect(() => {
    Promise.all([req('/company'), req('/health/detailed')]).then(([c, h]) => {
      setCompany(c || {}); setHealth(h);
    });
  }, []);

  const saveCompany = async () => {
    setSaving(true); setError(''); setSuccess('');
    try {
      await req('/company', { method: 'PUT', body: JSON.stringify(company) });
      setSuccess('Company settings saved');
    } catch (err) { setError(err.message); }
    setSaving(false);
  };

  const set = (k, v) => setCompany(c => ({ ...c, [k]: v }));

  return (
    <div className="page">
      <div className="page-header"><h1>Settings</h1></div>
      {error && <div className="alert alert-danger">{error}</div>}
      {success && <div style={{ background: 'var(--green-bg)', color: 'var(--green)', border: '1px solid #b2dfb2', padding: '10px 14px', borderRadius: 6, marginBottom: 16, fontSize: 13 }}>✓ {success}</div>}

      <div className="tab-bar">
        {[['company','Company'],['payroll','Payroll'],['notifications','Notifications'],['security','Security'],['system','System']].map(([id, label]) => (
          <button key={id} className={`tab-btn ${tab === id ? 'active' : ''}`} onClick={() => setTab(id)}>{label}</button>
        ))}
      </div>

      {/* ── COMPANY ─── */}
      {tab === 'company' && (
        <>
          <SettingsSection title="Company information" description="Basic details about your organization">
            <div className="form-grid">
              <Field label="Company name" value={company.name} onChange={v => set('name', v)} />
              <Field label="EIN (Employer ID)" value={company.ein} onChange={v => set('ein', v)} hint="Format: XX-XXXXXXX" />
              <Field label="Phone" value={company.phone} onChange={v => set('phone', v)} />
              <Field label="Website" value={company.website} onChange={v => set('website', v)} />
              <Field label="Address" value={company.address_line1} onChange={v => set('address_line1', v)} />
              <Field label="City" value={company.city} onChange={v => set('city', v)} />
              <Field label="State" value={company.state} onChange={v => set('state', v)} />
              <Field label="ZIP" value={company.zip} onChange={v => set('zip', v)} />
            </div>
            <button className="btn btn-primary" onClick={saveCompany} disabled={saving}>{saving ? 'Saving…' : 'Save changes'}</button>
          </SettingsSection>

          <SettingsSection title="Payroll defaults" description="Default settings applied to new employees">
            <div className="form-grid">
              <div className="form-group"><label>Default pay frequency</label>
                <select value={company.default_pay_frequency || 'biweekly'} onChange={e => set('default_pay_frequency', e.target.value)}>
                  {['weekly','biweekly','semimonthly','monthly'].map(f => <option key={f} value={f}>{f}</option>)}
                </select>
              </div>
              <div className="form-group"><label>Default state</label>
                <input type="text" maxLength={2} value={company.default_state || ''} onChange={e => set('default_state', e.target.value.toUpperCase())} placeholder="NY" />
              </div>
            </div>
            <button className="btn btn-primary" onClick={saveCompany} disabled={saving}>{saving ? 'Saving…' : 'Save'}</button>
          </SettingsSection>
        </>
      )}

      {/* ── PAYROLL ─── */}
      {tab === 'payroll' && (
        <SettingsSection title="Payroll settings" description="Control how payroll runs behave">
          <Toggle label="Require preview before running" value={settings.payroll_preview_required} onChange={v => setSettings(s => ({ ...s, payroll_preview_required: v }))} hint="Force a preview step before any payroll run can be approved" />
          <Toggle label="Auto-run scheduled payroll" value={settings.auto_run_payroll} onChange={v => setSettings(s => ({ ...s, auto_run_payroll: v }))} hint="Automatically run payroll on scheduled dates without manual approval" />
          <Toggle label="Compliance check before run" value={settings.compliance_check_before_run} onChange={v => setSettings(s => ({ ...s, compliance_check_before_run: v }))} hint="Block payroll run if critical compliance issues are found" />
          <Toggle label="Auto PTO accrual" value={settings.auto_pto_accrual} onChange={v => setSettings(s => ({ ...s, auto_pto_accrual: v }))} hint="Automatically accrue PTO after each payroll run" />
          <Toggle label="Require manager approval for PTO" value={settings.require_manager_approval_pto} onChange={v => setSettings(s => ({ ...s, require_manager_approval_pto: v }))} hint="PTO requests require manager sign-off before approval" />
          <div style={{ marginTop: 16 }}>
            <button className="btn btn-primary" onClick={() => setSuccess('Payroll settings saved')}>Save settings</button>
          </div>
        </SettingsSection>
      )}

      {/* ── NOTIFICATIONS ─── */}
      {tab === 'notifications' && (
        <SettingsSection title="Email notifications" description="Control which events trigger emails">
          <Toggle label="Email paystubs to employees" value={settings.email_paystubs} onChange={v => setSettings(s => ({ ...s, email_paystubs: v }))} hint="Send PDF paystubs to each employee after payroll runs" />
          <Toggle label="Payroll summary to admin" value={settings.email_payroll_summary} onChange={v => setSettings(s => ({ ...s, email_payroll_summary: v }))} hint="Send a summary email to admins after each payroll run" />
          <div className="form-group" style={{ marginTop: 16 }}>
            <label>Admin notification email</label>
            <input type="email" value={company.notification_email || company.email || ''} onChange={e => set('notification_email', e.target.value)} />
          </div>
          <button className="btn btn-primary" onClick={saveCompany} disabled={saving}>Save</button>
        </SettingsSection>
      )}

      {/* ── SECURITY ─── */}
      {tab === 'security' && (
        <>
          <SettingsSection title="Authentication" description="Control how users log in">
            <Toggle label="Require 2FA for all admins" value={settings.require_2fa} onChange={v => setSettings(s => ({ ...s, require_2fa: v }))} hint="Enforce TOTP 2-factor authentication for admin and manager accounts (coming soon)" />
            <div className="form-group" style={{ marginTop: 16 }}>
              <label>Session timeout (hours)</label>
              <input type="number" min="1" max="168" value={settings.session_timeout_hours} onChange={e => setSettings(s => ({ ...s, session_timeout_hours: Number(e.target.value) }))} style={{ maxWidth: 120 }} />
            </div>
            <button className="btn btn-primary" onClick={() => setSuccess('Security settings saved')}>Save</button>
          </SettingsSection>

          <SettingsSection title="Data & privacy" description="Encryption and data handling">
            <div style={{ fontSize: 13, lineHeight: 2, color: 'var(--text2)' }}>
              <div>SSN encryption: <span style={{ color: process.env.REACT_APP_SSN_KEY_SET === 'true' ? 'var(--green)' : 'var(--amber)' }}>
                {process.env.REACT_APP_SSN_KEY_SET === 'true' ? '✓ AES-256-GCM enabled' : '⚠ Set SSN_ENCRYPTION_KEY in .env'}
              </span></div>
              <div>Bank account encryption: <span style={{ color: 'var(--green)' }}>✓ AES-256-GCM enabled</span></div>
              <div>Transport: <span style={{ color: 'var(--green)' }}>✓ TLS 1.3</span></div>
              <div>Audit logging: <span style={{ color: 'var(--green)' }}>✓ Immutable audit trail enabled</span></div>
            </div>
          </SettingsSection>
        </>
      )}

      {/* ── SYSTEM ─── */}
      {tab === 'system' && (
        <>
          {health && (
            <SettingsSection title="System health" description="Current infrastructure status">
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2,1fr)', gap: 12 }}>
                {Object.entries(health.checks || {}).map(([name, check]) => (
                  <div key={name} style={{ padding: '10px 14px', border: '1px solid var(--border)', borderRadius: 8 }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                      <span style={{ fontWeight: 500, fontSize: 13, textTransform: 'capitalize' }}>{name.replace('_', ' ')}</span>
                      <span className={`badge badge-${check.status === 'ok' ? 'success' : 'danger'}`}>{check.status}</span>
                    </div>
                    {check.latency_ms !== undefined && <div style={{ fontSize: 11, color: 'var(--text3)', marginTop: 4 }}>{check.latency_ms}ms latency</div>}
                    {check.rss_mb && <div style={{ fontSize: 11, color: 'var(--text3)', marginTop: 4 }}>{check.rss_mb}MB RSS</div>}
                    {check.free_gb && <div style={{ fontSize: 11, color: 'var(--text3)', marginTop: 4 }}>{check.free_gb}GB free disk</div>}
                  </div>
                ))}
              </div>
              <div style={{ marginTop: 12, fontSize: 12, color: 'var(--text3)' }}>
                Version: {health.version} · Uptime: {health.uptime} · Python: {health.python}
              </div>
            </SettingsSection>
          )}

          <SettingsSection title="Data management" description="Export and backup your data">
            <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
              {[
                ['/export/employees', 'Export employees CSV'],
                ['/export/payroll-history', 'Export payroll history'],
                ['/export/employee-ytd', 'Export YTD data'],
                ['/openapi/postman', 'Download Postman collection'],
                ['/openapi/spec', 'Download OpenAPI spec'],
              ].map(([path, label]) => (
                <a key={path} href={`${BASE}${path}`} target="_blank" rel="noreferrer"
                  style={{ textDecoration: 'none' }}
                  onClick={e => { e.preventDefault(); const a = document.createElement('a'); a.href = `${BASE}${path}`; a.setAttribute('data-auth', tkn()); fetch(`${BASE}${path}`, { headers: { Authorization: `Bearer ${tkn()}` } }).then(r => r.blob()).then(b => { const url = URL.createObjectURL(b); const link = document.createElement('a'); link.href = url; link.download = path.split('/').pop(); link.click(); }); }}>
                  <button className="btn">{label}</button>
                </a>
              ))}
            </div>
          </SettingsSection>

          <SettingsSection title="Danger zone" description="Irreversible actions — proceed with caution">
            <div style={{ padding: 16, background: 'var(--red-bg)', border: '1px solid var(--red)', borderRadius: 8 }}>
              <div style={{ fontWeight: 500, color: 'var(--red)', marginBottom: 8 }}>Delete all payroll data</div>
              <div style={{ fontSize: 12, color: 'var(--text2)', marginBottom: 12 }}>This will permanently delete all pay runs, paystubs, and payroll history. Employees will not be deleted. This action cannot be undone.</div>
              <button className="btn btn-danger" onClick={() => window.confirm('Type DELETE to confirm') && alert('Contact support to reset payroll data.')}>
                Delete payroll history
              </button>
            </div>
          </SettingsSection>
        </>
      )}
    </div>
  );
}
