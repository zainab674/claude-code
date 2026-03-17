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

function ProgressBar({ pct, color = 'var(--blue)' }) {
  return (
    <div style={{ height: 6, background: 'var(--bg3)', borderRadius: 99, overflow: 'hidden' }}>
      <div style={{ height: '100%', width: `${pct}%`, background: pct === 100 ? 'var(--green)' : color, borderRadius: 99, transition: 'width 0.4s' }} />
    </div>
  );
}

export default function Onboarding() {
  const [pending, setPending] = useState([]);
  const [employees, setEmployees] = useState([]);
  const [selected, setSelected] = useState(null);
  const [checklist, setChecklist] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  const load = async () => {
    setLoading(true);
    try {
      const [p, e] = await Promise.all([req('/onboarding/pending'), req('/employees?status=active')]);
      setPending(p || []);
      setEmployees(e.employees || []);
    } catch (err) { setError(err.message); }
    setLoading(false);
  };

  useEffect(() => { load(); }, []);

  const viewEmployee = async (empId) => {
    setSelected(empId);
    try {
      const data = await req(`/onboarding/employees/${empId}`);
      setChecklist(data);
    } catch (err) { setError(err.message); }
  };

  const initialize = async (empId) => {
    try { await req(`/onboarding/employees/${empId}/initialize`, { method: 'POST' }); viewEmployee(empId); load(); }
    catch (err) { setError(err.message); }
  };

  const toggleTask = async (taskId, completed) => {
    try {
      const endpoint = completed ? `/onboarding/tasks/${taskId}/uncomplete` : `/onboarding/tasks/${taskId}/complete`;
      await req(endpoint, { method: 'PUT', body: JSON.stringify({ completed_by: '' }) });
      viewEmployee(selected);
    } catch (err) { setError(err.message); }
  };

  const empMap = Object.fromEntries(employees.map(e => [e.id, e]));

  return (
    <div className="page">
      <div className="page-header"><h1>Onboarding</h1></div>
      {error && <div className="alert alert-danger">{error}</div>}

      <div className="two-col">
        <div>
          {/* Pending onboarding */}
          <div className="card" style={{ marginBottom: 16 }}>
            <div className="card-header">
              <h3>In progress <span className="count-badge">{pending.length}</span></h3>
            </div>
            {loading && <div style={{ padding: 24, textAlign: 'center', color: 'var(--text3)' }}>Loading…</div>}
            {!loading && pending.length === 0 && (
              <div style={{ padding: 24, textAlign: 'center', color: 'var(--text3)', fontSize: 13 }}>
                All employees fully onboarded ✓
              </div>
            )}
            {pending.map(p => {
              const emp = empMap[p.employee_id];
              return (
                <div
                  key={p.employee_id}
                  onClick={() => viewEmployee(p.employee_id)}
                  style={{
                    padding: '12px 16px', borderBottom: '1px solid var(--border)',
                    cursor: 'pointer', background: selected === p.employee_id ? 'var(--blue-bg)' : 'transparent',
                  }}
                >
                  <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 6 }}>
                    <span style={{ fontWeight: 500 }}>{emp?.full_name || p.employee_id.slice(0, 8)}</span>
                    <span style={{ fontSize: 12, color: 'var(--text3)' }}>{p.progress_pct}%</span>
                  </div>
                  <ProgressBar pct={p.progress_pct} />
                  <div style={{ fontSize: 11, color: 'var(--text3)', marginTop: 4 }}>
                    {p.completed}/{p.total} tasks · {p.remaining} remaining
                  </div>
                </div>
              );
            })}
          </div>

          {/* Start onboarding for new employee */}
          <div className="card">
            <div className="card-header"><h3>Start onboarding</h3></div>
            <div style={{ padding: 16 }}>
              <p style={{ fontSize: 13, color: 'var(--text2)', marginBottom: 12 }}>
                Select a new employee to create their onboarding checklist.
              </p>
              <div className="form-group">
                <select onChange={e => e.target.value && initialize(e.target.value)} defaultValue="">
                  <option value="">Select employee…</option>
                  {employees
                    .filter(e => !pending.find(p => p.employee_id === e.id))
                    .map(e => <option key={e.id} value={e.id}>{e.full_name}</option>)}
                </select>
              </div>
            </div>
          </div>
        </div>

        {/* Checklist panel */}
        <div>
          {!selected && (
            <div className="card" style={{ padding: 32, textAlign: 'center', color: 'var(--text3)' }}>
              ← Select an employee to view their checklist
            </div>
          )}
          {selected && checklist && (
            <div className="card">
              <div className="card-header">
                <div>
                  <h3>{empMap[selected]?.full_name || 'Employee'}</h3>
                  <div style={{ fontSize: 12, color: 'var(--text3)', marginTop: 2 }}>
                    {checklist.completed}/{checklist.total} tasks · {checklist.progress_pct}% complete
                  </div>
                </div>
                {checklist.complete && <span className="badge badge-success">✓ Complete</span>}
              </div>
              <div style={{ padding: '8px 0 16px' }}>
                <div style={{ padding: '0 16px 12px' }}>
                  <ProgressBar pct={checklist.progress_pct} />
                </div>
                {checklist.categories?.map(cat => (
                  <div key={cat.category}>
                    <div style={{ padding: '8px 16px 4px', fontSize: 11, fontWeight: 500, color: 'var(--text3)', textTransform: 'uppercase', letterSpacing: '0.06em' }}>
                      {cat.category}
                    </div>
                    {cat.tasks.map(task => (
                      <div
                        key={task.id}
                        onClick={() => toggleTask(task.id, task.completed)}
                        style={{
                          display: 'flex', alignItems: 'flex-start', gap: 10,
                          padding: '8px 16px', cursor: 'pointer',
                          opacity: task.completed ? 0.6 : 1,
                          borderBottom: '1px solid var(--border)',
                        }}
                      >
                        <div style={{
                          width: 18, height: 18, borderRadius: 4, flexShrink: 0, marginTop: 1,
                          border: `1.5px solid ${task.completed ? 'var(--green)' : 'var(--border2)'}`,
                          background: task.completed ? 'var(--green)' : 'transparent',
                          display: 'flex', alignItems: 'center', justifyContent: 'center',
                          color: 'white', fontSize: 11,
                        }}>
                          {task.completed ? '✓' : ''}
                        </div>
                        <div style={{ flex: 1 }}>
                          <div style={{ fontSize: 13, textDecoration: task.completed ? 'line-through' : 'none' }}>
                            {task.title}
                          </div>
                          {task.completed_at && (
                            <div style={{ fontSize: 11, color: 'var(--text3)' }}>
                              Done {new Date(task.completed_at).toLocaleDateString()}
                              {task.completed_by && ` by ${task.completed_by}`}
                            </div>
                          )}
                          {!task.completed && (
                            <div style={{ fontSize: 11, color: 'var(--amber)' }}>Due within {task.due_days} days</div>
                          )}
                        </div>
                        {task.is_required && !task.completed && (
                          <span className="badge badge-warning" style={{ fontSize: 9 }}>required</span>
                        )}
                      </div>
                    ))}
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
