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

const RATING_LABELS = { 1: 'Needs Improvement', 2: 'Below Expectations', 3: 'Meets Expectations', 4: 'Exceeds Expectations', 5: 'Outstanding' };
const STATUS_COLOR = { pending: 'warning', in_progress: 'info', submitted: 'success', acknowledged: 'success', draft: 'warning', active: 'info', completed: 'success' };

function StarRating({ value, onChange }) {
  return (
    <div style={{ display: 'flex', gap: 4 }}>
      {[1,2,3,4,5].map(star => (
        <button key={star} type="button" onClick={() => onChange(star)}
          style={{ background: 'none', border: 'none', cursor: 'pointer', fontSize: 22,
                   color: star <= value ? 'var(--amber)' : 'var(--border2)' }}>
          ★
        </button>
      ))}
      {value > 0 && <span style={{ fontSize: 12, color: 'var(--text3)', alignSelf: 'center' }}>{RATING_LABELS[Math.round(value)]}</span>}
    </div>
  );
}

export default function PerformancePage() {
  const [tab, setTab] = useState('cycles');
  const [cycles, setCycles] = useState([]);
  const [reviews, setReviews] = useState([]);
  const [goals, setGoals] = useState([]);
  const [employees, setEmployees] = useState([]);
  const [selected, setSelected] = useState(null);
  const [showCycleForm, setShowCycleForm] = useState(false);
  const [cycleForm, setCycleForm] = useState({ name: '', cycle_type: 'annual', review_period_start: '', review_period_end: '', due_date: '', include_self_review: true });
  const [editReview, setEditReview] = useState(null);
  const [error, setError] = useState('');

  const load = async () => {
    const [c, g, e] = await Promise.all([req('/performance/cycles'), req('/performance/goals'), req('/employees?status=active')]);
    setCycles(c || []); setGoals(g || []); setEmployees(e?.employees || []);
  };
  useEffect(() => { load(); }, []);

  const loadReviews = async (cycleId) => {
    setSelected(cycleId);
    setReviews(await req(`/performance/reviews?cycle_id=${cycleId}`) || []);
  };

  const saveCycle = async (e) => {
    e.preventDefault(); setError('');
    try { await req('/performance/cycles', { method: 'POST', body: JSON.stringify(cycleForm) }); setShowCycleForm(false); load(); }
    catch (err) { setError(err.message); }
  };

  const launch = async (id) => {
    try { const r = await req(`/performance/cycles/${id}/launch`, { method: 'POST' }); alert(r.message); load(); if (selected === id) loadReviews(id); }
    catch (err) { setError(err.message); }
  };

  const submitReview = async (reviewId, updates) => {
    try {
      await req(`/performance/reviews/${reviewId}`, { method: 'PUT', body: JSON.stringify(updates) });
      await req(`/performance/reviews/${reviewId}/submit`, { method: 'POST' });
      setEditReview(null);
      loadReviews(selected);
    } catch (err) { setError(err.message); }
  };

  const empMap = Object.fromEntries(employees.map(e => [e.id, e.full_name]));

  return (
    <div className="page">
      <div className="page-header">
        <h1>Performance Reviews</h1>
        <button className="btn btn-primary" onClick={() => setShowCycleForm(!showCycleForm)}>+ New cycle</button>
      </div>
      {error && <div className="alert alert-danger">{error}</div>}

      <div className="tab-bar">
        {[['cycles','Review Cycles'],['goals','Goals']].map(([id, label]) => (
          <button key={id} className={`tab-btn ${tab === id ? 'active' : ''}`} onClick={() => { setTab(id); setSelected(null); }}>{label}</button>
        ))}
      </div>

      {showCycleForm && (
        <div className="card" style={{ marginBottom: 16 }}>
          <div className="card-header"><h3>New review cycle</h3><button className="btn btn-sm" onClick={() => setShowCycleForm(false)}>Cancel</button></div>
          <form onSubmit={saveCycle} style={{ padding: 16 }}>
            <div className="form-grid">
              <div className="form-group"><label>Name *</label><input type="text" value={cycleForm.name} onChange={e => setCycleForm(f => ({ ...f, name: e.target.value }))} placeholder="2026 Annual Review" required /></div>
              <div className="form-group"><label>Type</label>
                <select value={cycleForm.cycle_type} onChange={e => setCycleForm(f => ({ ...f, cycle_type: e.target.value }))}>
                  {['annual','quarterly','90day','pip'].map(t => <option key={t} value={t}>{t}</option>)}
                </select>
              </div>
              <div className="form-group"><label>Period start</label><input type="date" value={cycleForm.review_period_start} onChange={e => setCycleForm(f => ({ ...f, review_period_start: e.target.value }))} /></div>
              <div className="form-group"><label>Period end</label><input type="date" value={cycleForm.review_period_end} onChange={e => setCycleForm(f => ({ ...f, review_period_end: e.target.value }))} /></div>
              <div className="form-group"><label>Due date</label><input type="date" value={cycleForm.due_date} onChange={e => setCycleForm(f => ({ ...f, due_date: e.target.value }))} /></div>
              <div className="form-group" style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                <input type="checkbox" id="selfreview" checked={cycleForm.include_self_review} onChange={e => setCycleForm(f => ({ ...f, include_self_review: e.target.checked }))} style={{ width: 'auto' }} />
                <label htmlFor="selfreview" style={{ cursor: 'pointer' }}>Include self-review</label>
              </div>
            </div>
            <button className="btn btn-primary" type="submit">Create cycle</button>
          </form>
        </div>
      )}

      {tab === 'cycles' && (
        <div className="two-col">
          <div className="card">
            {cycles.length === 0 && <div style={{ padding: 32, textAlign: 'center', color: 'var(--text3)' }}>No review cycles yet</div>}
            {cycles.map(c => (
              <div key={c.id} onClick={() => c.status !== 'draft' && loadReviews(c.id)}
                style={{ padding: '12px 16px', borderBottom: '1px solid var(--border)', cursor: c.status !== 'draft' ? 'pointer' : 'default', background: selected === c.id ? 'var(--blue-bg)' : '' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                  <div>
                    <div style={{ fontWeight: 500 }}>{c.name}</div>
                    <div style={{ fontSize: 12, color: 'var(--text3)' }}>{c.cycle_type}{c.due_date ? ` · Due ${c.due_date}` : ''}</div>
                  </div>
                  <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
                    <span className={`badge badge-${STATUS_COLOR[c.status]}`}>{c.status}</span>
                    {c.status === 'draft' && <button className="btn btn-sm btn-primary" onClick={(e) => { e.stopPropagation(); launch(c.id); }}>▶ Launch</button>}
                  </div>
                </div>
              </div>
            ))}
          </div>

          <div>
            {!selected && <div className="card" style={{ padding: 32, textAlign: 'center', color: 'var(--text3)' }}>← Select an active cycle to view reviews</div>}
            {selected && (
              <div className="card">
                <div className="card-header"><h3>Reviews ({reviews.length})</h3></div>
                {reviews.map(r => (
                  <div key={r.id} style={{ padding: '10px 16px', borderBottom: '1px solid var(--border)' }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                      <div>
                        <div style={{ fontWeight: 500 }}>{empMap[r.employee_id] || r.employee_id.slice(0,8)}</div>
                        <div style={{ fontSize: 12, color: 'var(--text3)' }}>{r.review_type} review{r.overall_rating ? ` · ${r.overall_rating}/5` : ''}</div>
                      </div>
                      <div style={{ display: 'flex', gap: 6, alignItems: 'center' }}>
                        <span className={`badge badge-${STATUS_COLOR[r.status]}`}>{r.status}</span>
                        {r.status === 'pending' || r.status === 'in_progress' ? (
                          <button className="btn btn-sm" onClick={() => setEditReview(r)}>Fill out</button>
                        ) : null}
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      )}

      {tab === 'goals' && (
        <div className="card">
          <table className="table">
            <thead><tr><th>Employee</th><th>Goal</th><th>Category</th><th>Due</th><th>Progress</th><th>Status</th></tr></thead>
            <tbody>
              {goals.length === 0 && <tr><td colSpan={6} className="empty">No goals yet</td></tr>}
              {goals.map(g => (
                <tr key={g.id}>
                  <td style={{ fontWeight: 500 }}>{empMap[g.employee_id] || '—'}</td>
                  <td>{g.title}</td>
                  <td><span className="badge badge-info">{g.category}</span></td>
                  <td style={{ fontSize: 12, color: 'var(--text3)' }}>{g.due_date || '—'}</td>
                  <td>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                      <div style={{ flex: 1, height: 6, background: 'var(--bg3)', borderRadius: 99, overflow: 'hidden', minWidth: 60 }}>
                        <div style={{ height: '100%', width: `${g.progress_pct}%`, background: g.progress_pct === 100 ? 'var(--green)' : 'var(--blue)', borderRadius: 99 }} />
                      </div>
                      <span style={{ fontSize: 11, color: 'var(--text3)', minWidth: 30 }}>{g.progress_pct}%</span>
                    </div>
                  </td>
                  <td><span className={`badge badge-${STATUS_COLOR[g.status]}`}>{g.status}</span></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* Review edit modal */}
      {editReview && (
        <div style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.4)', display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 1000 }}>
          <div style={{ background: 'var(--bg)', borderRadius: 12, padding: 24, maxWidth: 560, width: '90%', maxHeight: '80vh', overflowY: 'auto' }}>
            <ReviewForm review={editReview} empName={empMap[editReview.employee_id]} onSave={submitReview} onClose={() => setEditReview(null)} />
          </div>
        </div>
      )}
    </div>
  );
}

function ReviewForm({ review, empName, onSave, onClose }) {
  const [form, setForm] = useState({
    overall_rating: review.overall_rating || 0,
    strengths: review.strengths || '',
    areas_for_improvement: review.areas_for_improvement || '',
    manager_comments: review.manager_comments || '',
    goals_next_period: review.goals_next_period || '',
    recommended_raise_pct: review.recommended_raise_pct || 0,
    recommended_promotion: review.recommended_promotion || false,
  });
  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 20 }}>
        <div><div style={{ fontWeight: 600, fontSize: 16 }}>{empName}</div><div style={{ fontSize: 12, color: 'var(--text3)' }}>{review.review_type} review</div></div>
        <button className="btn btn-sm" onClick={onClose}>✕</button>
      </div>
      <div className="form-group"><label>Overall rating</label><StarRating value={form.overall_rating} onChange={v => setForm(f => ({ ...f, overall_rating: v }))} /></div>
      <div className="form-group"><label>Strengths</label><textarea style={{ width: '100%', padding: '8px 10px', borderRadius: 6, border: '1px solid var(--border2)', fontSize: 13, fontFamily: 'inherit', minHeight: 80, color: 'var(--text)', background: 'var(--bg)' }} value={form.strengths} onChange={e => setForm(f => ({ ...f, strengths: e.target.value }))} /></div>
      <div className="form-group"><label>Areas for improvement</label><textarea style={{ width: '100%', padding: '8px 10px', borderRadius: 6, border: '1px solid var(--border2)', fontSize: 13, fontFamily: 'inherit', minHeight: 80, color: 'var(--text)', background: 'var(--bg)' }} value={form.areas_for_improvement} onChange={e => setForm(f => ({ ...f, areas_for_improvement: e.target.value }))} /></div>
      <div className="form-group"><label>Comments</label><textarea style={{ width: '100%', padding: '8px 10px', borderRadius: 6, border: '1px solid var(--border2)', fontSize: 13, fontFamily: 'inherit', minHeight: 60, color: 'var(--text)', background: 'var(--bg)' }} value={form.manager_comments} onChange={e => setForm(f => ({ ...f, manager_comments: e.target.value }))} /></div>
      <div className="form-group"><label>Goals for next period</label><textarea style={{ width: '100%', padding: '8px 10px', borderRadius: 6, border: '1px solid var(--border2)', fontSize: 13, fontFamily: 'inherit', minHeight: 60, color: 'var(--text)', background: 'var(--bg)' }} value={form.goals_next_period} onChange={e => setForm(f => ({ ...f, goals_next_period: e.target.value }))} /></div>
      <div className="form-grid">
        <div className="form-group"><label>Recommended raise %</label><input type="number" step="0.1" min="0" max="50" value={form.recommended_raise_pct} onChange={e => setForm(f => ({ ...f, recommended_raise_pct: Number(e.target.value) }))} /></div>
        <div className="form-group" style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <input type="checkbox" id="promo" checked={form.recommended_promotion} onChange={e => setForm(f => ({ ...f, recommended_promotion: e.target.checked }))} style={{ width: 'auto' }} />
          <label htmlFor="promo" style={{ cursor: 'pointer' }}>Recommend for promotion</label>
        </div>
      </div>
      <div style={{ display: 'flex', gap: 8, marginTop: 16 }}>
        <button className="btn btn-primary" onClick={() => onSave(review.id, form)}>Submit review</button>
        <button className="btn" onClick={onClose}>Cancel</button>
      </div>
    </div>
  );
}
