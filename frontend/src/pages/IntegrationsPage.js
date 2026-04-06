import React, { useState, useEffect, useCallback } from 'react';
import * as api from '../services/api';

const fmtDate = (d) =>
  d ? new Date(d).toLocaleString('en-US', { month: 'short', day: 'numeric', year: 'numeric', hour: '2-digit', minute: '2-digit' }) : '—';

// ── QuickBooks brand colour ──────────────────────────────────────
const QB_GREEN = '#2CA01C';
const QB_DARK = '#393A3D';

// ── QB Logo SVG ─────────────────────────────────────────────────
function QBLogo({ size = 36 }) {
  return (
    <svg width={size} height={size} viewBox="0 0 36 36" fill="none">
      <rect width="36" height="36" rx="8" fill={QB_GREEN} />
      <text x="18" y="26" textAnchor="middle" fill="#fff"
        style={{ fontSize: 22, fontWeight: 700, fontFamily: 'serif' }}>Q</text>
    </svg>
  );
}

// ── Badge ────────────────────────────────────────────────────────
function StatusBadge({ connected, tokenValid }) {
  if (!connected) return (
    <span style={{
      fontSize: 12, padding: '3px 10px', borderRadius: 20,
      background: 'rgba(255,255,255,0.08)', color: 'rgba(255,255,255,0.5)'
    }}>
      Not connected
    </span>
  );
  return (
    <span style={{
      fontSize: 12, padding: '3px 10px', borderRadius: 20,
      background: tokenValid ? 'rgba(44,160,28,0.15)' : 'rgba(255,160,0,0.15)',
      color: tokenValid ? QB_GREEN : '#ffa500',
      border: `1px solid ${tokenValid ? 'rgba(44,160,28,0.3)' : 'rgba(255,160,0,0.3)'}`
    }}>
      {tokenValid ? '● Connected' : '⚠ Token expired'}
    </span>
  );
}

