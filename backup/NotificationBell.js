import React, { useState, useEffect, useRef, useCallback } from 'react';

const BASE = process.env.REACT_APP_API_URL || 'http://localhost:8000';
const tkn = () => localStorage.getItem('payroll_token');

async function req(path, opts = {}) {
  const res = await fetch(`${BASE}${path}`, {
    ...opts,
    headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${tkn()}`, ...opts.headers },
  });
  if (!res.ok) return null;
  if (res.status === 204) return null;
  return res.json();
}

const SEV_COLORS = {
  critical: { bg: 'var(--red-bg)', text: 'var(--red)', dot: '#e24b4a' },
  warning:  { bg: 'var(--amber-bg)', text: 'var(--amber)', dot: '#ef9f27' },
  success:  { bg: 'var(--green-bg)', text: 'var(--green)', dot: '#639922' },
  info:     { bg: 'var(--blue-bg)', text: 'var(--blue)', dot: '#378add' },
};

const TYPE_ICONS = {
  payroll_complete: '✓', paystub_ready: '◧', pto_request: '◌',
  compliance: '⚠', leave_request: '◫', onboarding: '☑',
  document_uploaded: '◨', expense_submitted: '$', review_due: '◆',
  default: 'ℹ',
};

function timeAgo(dateStr) {
  if (!dateStr) return '';
  const diff = (Date.now() - new Date(dateStr).getTime()) / 1000;
  if (diff < 60) return 'just now';
  if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;
  if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`;
  return `${Math.floor(diff / 86400)}d ago`;
}

export default function NotificationBell({ onNavigate }) {
  const [open, setOpen] = useState(false);
  const [data, setData] = useState({ unread_count: 0, notifications: [] });
  const [loading, setLoading] = useState(false);
  const ref = useRef(null);

  const load = useCallback(async () => {
    const r = await req('/notifications?limit=20');
    if (r) setData(r);
  }, []);

  // Poll every 30 seconds
  useEffect(() => {
    load();
    const interval = setInterval(load, 30000);
    return () => clearInterval(interval);
  }, [load]);

  // Close on outside click
  useEffect(() => {
    const handler = (e) => { if (ref.current && !ref.current.contains(e.target)) setOpen(false); };
    document.addEventListener('mousedown', handler);
    return () => document.removeEventListener('mousedown', handler);
  }, []);

  const markRead = async (id) => {
    await req(`/notifications/${id}/read`, { method: 'POST' });
    setData(d => ({
      ...d,
      unread_count: Math.max(0, d.unread_count - 1),
      notifications: d.notifications.map(n => n.id === id ? { ...n, is_read: true } : n),
    }));
  };

  const markAllRead = async () => {
    await req('/notifications/read-all', { method: 'POST' });
    setData(d => ({ ...d, unread_count: 0, notifications: d.notifications.map(n => ({ ...n, is_read: true })) }));
  };

  const dismiss = async (id, e) => {
    e.stopPropagation();
    await req(`/notifications/${id}`, { method: 'DELETE' });
    setData(d => ({
      ...d,
      notifications: d.notifications.filter(n => n.id !== id),
      unread_count: d.notifications.find(n => n.id === id && !n.is_read) ? d.unread_count - 1 : d.unread_count,
    }));
  };

  const handleClick = (notif) => {
    if (!notif.is_read) markRead(notif.id);
    if (notif.action_url && onNavigate) {
      onNavigate(notif.action_url.replace('/', ''));
      setOpen(false);
    }
  };

  const unread = data.unread_count;

  return (
    <div ref={ref} style={{ position: 'relative' }}>
      {/* Bell button */}
      <button
        onClick={() => setOpen(!open)}
        style={{
          background: 'none', border: '1px solid var(--border)', borderRadius: 8,
          padding: '6px 10px', cursor: 'pointer', position: 'relative',
          color: 'var(--text)', display: 'flex', alignItems: 'center', gap: 6,
          transition: 'background 0.12s',
        }}
        onMouseEnter={e => e.currentTarget.style.background = 'var(--bg2)'}
        onMouseLeave={e => e.currentTarget.style.background = 'none'}
      >
        <span style={{ fontSize: 14 }}>🔔</span>
        {unread > 0 && (
          <span style={{
            position: 'absolute', top: -4, right: -4,
            background: 'var(--red)', color: '#fff',
            borderRadius: '99px', fontSize: 10, fontWeight: 700,
            minWidth: 16, height: 16, display: 'flex', alignItems: 'center',
            justifyContent: 'center', padding: '0 4px', lineHeight: 1,
          }}>
            {unread > 99 ? '99+' : unread}
          </span>
        )}
      </button>

      {/* Dropdown panel */}
      {open && (
        <div style={{
          position: 'absolute', right: 0, top: 'calc(100% + 8px)',
          width: 360, background: 'var(--bg)', border: '1px solid var(--border)',
          borderRadius: 12, boxShadow: '0 8px 24px rgba(0,0,0,0.12)',
          zIndex: 1000, overflow: 'hidden', maxHeight: '80vh',
          display: 'flex', flexDirection: 'column',
        }}>
          {/* Header */}
          <div style={{
            padding: '12px 16px', borderBottom: '1px solid var(--border)',
            display: 'flex', justifyContent: 'space-between', alignItems: 'center',
          }}>
            <span style={{ fontWeight: 500, fontSize: 14 }}>
              Notifications {unread > 0 && <span style={{ color: 'var(--blue)', fontSize: 12 }}>({unread} unread)</span>}
            </span>
            {unread > 0 && (
              <button onClick={markAllRead} style={{
                background: 'none', border: 'none', cursor: 'pointer',
                fontSize: 12, color: 'var(--blue)', padding: 0,
              }}>
                Mark all read
              </button>
            )}
          </div>

          {/* List */}
          <div style={{ overflowY: 'auto', flex: 1 }}>
            {data.notifications.length === 0 && (
              <div style={{ padding: 32, textAlign: 'center', color: 'var(--text3)', fontSize: 13 }}>
                <div style={{ fontSize: 24, marginBottom: 8 }}>🔔</div>
                No notifications
              </div>
            )}
            {data.notifications.map(n => {
              const sev = SEV_COLORS[n.severity] || SEV_COLORS.info;
              const icon = TYPE_ICONS[n.type] || TYPE_ICONS.default;
              return (
                <div
                  key={n.id}
                  onClick={() => handleClick(n)}
                  style={{
                    padding: '12px 16px',
                    borderBottom: '1px solid var(--border)',
                    cursor: n.action_url ? 'pointer' : 'default',
                    background: n.is_read ? 'transparent' : 'var(--bg2)',
                    display: 'flex', gap: 10, position: 'relative',
                    transition: 'background 0.12s',
                  }}
                  onMouseEnter={e => e.currentTarget.style.background = 'var(--bg3)'}
                  onMouseLeave={e => e.currentTarget.style.background = n.is_read ? 'transparent' : 'var(--bg2)'}
                >
                  {/* Icon */}
                  <div style={{
                    width: 32, height: 32, borderRadius: 8, background: sev.bg,
                    display: 'flex', alignItems: 'center', justifyContent: 'center',
                    fontSize: 14, color: sev.text, flexShrink: 0,
                  }}>
                    {icon}
                  </div>

                  {/* Content */}
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div style={{ fontWeight: n.is_read ? 400 : 500, fontSize: 13, lineHeight: 1.4 }}>
                      {n.title}
                    </div>
                    {n.body && (
                      <div style={{ fontSize: 12, color: 'var(--text3)', marginTop: 2, lineHeight: 1.4, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                        {n.body}
                      </div>
                    )}
                    <div style={{ fontSize: 11, color: 'var(--text3)', marginTop: 4 }}>
                      {timeAgo(n.created_at)}
                    </div>
                  </div>

                  {/* Unread dot + dismiss */}
                  <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'flex-end', gap: 6, flexShrink: 0 }}>
                    {!n.is_read && (
                      <div style={{ width: 8, height: 8, borderRadius: '50%', background: sev.dot }} />
                    )}
                    <button
                      onClick={(e) => dismiss(n.id, e)}
                      style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--text3)', fontSize: 14, padding: 0, lineHeight: 1 }}
                    >
                      ×
                    </button>
                  </div>
                </div>
              );
            })}
          </div>

          {/* Footer */}
          <div style={{ padding: '8px 16px', borderTop: '1px solid var(--border)', textAlign: 'center' }}>
            <button onClick={() => { setOpen(false); if (onNavigate) onNavigate('audit'); }}
              style={{ background: 'none', border: 'none', cursor: 'pointer', fontSize: 12, color: 'var(--blue)', padding: 0 }}>
              View audit log →
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
