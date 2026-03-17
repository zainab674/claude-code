import React, { useState, useEffect } from 'react';
import * as api from '../services/api';

const BASE = process.env.REACT_APP_API_URL || 'http://localhost:8000';
const token = () => localStorage.getItem('payroll_token');

const ACTION_COLORS = {
  'auth.login': 'info',
  'payroll.run': 'success',
  'payroll.preview': 'info',
  'employee.created': 'success',
  'employee.updated': 'warning',
  'employee.terminated': 'danger',
  'paystub.downloaded': 'info',
  'export': 'info',
  'import': 'warning',
};

function actionColor(action) {
  for (const [key, color] of Object.entries(ACTION_COLORS)) {
    if (action.startsWith(key)) return color;
  }
  return 'info';
}

function fmtDt(dt) {
  if (!dt) return '—';
  const d = new Date(dt);
  return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' }) +
    ' ' + d.toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit' });
}

export default function AuditLog() {
  const [logs, setLogs] = useState([]);
  const [total, setTotal] = useState(0);
  const [filter, setFilter] = useState('');
  const [loading, setLoading] = useState(true);
  const [expanded, setExpanded] = useState(null);

  const load = async () => {
    setLoading(true);
    try {
      const res = await fetch(
        `${BASE}/audit?limit=100${filter ? '&action=' + filter : ''}`,
        { headers: { Authorization: `Bearer ${token()}` } }
      );
      const data = await res.json();
      setLogs(data.logs || []);
      setTotal(data.total || 0);
    } catch {
      setLogs([]);
    }
    setLoading(false);
  };

  useEffect(() => { load(); }, [filter]);

  const ACTION_FILTERS = [
    ['', 'All'],
    ['auth', 'Auth'],
    ['employee', 'Employees'],
    ['payroll', 'Payroll'],
    ['paystub', 'Paystubs'],
    ['export', 'Exports'],
    ['import', 'Imports'],
  ];

  return (
    <div className="page">
      <div className="page-header">
        <h1>Audit Log <span className="count-badge">{total}</span></h1>
        <div className="tab-bar" style={{ margin: 0 }}>
          {ACTION_FILTERS.map(([val, label]) => (
            <button key={val} className={`tab-btn ${filter === val ? 'active' : ''}`}
              onClick={() => setFilter(val)}>{label}</button>
          ))}
        </div>
      </div>

      <div className="card">
        <table className="table">
          <thead>
            <tr>
              <th>Time</th><th>User</th><th>Action</th>
              <th>Resource</th><th>IP</th><th></th>
            </tr>
          </thead>
          <tbody>
            {loading && <tr><td colSpan={6} className="empty">Loading…</td></tr>}
            {!loading && logs.length === 0 && (
              <tr><td colSpan={6} className="empty">No audit events yet — actions will appear here as users interact with the system</td></tr>
            )}
            {logs.map(log => (
              <React.Fragment key={log.id}>
                <tr style={{ cursor: 'pointer' }} onClick={() => setExpanded(expanded === log.id ? null : log.id)}>
                  <td style={{ fontSize: 12, whiteSpace: 'nowrap' }}>{fmtDt(log.created_at)}</td>
                  <td style={{ fontSize: 12 }}>{log.user_email || '—'}</td>
                  <td>
                    <span className={`badge badge-${actionColor(log.action)}`}>
                      {log.action}
                    </span>
                  </td>
                  <td style={{ fontSize: 12, color: 'var(--text3)' }}>
                    {log.resource_type && <span>{log.resource_type}</span>}
                    {log.resource_id && <span style={{ marginLeft: 4, fontFamily: 'monospace', fontSize: 11 }}>{log.resource_id.slice(0, 8)}…</span>}
                  </td>
                  <td style={{ fontSize: 11, color: 'var(--text3)' }}>{log.ip_address || '—'}</td>
                  <td style={{ color: 'var(--text3)', fontSize: 11 }}>{expanded === log.id ? '▲' : '▼'}</td>
                </tr>
                {expanded === log.id && (
                  <tr>
                    <td colSpan={6} style={{ background: 'var(--bg2)', padding: '8px 16px' }}>
                      <pre style={{ fontSize: 11, fontFamily: 'monospace', margin: 0, color: 'var(--text2)', whiteSpace: 'pre-wrap' }}>
                        {JSON.stringify(log.details, null, 2)}
                      </pre>
                    </td>
                  </tr>
                )}
              </React.Fragment>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