// ── Result block ────────────────────────────────────────────────
function ResultBlock({ result, onClose }) {
  if (!result) return null;
  const isError = result.type === 'error';
  return (
    <div style={{
      margin: '16px 0', padding: 16, borderRadius: 10,
      background: isError ? 'rgba(220,50,50,0.08)' : 'rgba(44,160,28,0.08)',
      border: `1px solid ${isError ? 'rgba(220,50,50,0.25)' : 'rgba(44,160,28,0.25)'}`,
      fontSize: 14, color: isError ? '#f87171' : '#4ade80', position: 'relative',
    }}>
      <button onClick={onClose} style={{
        position: 'absolute', top: 8, right: 12, background: 'none',
        border: 'none', color: 'inherit', cursor: 'pointer', fontSize: 16,
      }}>✕</button>
      <div style={{ fontWeight: 600, marginBottom: result.details ? 8 : 0 }}>
        {isError ? '✗ ' : '✓ '}{result.message}
      </div>
      {result.details && (
        <div style={{ fontSize: 13, color: 'rgba(255,255,255,0.6)', marginTop: 4 }}>
          {result.details}
        </div>
      )}
      {result.items && result.items.length > 0 && (
        <div style={{ marginTop: 10, maxHeight: 180, overflowY: 'auto' }}>
          <table style={{ width: '100%', fontSize: 12, borderCollapse: 'collapse' }}>
            <tbody>
              {result.items.map((item, i) => (
                <tr key={i} style={{ borderTop: '1px solid rgba(255,255,255,0.07)' }}>
                  <td style={{ padding: '4px 8px 4px 0', color: 'rgba(255,255,255,0.7)' }}>
                    {item.name || item.qb_id || item.id}
                  </td>
                  <td style={{ padding: '4px 0', color: 'rgba(255,255,255,0.4)', fontSize: 11 }}>
                    {item.qb_id ? `QB ID: ${item.qb_id}` : ''}
                    {item.error ? <span style={{ color: '#f87171' }}> {item.error}</span> : ''}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

// ── QB Data Preview Table ────────────────────────────────────────
function QBDataTable({ title, data, columns, onClose }) {
  if (!data) return null;
  return (
    <div style={{
      margin: '16px 0', padding: 16, borderRadius: 10,
      background: 'rgba(255,255,255,0.04)', border: '1px solid rgba(255,255,255,0.1)',
    }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 }}>
        <div style={{ fontSize: 14, fontWeight: 600 }}>{title} <span style={{ color: 'rgba(255,255,255,0.4)', fontWeight: 400 }}>({data.length})</span></div>
        <button onClick={onClose} style={{ background: 'none', border: 'none', color: 'rgba(255,255,255,0.5)', cursor: 'pointer', fontSize: 16 }}>✕</button>
      </div>
      {data.length === 0 ? (
        <div style={{ color: 'rgba(255,255,255,0.4)', fontSize: 13 }}>No records found.</div>
      ) : (
        <div style={{ overflowX: 'auto', maxHeight: 320, overflowY: 'auto' }}>
          <table style={{ width: '100%', fontSize: 12, borderCollapse: 'collapse' }}>
            <thead>
              <tr>
                {columns.map(c => (
                  <th key={c.key} style={{ padding: '6px 10px', textAlign: 'left', color: 'rgba(255,255,255,0.4)', fontWeight: 500, borderBottom: '1px solid rgba(255,255,255,0.1)', whiteSpace: 'nowrap' }}>
                    {c.label}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {data.map((row, i) => (
                <tr key={i} style={{ borderBottom: '1px solid rgba(255,255,255,0.05)' }}>
                  {columns.map(c => (
                    <td key={c.key} style={{ padding: '6px 10px', color: 'rgba(255,255,255,0.8)' }}>
                      {c.render ? c.render(row) : (row[c.key] ?? '—')}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

// ── Sync Payroll Modal ───────────────────────────────────────────
function SyncPayrollModal({ onClose, onSync }) {
  const [runs, setRuns] = useState([]);
  const [selectedId, setSelectedId] = useState('');
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    api.getPayrollHistory({ limit: 20 }).then(r => setRuns(r.runs || []));
  }, []);

  const handleSync = async () => {
    if (!selectedId) return;
    setLoading(true);
    try {
      const res = await api.syncPayrollToQB(selectedId);
      onSync({ type: 'success', message: `Journal entry created in QuickBooks (ID: ${res.journal_entry_id})`, details: `${res.lines} line items | Period: ${res.period}` });
      onClose();
    } catch (e) {
      onSync({ type: 'error', message: e.message });
      onClose();
    } finally {
      setLoading(false);
    }
  };

  return (
    <div style={{
      position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.7)', zIndex: 1000,
      display: 'flex', alignItems: 'center', justifyContent: 'center',
    }}>
      <div style={{
        background: 'var(--card)', borderRadius: 16, padding: 28, width: 480,
        border: '1px solid rgba(255,255,255,0.1)', boxShadow: '0 24px 64px rgba(0,0,0,0.6)',
      }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 20 }}>
          <h3 style={{ margin: 0, fontSize: 18 }}>Push Payroll to QuickBooks</h3>
          <button onClick={onClose} style={{ background: 'none', border: 'none', color: 'rgba(255,255,255,0.5)', cursor: 'pointer', fontSize: 20 }}>✕</button>
        </div>
        <p style={{ fontSize: 13, color: 'rgba(255,255,255,0.5)', marginBottom: 16, lineHeight: 1.5 }}>
          Select a completed pay run to create a double-entry journal entry in QuickBooks Online.
          This records payroll expense, tax liabilities, and net payroll clearing.
        </p>
        <div style={{ marginBottom: 16 }}>
          <label style={{ fontSize: 13, color: 'rgba(255,255,255,0.6)', display: 'block', marginBottom: 6 }}>Pay Run</label>
          <select
            value={selectedId}
            onChange={e => setSelectedId(e.target.value)}
            style={{ width: '100%', padding: '10px 12px', borderRadius: 8, background: 'rgba(255,255,255,0.06)', border: '1px solid rgba(255,255,255,0.15)', color: '#fff', fontSize: 14 }}
          >
            <option value="">Select a pay run...</option>
            {runs.filter(r => r.status === 'completed').map(r => (
              <option key={r.id} value={r.id}>
                {new Date(r.created_at).toLocaleDateString()} — {r.employee_count} employees — ${Number(r.total_gross || 0).toLocaleString()}
              </option>
            ))}
          </select>
        </div>
        <div style={{ display: 'flex', gap: 10, justifyContent: 'flex-end' }}>
          <button className="btn" onClick={onClose}>Cancel</button>
          <button
            className="btn btn-primary"
            onClick={handleSync}
            disabled={!selectedId || loading}
            style={{ background: QB_GREEN, borderColor: QB_GREEN }}
          >
            {loading ? 'Pushing...' : 'Push to QuickBooks'}
          </button>
        </div>
      </div>
    </div>
  );
}

// ── QBXpress Sync Payroll Modal ──────────────────────────────────
function SyncPayrollQBXModal({ onClose, onSync }) {
  const [runs, setRuns] = useState([]);
  const [selectedId, setSelectedId] = useState('');
  const [loading, setLoading] = useState(false);
  const QBX_BLUE = '#2563eb';

  useEffect(() => {
    api.getPayrollHistory({ limit: 20 }).then(r => setRuns(r.runs || []));
  }, []);

  const handleSync = async () => {
    if (!selectedId) return;
    setLoading(true);
    try {
      const res = await api.syncPayrollToQBX(selectedId);
      onSync({ type: 'success', message: `Payroll synced to QBXpress`, details: `Period: ${res.period} | ${res.employee_count} employees | $${Number(res.total_gross || 0).toLocaleString()} gross` });
      onClose();
    } catch (e) {
      onSync({ type: 'error', message: e.message });
      onClose();
    } finally {
      setLoading(false);
    }
  };

  return (
    <div style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.7)', zIndex: 1000, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
      <div style={{ background: 'var(--card)', borderRadius: 16, padding: 28, width: 480, border: '1px solid rgba(255,255,255,0.1)', boxShadow: '0 24px 64px rgba(0,0,0,0.6)' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 20 }}>
          <h3 style={{ margin: 0, fontSize: 18 }}>Push Payroll to QBXpress</h3>
          <button onClick={onClose} style={{ background: 'none', border: 'none', color: 'rgba(255,255,255,0.5)', cursor: 'pointer', fontSize: 20 }}>✕</button>
        </div>
        <p style={{ fontSize: 13, color: 'rgba(255,255,255,0.5)', marginBottom: 16, lineHeight: 1.5 }}>
          Push a completed pay run to QBXpress. It will appear in your QBXpress Integrations dashboard as a payroll sync record.
        </p>
        <div style={{ marginBottom: 16 }}>
          <label style={{ fontSize: 13, color: 'rgba(255,255,255,0.6)', display: 'block', marginBottom: 6 }}>Pay Run</label>
          <select value={selectedId} onChange={e => setSelectedId(e.target.value)}
            style={{ width: '100%', padding: '10px 12px', borderRadius: 8, background: 'rgba(255,255,255,0.06)', border: '1px solid rgba(255,255,255,0.15)', color: '#fff', fontSize: 14 }}>
            <option value="">Select a pay run...</option>
            {runs.filter(r => r.status === 'completed').map(r => (
              <option key={r.id} value={r.id}>
                {new Date(r.created_at).toLocaleDateString()} — {r.employee_count} employees — ${Number(r.total_gross || 0).toLocaleString()}
              </option>
            ))}
          </select>
        </div>
        <div style={{ display: 'flex', gap: 10, justifyContent: 'flex-end' }}>
          <button className="btn" onClick={onClose}>Cancel</button>
          <button className="btn btn-primary" onClick={handleSync} disabled={!selectedId || loading}
            style={{ background: QBX_BLUE, borderColor: QBX_BLUE }}>
            {loading ? 'Pushing...' : 'Push to QBXpress'}
          </button>
        </div>
      </div>
    </div>
  );
}

// ── Main IntegrationsPage ────────────────────────────────────────
export default function IntegrationsPage() {
  // QuickBooks state
  const [status, setStatus] = useState(null);
  const [loading, setLoading] = useState(true);
  const [actionLoading, setActionLoading] = useState('');
  const [result, setResult] = useState(null);
  const [qbData, setQbData] = useState(null);
  const [showPayrollModal, setShowPayrollModal] = useState(false);

  // QBXpress state
  const [qbxStatus, setQbxStatus] = useState(null);
  const [qbxLoading, setQbxLoading] = useState(true);
  const [qbxActionLoading, setQbxActionLoading] = useState('');
  const [qbxData, setQbxData] = useState(null);
  const [showQBXPayrollModal, setShowQBXPayrollModal] = useState(false);

  const loadStatus = useCallback(async () => {
    setLoading(true);
    try {
      const s = await api.getQBStatus();
      setStatus(s);
    } catch (e) {
      setStatus({ connected: false });
    } finally {
      setLoading(false);
    }
  }, []);

  const loadQBXStatus = useCallback(async () => {
    setQbxLoading(true);
    try {
      const s = await api.getQBXStatus();
      setQbxStatus(s);
    } catch (e) {
      setQbxStatus({ connected: false });
    } finally {
      setQbxLoading(false);
    }
  }, []);

  useEffect(() => { loadStatus(); loadQBXStatus(); }, [loadStatus, loadQBXStatus]);

  // Listen for OAuth popup messages (both QB and QBXpress)
  useEffect(() => {
    const handler = (event) => {
      if (event.data?.type === 'qb_oauth') {
        if (event.data.status === 'connected') {
          setResult({ type: 'success', message: event.data.message || 'QuickBooks connected!' });
          loadStatus();
        } else {
          setResult({ type: 'error', message: event.data.message || 'Connection failed' });
        }
      }
      if (event.data?.type === 'qbx_oauth') {
        if (event.data.status === 'connected') {
          setResult({ type: 'success', message: event.data.message || 'QBXpress connected!' });
          loadQBXStatus();
        } else {
          setResult({ type: 'error', message: event.data.message || 'QBXpress connection failed' });
        }
      }
    };
    window.addEventListener('message', handler);
    return () => window.removeEventListener('message', handler);
  }, [loadStatus, loadQBXStatus]);

  const handleConnect = async () => {
    setActionLoading('connect');
    try {
      const { url } = await api.getQBAuthUrl();
      window.open(url, 'qb_oauth', 'width=600,height=700,scrollbars=yes');
    } catch (e) {
      setResult({ type: 'error', message: 'Could not get QuickBooks authorization URL' });
    } finally {
      setActionLoading('');
    }
  };

  const handleDisconnect = async () => {
    if (!window.confirm('Disconnect QuickBooks? You can reconnect anytime.')) return;
    setActionLoading('disconnect');
    try {
      await api.disconnectQB();
      setResult({ type: 'success', message: 'QuickBooks disconnected' });
      setStatus({ connected: false });
      setQbData(null);
    } catch (e) {
      setResult({ type: 'error', message: e.message });
    } finally {
      setActionLoading('');
    }
  };

  const handleRefresh = async () => {
    setActionLoading('refresh');
    try {
      await api.forceRefreshQB();
      setResult({ type: 'success', message: 'QuickBooks token refreshed manually' });
      loadStatus();
    } catch (e) {
      setResult({ type: 'error', message: e.message });
    } finally {
      setActionLoading('');
    }
  };

  const handleFetchEmployees = async () => {
    setActionLoading('fetchEmp');
    setQbData(null);
    try {
      const res = await api.fetchQBEmployees();
      setQbData({ type: 'employees', data: res.employees || [] });
    } catch (e) {
      setResult({ type: 'error', message: e.message });
    } finally {
      setActionLoading('');
    }
  };

  const handleFetchAccounts = async () => {
    setActionLoading('fetchAcc');
    setQbData(null);
    try {
      const res = await api.fetchQBAccounts();
      setQbData({ type: 'accounts', data: res.accounts || [] });
    } catch (e) {
      setResult({ type: 'error', message: e.message });
    } finally {
      setActionLoading('');
    }
  };

  const handleSyncEmployees = async () => {
    setActionLoading('syncEmp');
    try {
      const res = await api.syncEmployeesToQB();
      const allItems = [...(res.created || []), ...(res.errors || [])];
      setResult({
        type: res.errors?.length > 0 && res.created?.length === 0 ? 'error' : 'success',
        message: res.message,
        items: allItems,
      });
    } catch (e) {
      setResult({ type: 'error', message: e.message });
    } finally {
      setActionLoading('');
    }
  };

  const handleImportEmployees = async (qbIds = null) => {
    setActionLoading('importEmp');
    try {
      const res = await api.importEmployeesFromQB(qbIds || []);
      setResult({
        type: 'success',
        message: res.message,
        items: [...(res.imported || []), ...(res.errors || [])],
      });
      // Clear preview after successful import of all
      if (!qbIds) setQbData(null);
    } catch (e) {
      setResult({ type: 'error', message: e.message });
    } finally {
      setActionLoading('');
    }
  };

  // ── QBXpress handlers ──────────────────────────────────────────
  const QBX_BLUE = '#2563eb';

  const handleQBXConnect = async () => {
    setQbxActionLoading('connect');
    try {
      const { url } = await api.getQBXAuthUrl();
      window.open(url, 'qbx_oauth', 'width=480,height=680,scrollbars=yes');
    } catch (e) {
      setResult({ type: 'error', message: 'Could not reach QBXpress. Check that QBXpress is running.' });
    } finally {
      setQbxActionLoading('');
    }
  };

  const handleQBXDisconnect = async () => {
    if (!window.confirm('Disconnect QBXpress? You can reconnect anytime.')) return;
    setQbxActionLoading('disconnect');
    try {
      await api.disconnectQBX();
      setResult({ type: 'success', message: 'QBXpress disconnected' });
      setQbxStatus({ connected: false });
      setQbxData(null);
    } catch (e) {
      setResult({ type: 'error', message: e.message });
    } finally {
      setQbxActionLoading('');
    }
  };

  const handleFetchQBXCompany = async () => {
    setQbxActionLoading('fetchCompany');
    setQbxData(null);
    try {
      const res = await api.fetchQBXCompany();
      setQbxData({ type: 'company', data: res });
    } catch (e) {
      setResult({ type: 'error', message: e.message });
    } finally {
      setQbxActionLoading('');
    }
  };

  const handleFetchQBXAccounts = async () => {
    setQbxActionLoading('fetchQBXAcc');
    setQbxData(null);
    try {
      const res = await api.fetchQBXAccounts();
      setQbxData({ type: 'qbxAccounts', data: res.accounts || [] });
    } catch (e) {
      setResult({ type: 'error', message: e.message });
    } finally {
      setQbxActionLoading('');
    }
  };

  const handleSyncQBXEmployees = async () => {
    setQbxActionLoading('syncQBXEmp');
    try {
      const res = await api.syncEmployeesFromQBX();
      setResult({ type: 'success', message: res.message });
    } catch (e) {
      setResult({ type: 'error', message: e.message });
    } finally {
      setQbxActionLoading('');
    }
  };

  const handleSyncQBXEmployeesToQBX = async () => {
    setQbxActionLoading('syncQBXEmpPush');
    try {
      const res = await api.syncEmployeesToQBX();
      setResult({ type: 'success', message: res.message });
    } catch (e) {
      setResult({ type: 'error', message: e.message });
    } finally {
      setQbxActionLoading('');
    }
  };

  const qbxConnected = qbxStatus?.connected;

  const connected = status?.connected;

  const empColumns = [
    { key: 'Id', label: 'QB ID' },
    { key: 'GivenName', label: 'First Name' },
    { key: 'FamilyName', label: 'Last Name' },
    { key: 'PrimaryEmailAddr', label: 'Email', render: r => r.PrimaryEmailAddr?.Address || '—' },
    { key: 'Active', label: 'Status', render: r => r.Active ? <span style={{ color: QB_GREEN }}>Active</span> : <span style={{ color: '#f87171' }}>Inactive</span> },
    { key: 'HiredDate', label: 'Hire Date', render: r => r.HiredDate || '—' },
    {
      key: 'action',
      label: 'Action',
      render: r => r.is_imported ? (
        <span style={{ fontSize: 11, color: QB_GREEN, fontWeight: 600 }}>✓ Imported</span>
      ) : (
        <button
          onClick={() => handleImportEmployees([r.Id])}
          disabled={!!actionLoading}
          style={{
            padding: '4px 10px', borderRadius: 4, background: QB_GREEN, border: 'none', color: '#fff', fontSize: 11, cursor: 'pointer', opacity: actionLoading ? 0.6 : 1
          }}
        >
          {actionLoading === 'importEmp' ? '...' : 'Import'}
        </button>
      )
    },
  ];

  const accColumns = [
    { key: 'Id', label: 'QB ID' },
    { key: 'Name', label: 'Account Name' },
    { key: 'AccountType', label: 'Type' },
    { key: 'AccountSubType', label: 'Sub-type' },
    { key: 'CurrentBalance', label: 'Balance', render: r => r.CurrentBalance != null ? `$${Number(r.CurrentBalance).toLocaleString()}` : '—' },
    { key: 'Active', label: 'Active', render: r => r.Active ? 'Yes' : 'No' },
  ];

  return (
    <div className="page">
      <div className="page-header">
        <div>
          <h1>Integrations</h1>

        </div>
      </div>

      {/* Results / alerts */}
      <ResultBlock result={result} onClose={() => setResult(null)} />


      {/* ── QuickBooks Card ── */}
      <div style={{
        borderRadius: 16, border: `1px solid ${connected ? 'rgba(44,160,28,0.35)' : 'rgba(255,255,255,0.12)'}`,
        background: connected ? 'rgba(44,160,28,0.05)' : 'rgba(255,255,255,0.03)',
        overflow: 'hidden',
      }}>
        {/* Card header */}
        <div style={{ padding: '24px 28px', borderBottom: '1px solid rgba(255,255,255,0.08)' }}>
          <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', gap: 16 }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 16 }}>
              <QBLogo size={44} />
              <div>
                <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 4 }}>
                  <h2 style={{ margin: 0, fontSize: 20, fontWeight: 700 }}>QuickBooks Online</h2>
                  {!loading && (
                    <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                      <StatusBadge connected={connected} tokenValid={status?.token_valid} />
                      {connected && (
                        <button
                          onClick={handleRefresh}
                          disabled={!!actionLoading}
                          title="Force token refresh"
                          style={{
                            background: 'none', border: 'none', color: 'rgba(255,255,255,0.3)',
                            cursor: 'pointer', padding: 0, display: 'flex', alignItems: 'center',
                            fontSize: 11, textDecoration: 'underline'
                          }}
                        >
                          {actionLoading === 'refresh' ? 'Refreshing...' : 'Refresh'}
                        </button>
                      )}
                    </div>
                  )}
                </div>
                <p style={{ margin: 0, fontSize: 14, color: 'rgba(255,255,255,0.55)', lineHeight: 1.5, maxWidth: 520 }}>
                  Full two-way sync with QuickBooks Online via official OAuth 2.0 API.
                  Import employees, push payroll journal entries, and keep your books in sync automatically.
                </p>
              </div>
            </div>

            {loading ? (
              <div style={{ color: 'rgba(255,255,255,0.3)', fontSize: 13 }}>Loading...</div>
            ) : connected ? (
              <button
                className="btn"
                onClick={handleDisconnect}
                disabled={actionLoading === 'disconnect'}
                style={{ whiteSpace: 'nowrap', borderColor: 'rgba(220,50,50,0.4)', color: '#f87171' }}
              >
                {actionLoading === 'disconnect' ? 'Disconnecting...' : 'Disconnect'}
              </button>
            ) : (
              <button
                onClick={handleConnect}
                disabled={actionLoading === 'connect'}
                style={{
                  whiteSpace: 'nowrap', padding: '10px 20px', borderRadius: 9, fontWeight: 600,
                  fontSize: 14, cursor: 'pointer', border: 'none',
                  background: QB_GREEN, color: '#fff',
                  opacity: actionLoading === 'connect' ? 0.7 : 1,
                }}
              >
                {actionLoading === 'connect' ? 'Redirecting...' : '⚡ Connect QuickBooks'}
              </button>
            )}
          </div>

          {/* Connection details row */}
          {connected && status && (
            <div style={{
              marginTop: 18, display: 'flex', flexWrap: 'wrap', gap: 24,
              padding: '14px 18px', borderRadius: 10,
              background: 'rgba(255,255,255,0.04)', border: '1px solid rgba(255,255,255,0.08)',
            }}>
              {[
                ['Company', status.qb_company_name || status.realm_id],
                ['Environment', status.is_sandbox ? 'Sandbox' : 'Production'],
                ['Connected', fmtDate(status.connected_at)],
                ['Last synced', fmtDate(status.last_synced_at)],
                ['Token expires', fmtDate(status.token_expires_at)],
              ].map(([label, val]) => (
                <div key={label}>
                  <div style={{ fontSize: 11, color: 'rgba(255,255,255,0.35)', marginBottom: 2 }}>{label}</div>
                  <div style={{ fontSize: 13, fontWeight: 500 }}>{val || '—'}</div>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* ── Action panels (only when connected) ── */}
        {connected && (
          <div style={{ padding: '20px 28px 28px' }}>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))', gap: 16 }}>

              {/* Pull from QB */}
              <ActionPanel
                title="Pull from QuickBooks"
                icon="↓"
                iconColor="#60A5FA"
                items={[
                  {
                    label: 'View QB Employees',
                    desc: 'Fetch all employee records from your QuickBooks company',
                    onClick: handleFetchEmployees,
                    loading: actionLoading === 'fetchEmp',
                  },
                  {
                    label: 'View Chart of Accounts',
                    desc: 'Browse your QuickBooks accounts for payroll mapping',
                    onClick: handleFetchAccounts,
                    loading: actionLoading === 'fetchAcc',
                  },
                ]}
              />

              {/* Import into PayrollOS */}
              <ActionPanel
                title="Import into PayrollOS"
                icon="⬇"
                iconColor={QB_GREEN}
                items={[
                  {
                    label: 'Import QB Employees',
                    desc: 'Create PayrollOS employees from your QuickBooks employee list',
                    onClick: () => handleImportEmployees(),
                    loading: actionLoading === 'importEmp',
                    cta: true,
                  },
                ]}
              />

              {/* Push to QB */}
              <ActionPanel
                title="Push to QuickBooks"
                icon="↑"
                iconColor="#F59E0B"
                items={[
                  {
                    label: 'Sync Employees to QB',
                    desc: 'Push all active PayrollOS employees into QuickBooks',
                    onClick: handleSyncEmployees,
                    loading: actionLoading === 'syncEmp',
                  },
                  {
                    label: 'Push Payroll Journal Entry',
                    desc: 'Record a completed pay run as a double-entry journal in QB',
                    onClick: () => setShowPayrollModal(true),
                    loading: false,
                  },
                ]}
              />

            </div>

            {/* QB Data Table Preview */}
            {qbData?.type === 'employees' && (
              <QBDataTable
                title="QuickBooks Employees"
                data={qbData.data}
                columns={empColumns}
                onClose={() => setQbData(null)}
              />
            )}
            {qbData?.type === 'accounts' && (
              <QBDataTable
                title="QuickBooks Chart of Accounts"
                data={qbData.data}
                columns={accColumns}
                onClose={() => setQbData(null)}
              />
            )}

            {/* How it works */}
            <div style={{
              marginTop: 24, padding: '18px 20px', borderRadius: 10,
              background: 'rgba(255,255,255,0.03)', border: '1px solid rgba(255,255,255,0.07)',
            }}>
              <div style={{ fontSize: 13, fontWeight: 600, marginBottom: 12, color: 'rgba(255,255,255,0.6)' }}>
                How sync works
              </div>
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: 12 }}>
                {[
                  ['Employees', 'PayrollOS pushes employee name, email, phone, address, and hire date to QB. Already-synced employees are skipped. QB IDs are stored for future updates.'],
                  ['Payroll Journal Entry', 'Each completed pay run creates a balanced journal entry: Payroll Expense and Tax Expense (debit) offset against Net Payroll Clearing and Tax Liabilities (credit).'],
                  ['Token Refresh', 'OAuth tokens are refreshed automatically before they expire (100-day refresh token). No need to reconnect unless you explicitly disconnect.'],
                ].map(([title, desc]) => (
                  <div key={title} style={{ fontSize: 12, color: 'rgba(255,255,255,0.45)', lineHeight: 1.6 }}>
                    <div style={{ fontWeight: 600, color: 'rgba(255,255,255,0.65)', marginBottom: 4 }}>{title}</div>
                    {desc}
                  </div>
                ))}
              </div>
            </div>
          </div>
        )}

        {/* Setup instructions (when not connected) */}
        {!connected && !loading && (
          <div style={{ padding: '20px 28px 28px' }}>
            <div style={{
              padding: '18px 20px', borderRadius: 10,
              background: 'rgba(255,255,255,0.03)', border: '1px solid rgba(255,255,255,0.08)',
            }}>
              <div style={{ fontSize: 13, fontWeight: 600, marginBottom: 14, color: 'rgba(255,255,255,0.6)' }}>
                Setup instructions
              </div>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
                {[
                  ['1', 'Create a QuickBooks app at developer.intuit.com and get your Client ID and Client Secret.'],
                  ['2', `Set QB_CLIENT_ID, QB_CLIENT_SECRET in your backend .env file. Set QB_REDIRECT_URI to your backend callback URL (default: http://localhost:8000/quickbooks/callback).`],
                  ['3', 'Click "Connect QuickBooks" above — a popup will open to log into your QuickBooks account.'],
                  ['4', 'Approve the permissions. The popup closes and your connection is saved automatically.'],
                  ['5', 'Use the sync tools to push employees and payroll data between systems.'],
                ].map(([num, text]) => (
                  <div key={num} style={{ display: 'flex', gap: 12, fontSize: 13, color: 'rgba(255,255,255,0.55)', lineHeight: 1.6 }}>
                    <div style={{
                      width: 22, height: 22, borderRadius: '50%', background: 'rgba(44,160,28,0.2)',
                      color: QB_GREEN, display: 'flex', alignItems: 'center', justifyContent: 'center',
                      fontSize: 11, fontWeight: 700, flexShrink: 0, marginTop: 1,
                    }}>{num}</div>
                    <div>{text}</div>
                  </div>
                ))}
              </div>
            </div>
          </div>
        )}
      </div>

      {/* ── QBXpress Card ── */}
      <div style={{
        borderRadius: 16, marginTop: 20,
        border: `1px solid ${qbxConnected ? 'rgba(37,99,235,0.4)' : 'rgba(255,255,255,0.12)'}`,
        background: qbxConnected ? 'rgba(37,99,235,0.04)' : 'rgba(255,255,255,0.03)',
        overflow: 'hidden',
      }}>
        {/* QBXpress header */}
        <div style={{ padding: '24px 28px', borderBottom: '1px solid rgba(255,255,255,0.08)' }}>
          <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', gap: 16 }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 16 }}>
              {/* QBXpress logo mark */}
              <div style={{ width: 44, height: 44, borderRadius: 12, background: 'linear-gradient(135deg, #2563eb 0%, #1d4ed8 100%)', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 15, fontWeight: 700, color: '#fff', flexShrink: 0 }}>QB</div>
              <div>
                <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 4 }}>
                  <h2 style={{ margin: 0, fontSize: 20, fontWeight: 700 }}>QBXpress</h2>
                  {!qbxLoading && (
                    <span style={{
                      fontSize: 12, padding: '3px 10px', borderRadius: 20,
                      background: qbxConnected ? 'rgba(37,99,235,0.15)' : 'rgba(255,255,255,0.08)',
                      color: qbxConnected ? '#60a5fa' : 'rgba(255,255,255,0.4)',
                      border: qbxConnected ? '1px solid rgba(37,99,235,0.3)' : 'none',
                    }}>
                      {qbxConnected ? '● Connected' : 'Not connected'}
                    </span>
                  )}
                </div>
                <p style={{ margin: 0, fontSize: 14, color: 'rgba(255,255,255,0.55)', lineHeight: 1.5, maxWidth: 520 }}>
                  Connect to your QBXpress bookkeeping account. Fetch QuickBooks data via QBXpress, view financial accounts, and push payroll records for your bookkeeper to review.
                </p>
              </div>
            </div>

            {qbxLoading ? (
              <div style={{ color: 'rgba(255,255,255,0.3)', fontSize: 13 }}>Loading...</div>
            ) : qbxConnected ? (
              <button className="btn" onClick={handleQBXDisconnect} disabled={qbxActionLoading === 'disconnect'}
                style={{ whiteSpace: 'nowrap', borderColor: 'rgba(220,50,50,0.4)', color: '#f87171' }}>
                {qbxActionLoading === 'disconnect' ? 'Disconnecting...' : 'Disconnect'}
              </button>
            ) : (
              <button onClick={handleQBXConnect} disabled={qbxActionLoading === 'connect'}
                style={{ whiteSpace: 'nowrap', padding: '10px 20px', borderRadius: 9, fontWeight: 600, fontSize: 14, cursor: 'pointer', border: 'none', background: QBX_BLUE, color: '#fff', opacity: qbxActionLoading === 'connect' ? 0.7 : 1 }}>
                {qbxActionLoading === 'connect' ? 'Redirecting...' : '⚡ Connect QBXpress'}
              </button>
            )}
          </div>

          {/* Connection info */}
          {qbxConnected && qbxStatus && (
            <div style={{ marginTop: 18, display: 'flex', flexWrap: 'wrap', gap: 24, padding: '14px 18px', borderRadius: 10, background: 'rgba(255,255,255,0.04)', border: '1px solid rgba(255,255,255,0.08)' }}>
              {[
                ['Company', qbxStatus.qbx_company_name || '—'],
                ['Connected', fmtDate(qbxStatus.connected_at)],
                ['Last synced', fmtDate(qbxStatus.last_synced_at)],
              ].map(([label, val]) => (
                <div key={label}>
                  <div style={{ fontSize: 11, color: 'rgba(255,255,255,0.35)', marginBottom: 2 }}>{label}</div>
                  <div style={{ fontSize: 13, fontWeight: 500 }}>{val || '—'}</div>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Action panels when connected */}
        {qbxConnected && (
          <div style={{ padding: '20px 28px 28px' }}>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(260px, 1fr))', gap: 16 }}>
              <ActionPanel title="Fetch from QBXpress" icon="↓" iconColor="#60A5FA" items={[
                { label: 'View Company Info', desc: 'Fetch your QBXpress company and QB connection status', onClick: handleFetchQBXCompany, loading: qbxActionLoading === 'fetchCompany' },
                { label: 'View QB Accounts', desc: 'Fetch chart of accounts from QB via QBXpress', onClick: handleFetchQBXAccounts, loading: qbxActionLoading === 'fetchQBXAcc' },
                { label: 'Sync Employees from QBX', desc: 'Pull all employees from QBXpress and upsert into PayrollOS', onClick: handleSyncQBXEmployees, loading: qbxActionLoading === 'syncQBXEmp', cta: true },
              ]} />
              <ActionPanel title="Push to QBXpress" icon="↑" iconColor="#F59E0B" items={[
                { label: 'Sync Employees to QBX', desc: 'Push all active PayrollOS employees into QBXpress', onClick: handleSyncQBXEmployeesToQBX, loading: qbxActionLoading === 'syncQBXEmpPush' },
                { label: 'Push Payroll Record', desc: "Send a completed pay run to your bookkeeper's QBXpress dashboard", onClick: () => setShowQBXPayrollModal(true), loading: false },
              ]} />
            </div>

            {/* Company info display */}
            {qbxData?.type === 'company' && qbxData.data && (
              <div style={{ margin: '16px 0', padding: 16, borderRadius: 10, background: 'rgba(255,255,255,0.04)', border: '1px solid rgba(255,255,255,0.1)' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 }}>
                  <div style={{ fontSize: 14, fontWeight: 600 }}>QBXpress Company Info</div>
                  <button onClick={() => setQbxData(null)} style={{ background: 'none', border: 'none', color: 'rgba(255,255,255,0.4)', cursor: 'pointer', fontSize: 16 }}>✕</button>
                </div>
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(160px, 1fr))', gap: 12, fontSize: 13 }}>
                  {[['Company', qbxData.data.company], ['Name', qbxData.data.name], ['Email', qbxData.data.email], ['QB Connected', qbxData.data.qbConnected ? 'Yes' : 'No']].map(([l, v]) => v && (
                    <div key={l}><div style={{ fontSize: 11, color: 'rgba(255,255,255,0.35)', marginBottom: 2 }}>{l}</div><div style={{ fontWeight: 500 }}>{v}</div></div>
                  ))}
                </div>
              </div>
            )}

            {/* QB Accounts via QBXpress */}
            {qbxData?.type === 'qbxAccounts' && (
              <QBDataTable title="QuickBooks Accounts (via QBXpress)" data={qbxData.data}
                columns={[
                  { key: 'Id', label: 'ID' }, { key: 'Name', label: 'Account Name' },
                  { key: 'AccountType', label: 'Type' }, { key: 'AccountSubType', label: 'Sub-type' },
                  { key: 'CurrentBalance', label: 'Balance', render: r => r.CurrentBalance != null ? `$${Number(r.CurrentBalance).toLocaleString()}` : '—' },
                ]}
                onClose={() => setQbxData(null)}
              />
            )}
          </div>
        )}

        {/* Setup instructions when not connected */}
        {!qbxConnected && !qbxLoading && (
          <div style={{ padding: '20px 28px 28px' }}>
            <div style={{ padding: '18px 20px', borderRadius: 10, background: 'rgba(255,255,255,0.03)', border: '1px solid rgba(255,255,255,0.08)' }}>
              <div style={{ fontSize: 13, fontWeight: 600, marginBottom: 14, color: 'rgba(255,255,255,0.6)' }}>How to connect</div>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
                {[
                  ['1', 'Make sure you have a QBXpress account at payroll.qbxpress.com.'],
                  ['2', 'Click "Connect QBXpress" above — a popup will open to the QBXpress authorization page.'],
                  ['3', 'Log in with your QBXpress credentials and click "Authorize PayrollOS".'],
                  ['4', 'The popup closes automatically and your connection is saved.'],
                  ['5', 'Use the sync tools to fetch QuickBooks data via QBXpress or push payroll records to your bookkeeper.'],
                ].map(([num, text]) => (
                  <div key={num} style={{ display: 'flex', gap: 12, fontSize: 13, color: 'rgba(255,255,255,0.55)', lineHeight: 1.6 }}>
                    <div style={{ width: 22, height: 22, borderRadius: '50%', background: 'rgba(37,99,235,0.2)', color: '#60a5fa', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 11, fontWeight: 700, flexShrink: 0, marginTop: 1 }}>{num}</div>
                    <div>{text}</div>
                  </div>
                ))}
              </div>
            </div>
          </div>
        )}
      </div>

      {/* Sync Payroll Modal (QuickBooks) */}
      {showPayrollModal && (
        <SyncPayrollModal
          onClose={() => setShowPayrollModal(false)}
          onSync={(r) => setResult(r)}
        />
      )}

      {/* Sync Payroll Modal (QBXpress) */}
      {showQBXPayrollModal && (
        <SyncPayrollQBXModal
          onClose={() => setShowQBXPayrollModal(false)}
          onSync={(r) => setResult(r)}
        />
      )}
    </div>
  );
}

// ── ActionPanel component ────────────────────────────────────────
function ActionPanel({ title, icon, iconColor, items }) {
  return (
    <div style={{
      borderRadius: 12, border: '1px solid rgba(255,255,255,0.08)',
      background: 'rgba(255,255,255,0.03)', overflow: 'hidden',
    }}>
      <div style={{
        padding: '12px 16px', borderBottom: '1px solid rgba(255,255,255,0.06)',
        display: 'flex', alignItems: 'center', gap: 8,
      }}>
        <span style={{ fontSize: 16, color: iconColor }}>{icon}</span>
        <span style={{ fontWeight: 600, fontSize: 14 }}>{title}</span>
      </div>
      <div style={{ padding: 12, display: 'flex', flexDirection: 'column', gap: 8 }}>
        {items.map((item, i) => (
          <div key={i} style={{
            padding: '12px 14px', borderRadius: 9,
            background: 'rgba(255,255,255,0.03)', border: '1px solid rgba(255,255,255,0.06)',
          }}>
            <div style={{ fontSize: 13, fontWeight: 600, marginBottom: 4 }}>{item.label}</div>
            <div style={{ fontSize: 12, color: 'rgba(255,255,255,0.45)', marginBottom: 10, lineHeight: 1.5 }}>{item.desc}</div>
            <button
              className="btn btn-sm"
              onClick={item.onClick}
              disabled={item.loading}
              style={item.cta ? { background: QB_GREEN, borderColor: QB_GREEN, color: '#fff' } : {}}
            >
              {item.loading ? 'Working...' : item.label}
            </button>
          </div>
        ))}
      </div>
    </div>
  );
}
