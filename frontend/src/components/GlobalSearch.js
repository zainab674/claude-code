import React, { useState, useEffect, useRef, useCallback } from 'react';

const BASE = process.env.REACT_APP_API_URL || 'http://localhost:8000';
const tkn = () => localStorage.getItem('payroll_token');

function debounce(fn, ms) {
  let t;
  return (...args) => { clearTimeout(t); t = setTimeout(() => fn(...args), ms); };
}

const RESULT_ICONS = { employee: '◉', pay_run: '▶', paystub: '◧', report: '◈' };
const RESULT_COLORS = { employee: 'info', pay_run: 'success', paystub: 'warning', report: 'info' };

export default function GlobalSearch({ onNavigate }) {
  const [query, setQuery] = useState('');
  const [results, setResults] = useState([]);
  const [loading, setLoading] = useState(false);
  const [open, setOpen] = useState(false);
  const [selected, setSelected] = useState(-1);
  const ref = useRef(null);
  const inputRef = useRef(null);

  // Close on outside click
  useEffect(() => {
    const handler = (e) => { if (ref.current && !ref.current.contains(e.target)) setOpen(false); };
    document.addEventListener('mousedown', handler);
    return () => document.removeEventListener('mousedown', handler);
  }, []);

  // Keyboard shortcut: Cmd/Ctrl+K
  useEffect(() => {
    const handler = (e) => {
      if ((e.metaKey || e.ctrlKey) && e.key === 'k') {
        e.preventDefault();
        inputRef.current?.focus();
        setOpen(true);
      }
      if (e.key === 'Escape') { setOpen(false); setQuery(''); }
    };
    document.addEventListener('keydown', handler);
    return () => document.removeEventListener('keydown', handler);
  }, []);

  const search = useCallback(debounce(async (q) => {
    if (!q.trim() || q.length < 2) { setResults([]); setLoading(false); return; }
    setLoading(true);
    try {
      // Search employees
      const empRes = await fetch(`${BASE}/employees?search=${encodeURIComponent(q)}&limit=5`, {
        headers: { Authorization: `Bearer ${tkn()}` },
      });
      const empData = empRes.ok ? await empRes.json() : { employees: [] };

      // Search pay runs
      const runRes = await fetch(`${BASE}/payroll/history?limit=3`, {
        headers: { Authorization: `Bearer ${tkn()}` },
      });
      const runData = runRes.ok ? await runRes.json() : { runs: [] };

      const combined = [
        ...(empData.employees || []).map(e => ({
          type: 'employee',
          id: e.id,
          title: e.full_name,
          subtitle: `${e.job_title || ''} · ${e.department || ''} · ${e.status}`,
          action: 'employees',
        })),
        ...(runData.runs || []).filter(r =>
          r.id.includes(q) || r.created_at?.includes(q) || r.status?.includes(q.toLowerCase())
        ).slice(0, 2).map(r => ({
          type: 'pay_run',
          id: r.id,
          title: `Pay run ${r.id.slice(0, 8)}…`,
          subtitle: `${r.employee_count} employees · $${Number(r.total_net || 0).toLocaleString()} net · ${r.status}`,
          action: 'history',
        })),
      ];
      setResults(combined);
    } catch {
      setResults([]);
    }
    setLoading(false);
  }, 250), []);

  const handleChange = (e) => {
    const v = e.target.value;
    setQuery(v);
    setSelected(-1);
    if (v.length >= 2) { setLoading(true); setOpen(true); }
    else { setResults([]); }
    search(v);
  };

  const handleKeyDown = (e) => {
    if (!open || results.length === 0) return;
    if (e.key === 'ArrowDown') { e.preventDefault(); setSelected(s => Math.min(s + 1, results.length - 1)); }
    if (e.key === 'ArrowUp') { e.preventDefault(); setSelected(s => Math.max(s - 1, 0)); }
    if (e.key === 'Enter' && selected >= 0) {
      const r = results[selected];
      onNavigate?.(r.action);
      setOpen(false); setQuery('');
    }
  };

  const handleSelect = (r) => {
    onNavigate?.(r.action);
    setOpen(false);
    setQuery('');
  };

  // Quick action shortcuts
  const QUICK_ACTIONS = [
    { icon: '▶', label: 'Run payroll', action: 'run-payroll' },
    { icon: '◉', label: 'Add employee', action: 'employees' },
    { icon: '◷', label: 'Payroll history', action: 'history' },
    { icon: '✓', label: 'Compliance check', action: 'compliance' },
  ];

  return (
    <div ref={ref} style={{ position: 'relative', flex: 1, maxWidth: 400 }}>
      <div style={{ position: 'relative' }}>
        <span style={{ position: 'absolute', left: 10, top: '50%', transform: 'translateY(-50%)', color: 'var(--text3)', fontSize: 13, pointerEvents: 'none' }}>⌕</span>
        <input
          ref={inputRef}
          type="text"
          value={query}
          onChange={handleChange}
          onKeyDown={handleKeyDown}
          onFocus={() => { setOpen(true); }}
          placeholder="Search employees, runs… (⌘K)"
          style={{
            width: '100%', padding: '7px 10px 7px 30px',
            border: '1px solid var(--border)', borderRadius: 8,
            fontSize: 13, background: 'var(--bg2)', color: 'var(--text)',
            fontFamily: 'inherit',
          }}
        />
        {loading && (
          <span style={{ position: 'absolute', right: 10, top: '50%', transform: 'translateY(-50%)', color: 'var(--text3)', fontSize: 11 }}>…</span>
        )}
      </div>

      {open && (
        <div style={{
          position: 'absolute', top: 'calc(100% + 6px)', left: 0, right: 0,
          background: 'var(--bg)', border: '1px solid var(--border)', borderRadius: 10,
          boxShadow: '0 8px 24px rgba(0,0,0,0.12)', zIndex: 999, overflow: 'hidden',
        }}>
          {/* Results */}
          {results.length > 0 && results.map((r, i) => (
            <div
              key={r.id}
              onClick={() => handleSelect(r)}
              style={{
                padding: '10px 14px', display: 'flex', gap: 10, alignItems: 'center',
                cursor: 'pointer', borderBottom: '1px solid var(--border)',
                background: selected === i ? 'var(--blue-bg)' : 'transparent',
                transition: 'background 0.1s',
              }}
              onMouseEnter={() => setSelected(i)}
            >
              <span style={{
                width: 28, height: 28, borderRadius: 6, background: `var(--${RESULT_COLORS[r.type]}-bg)`,
                color: `var(--${RESULT_COLORS[r.type]})`, display: 'flex', alignItems: 'center',
                justifyContent: 'center', fontSize: 13, flexShrink: 0,
              }}>
                {RESULT_ICONS[r.type] || 'ℹ'}
              </span>
              <div style={{ flex: 1, minWidth: 0 }}>
                <div style={{ fontWeight: 500, fontSize: 13 }}>{r.title}</div>
                <div style={{ fontSize: 11, color: 'var(--text3)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{r.subtitle}</div>
              </div>
              <span style={{ fontSize: 11, color: 'var(--text3)' }}>{r.type.replace('_', ' ')}</span>
            </div>
          ))}

          {/* No results */}
          {query.length >= 2 && !loading && results.length === 0 && (
            <div style={{ padding: '16px 14px', fontSize: 13, color: 'var(--text3)', textAlign: 'center' }}>
              No results for "{query}"
            </div>
          )}

          {/* Quick actions (shown when empty) */}
          {query.length < 2 && (
            <div>
              <div style={{ padding: '8px 14px 4px', fontSize: 11, color: 'var(--text3)', fontWeight: 500, textTransform: 'uppercase', letterSpacing: '0.06em' }}>Quick actions</div>
              {QUICK_ACTIONS.map(a => (
                <div
                  key={a.action}
                  onClick={() => { onNavigate?.(a.action); setOpen(false); }}
                  style={{ padding: '8px 14px', display: 'flex', gap: 10, alignItems: 'center', cursor: 'pointer', transition: 'background 0.1s' }}
                  onMouseEnter={e => e.currentTarget.style.background = 'var(--bg2)'}
                  onMouseLeave={e => e.currentTarget.style.background = 'transparent'}
                >
                  <span style={{ width: 28, height: 28, borderRadius: 6, background: 'var(--bg3)', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 13, color: 'var(--text2)' }}>{a.icon}</span>
                  <span style={{ fontSize: 13 }}>{a.label}</span>
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
