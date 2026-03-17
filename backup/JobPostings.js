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

const fmt = n => n ? `$${Number(n).toLocaleString()}` : '—';
const STATUS_COLOR = { draft: 'warning', open: 'success', closed: 'danger', filled: 'info' };
const STAGE_COLOR = {
  applied: '#6b7280', screening: '#3b82f6', phone_screen: '#8b5cf6',
  interview: '#f59e0b', technical: '#ef4444', offer: '#10b981',
  hired: '#059669', rejected: '#dc2626', withdrawn: '#9ca3af',
};
const STAGES = ['applied','screening','phone_screen','interview','technical','offer','hired','rejected'];

export default function JobPostings() {
  const [tab, setTab] = useState('board');
  const [jobs, setJobs] = useState([]);
  const [dashboard, setDashboard] = useState(null);
  const [selectedJob, setSelectedJob] = useState(null);
  const [candidates, setCandidates] = useState([]);
  const [selectedCandidate, setSelectedCandidate] = useState(null);
  const [notes, setNotes] = useState([]);
  const [showJobForm, setShowJobForm] = useState(false);
  const [showCandForm, setShowCandForm] = useState(false);
  const [jobForm, setJobForm] = useState({ title: '', department: '', location: '', work_mode: 'hybrid', job_type: 'full_time', salary_min: '', salary_max: '', description: '', requirements: '', headcount: 1 });
  const [candForm, setCandForm] = useState({ first_name: '', last_name: '', email: '', phone: '', source: 'direct', notes: '' });
  const [newNote, setNewNote] = useState('');
  const [error, setError] = useState('');

  const load = async () => {
    const [j, d] = await Promise.all([req('/jobs'), req('/ats/dashboard')]);
    setJobs(j || []);
    setDashboard(d);
  };
  useEffect(() => { load(); }, []);

  const loadCandidates = async (jobId) => {
    setSelectedJob(jobId);
    setSelectedCandidate(null);
    const c = await req(`/jobs/${jobId}/candidates`);
    setCandidates(c || []);
  };

  const loadNotes = async (candId) => {
    setSelectedCandidate(candId);
    const n = await req(`/candidates/${candId}/notes`);
    setNotes(n || []);
  };

  const saveJob = async (e) => {
    e.preventDefault(); setError('');
    try {
      const body = { ...jobForm, salary_min: jobForm.salary_min ? Number(jobForm.salary_min) : null, salary_max: jobForm.salary_max ? Number(jobForm.salary_max) : null };
      await req('/jobs', { method: 'POST', body: JSON.stringify(body) });
      setShowJobForm(false);
      setJobForm({ title: '', department: '', location: '', work_mode: 'hybrid', job_type: 'full_time', salary_min: '', salary_max: '', description: '', requirements: '', headcount: 1 });
      load();
    } catch (err) { setError(err.message); }
  };

  const saveCandidate = async (e) => {
    e.preventDefault(); setError('');
    try {
      await req(`/jobs/${selectedJob}/candidates`, { method: 'POST', body: JSON.stringify(candForm) });
      setShowCandForm(false);
      setCandForm({ first_name: '', last_name: '', email: '', phone: '', source: 'direct', notes: '' });
      loadCandidates(selectedJob);
    } catch (err) { setError(err.message); }
  };

  const moveStage = async (candId, stage) => {
    try { await req(`/candidates/${candId}/stage`, { method: 'PUT', body: JSON.stringify({ stage }) }); loadCandidates(selectedJob); }
    catch (err) { setError(err.message); }
  };

  const publishJob = async (id) => {
    try { await req(`/jobs/${id}/publish`, { method: 'PUT' }); load(); }
    catch (err) { setError(err.message); }
  };

  const addNote = async () => {
    if (!newNote.trim()) return;
    try { await req(`/candidates/${selectedCandidate}/notes`, { method: 'POST', body: JSON.stringify({ content: newNote }) }); setNewNote(''); loadNotes(selectedCandidate); }
    catch (err) { setError(err.message); }
  };

  const openJobs = jobs.filter(j => j.status === 'open');
  const candByStage = STAGES.reduce((acc, s) => ({ ...acc, [s]: candidates.filter(c => c.stage === s) }), {});

  return (
    <div className="page">
      <div className="page-header">
        <h1>Recruiting <span className="count-badge">{openJobs.length} open</span></h1>
        <div style={{ display: 'flex', gap: 8 }}>
          <div className="tab-bar" style={{ margin: 0 }}>
            {[['board','Pipeline'],['jobs','Jobs'],['dashboard','Stats']].map(([id, label]) => (
              <button key={id} className={`tab-btn ${tab === id ? 'active' : ''}`} onClick={() => setTab(id)}>{label}</button>
            ))}
          </div>
          <button className="btn btn-primary" onClick={() => setShowJobForm(!showJobForm)}>+ New job</button>
        </div>
      </div>
      {error && <div className="alert alert-danger">{error}</div>}

      {/* New job form */}
      {showJobForm && (
        <div className="card" style={{ marginBottom: 16 }}>
          <div className="card-header"><h3>New job posting</h3><button className="btn btn-sm" onClick={() => setShowJobForm(false)}>Cancel</button></div>
          <form onSubmit={saveJob} style={{ padding: 16 }}>
            <div className="form-grid">
              <div className="form-group" style={{ gridColumn: '1/-1' }}><label>Job title *</label><input type="text" value={jobForm.title} onChange={e => setJobForm(f => ({ ...f, title: e.target.value }))} required /></div>
              <div className="form-group"><label>Department</label><input type="text" value={jobForm.department} onChange={e => setJobForm(f => ({ ...f, department: e.target.value }))} /></div>
              <div className="form-group"><label>Location</label><input type="text" value={jobForm.location} onChange={e => setJobForm(f => ({ ...f, location: e.target.value }))} placeholder="New York, NY" /></div>
              <div className="form-group"><label>Work mode</label><select value={jobForm.work_mode} onChange={e => setJobForm(f => ({ ...f, work_mode: e.target.value }))}><option value="onsite">Onsite</option><option value="remote">Remote</option><option value="hybrid">Hybrid</option></select></div>
              <div className="form-group"><label>Type</label><select value={jobForm.job_type} onChange={e => setJobForm(f => ({ ...f, job_type: e.target.value }))}><option value="full_time">Full-time</option><option value="part_time">Part-time</option><option value="contract">Contract</option><option value="internship">Internship</option></select></div>
              <div className="form-group"><label>Salary min ($)</label><input type="number" value={jobForm.salary_min} onChange={e => setJobForm(f => ({ ...f, salary_min: e.target.value }))} /></div>
              <div className="form-group"><label>Salary max ($)</label><input type="number" value={jobForm.salary_max} onChange={e => setJobForm(f => ({ ...f, salary_max: e.target.value }))} /></div>
              <div className="form-group"><label>Headcount</label><input type="number" min="1" value={jobForm.headcount} onChange={e => setJobForm(f => ({ ...f, headcount: Number(e.target.value) }))} /></div>
              <div className="form-group" style={{ gridColumn: '1/-1' }}><label>Description</label><textarea style={{ width: '100%', minHeight: 80, padding: '8px 10px', border: '1px solid var(--border2)', borderRadius: 6, fontFamily: 'inherit', fontSize: 13, color: 'var(--text)', background: 'var(--bg)' }} value={jobForm.description} onChange={e => setJobForm(f => ({ ...f, description: e.target.value }))} /></div>
            </div>
            <div style={{ display: 'flex', gap: 8 }}>
              <button className="btn btn-primary" type="submit">Save draft</button>
            </div>
          </form>
        </div>
      )}

      {/* ── PIPELINE BOARD ─── */}
      {tab === 'board' && (
        <div>
          {!selectedJob ? (
            <div>
              <div style={{ marginBottom: 12, fontSize: 13, color: 'var(--text3)' }}>Select a job to view its pipeline</div>
              <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>
                {openJobs.map(j => (
                  <button key={j.id} onClick={() => loadCandidates(j.id)}
                    className={`btn ${selectedJob === j.id ? 'btn-primary' : ''}`}
                    style={{ fontSize: 13 }}>
                    {j.title} <span className="count-badge">{j.candidate_count}</span>
                  </button>
                ))}
                {openJobs.length === 0 && <div style={{ color: 'var(--text3)', fontSize: 13 }}>No open jobs — publish a job first</div>}
              </div>
            </div>
          ) : (
            <>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 }}>
                <button className="btn btn-sm" onClick={() => { setSelectedJob(null); setSelectedCandidate(null); }}>← All jobs</button>
                <button className="btn btn-sm btn-primary" onClick={() => setShowCandForm(!showCandForm)}>+ Add candidate</button>
              </div>
              {showCandForm && (
                <div className="card" style={{ marginBottom: 12 }}>
                  <form onSubmit={saveCandidate} style={{ padding: 16 }}>
                    <div className="form-grid">
                      <div className="form-group"><label>First name *</label><input type="text" value={candForm.first_name} onChange={e => setCandForm(f => ({ ...f, first_name: e.target.value }))} required /></div>
                      <div className="form-group"><label>Last name *</label><input type="text" value={candForm.last_name} onChange={e => setCandForm(f => ({ ...f, last_name: e.target.value }))} required /></div>
                      <div className="form-group"><label>Email *</label><input type="email" value={candForm.email} onChange={e => setCandForm(f => ({ ...f, email: e.target.value }))} required /></div>
                      <div className="form-group"><label>Phone</label><input type="text" value={candForm.phone} onChange={e => setCandForm(f => ({ ...f, phone: e.target.value }))} /></div>
                      <div className="form-group"><label>Source</label><select value={candForm.source} onChange={e => setCandForm(f => ({ ...f, source: e.target.value }))}>{['direct','linkedin','referral','job_board','agency'].map(s => <option key={s} value={s}>{s}</option>)}</select></div>
                    </div>
                    <div style={{ display: 'flex', gap: 8 }}>
                      <button className="btn btn-primary btn-sm" type="submit">Add</button>
                      <button className="btn btn-sm" type="button" onClick={() => setShowCandForm(false)}>Cancel</button>
                    </div>
                  </form>
                </div>
              )}
              {/* Kanban board */}
              <div style={{ display: 'flex', gap: 8, overflowX: 'auto', paddingBottom: 8 }}>
                {STAGES.map(stage => (
                  <div key={stage} style={{ minWidth: 180, flex: '0 0 180px' }}>
                    <div style={{ padding: '6px 8px', borderRadius: '6px 6px 0 0', background: STAGE_COLOR[stage] + '22', borderBottom: `2px solid ${STAGE_COLOR[stage]}`, marginBottom: 6 }}>
                      <span style={{ fontSize: 11, fontWeight: 600, textTransform: 'uppercase', color: STAGE_COLOR[stage] }}>{stage.replace('_', ' ')}</span>
                      <span style={{ fontSize: 11, marginLeft: 4, color: 'var(--text3)' }}>{candByStage[stage]?.length || 0}</span>
                    </div>
                    {(candByStage[stage] || []).map(c => (
                      <div key={c.id}
                        onClick={() => { setSelectedCandidate(c.id); loadNotes(c.id); }}
                        style={{
                          background: 'var(--bg2)', border: `1px solid ${selectedCandidate === c.id ? STAGE_COLOR[stage] : 'var(--border)'}`,
                          borderRadius: 8, padding: '8px 10px', marginBottom: 6, cursor: 'pointer',
                          fontSize: 12,
                        }}>
                        <div style={{ fontWeight: 500 }}>{c.name}</div>
                        <div style={{ color: 'var(--text3)', fontSize: 11 }}>{c.source}</div>
                        {c.rating && <div style={{ color: 'var(--amber)' }}>{'★'.repeat(c.rating)}</div>}
                        <div style={{ marginTop: 6, display: 'flex', flexWrap: 'wrap', gap: 3 }}>
                          {STAGES.filter(s => s !== stage && !['hired','rejected','withdrawn'].includes(s)).slice(0,2).map(s => (
                            <button key={s} onClick={ev => { ev.stopPropagation(); moveStage(c.id, s); }}
                              style={{ fontSize: 9, padding: '1px 5px', border: '1px solid var(--border)', borderRadius: 4, background: 'none', cursor: 'pointer', color: 'var(--text3)' }}>
                              → {s.replace('_',' ')}
                            </button>
                          ))}
                        </div>
                      </div>
                    ))}
                  </div>
                ))}
              </div>
              {/* Notes panel */}
              {selectedCandidate && (
                <div className="card" style={{ marginTop: 16 }}>
                  <div className="card-header"><h3>Hiring notes</h3></div>
                  <div style={{ padding: 16 }}>
                    <div style={{ display: 'flex', gap: 8, marginBottom: 12 }}>
                      <input type="text" value={newNote} onChange={e => setNewNote(e.target.value)} placeholder="Add a note…" style={{ flex: 1 }} onKeyDown={e => e.key === 'Enter' && addNote()} />
                      <button className="btn btn-primary btn-sm" onClick={addNote}>Add</button>
                    </div>
                    {notes.map(n => (
                      <div key={n.id} style={{ padding: '8px 0', borderBottom: '1px solid var(--border)', fontSize: 13 }}>
                        <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                          <span style={{ fontWeight: 500 }}>{n.author}</span>
                          <span style={{ fontSize: 11, color: 'var(--text3)' }}>{new Date(n.created_at).toLocaleDateString()}</span>
                        </div>
                        <div style={{ marginTop: 4, color: 'var(--text2)' }}>{n.content}</div>
                      </div>
                    ))}
                    {notes.length === 0 && <div style={{ color: 'var(--text3)', fontSize: 13 }}>No notes yet</div>}
                  </div>
                </div>
              )}
            </>
          )}
        </div>
      )}

      {/* ── JOBS LIST ─── */}
      {tab === 'jobs' && (
        <div className="card">
          <table className="table">
            <thead><tr><th>Title</th><th>Dept</th><th>Type</th><th>Salary</th><th>Candidates</th><th>Status</th><th></th></tr></thead>
            <tbody>
              {jobs.length === 0 && <tr><td colSpan={7} className="empty">No job postings yet</td></tr>}
              {jobs.map(j => (
                <tr key={j.id}>
                  <td style={{ fontWeight: 500 }}>{j.title}</td>
                  <td style={{ color: 'var(--text3)' }}>{j.department || '—'}</td>
                  <td><span className="badge badge-info">{j.job_type?.replace('_',' ')}</span></td>
                  <td style={{ fontSize: 12 }}>{j.salary_range || '—'}</td>
                  <td><span className="count-badge">{j.candidate_count}</span></td>
                  <td><span className={`badge badge-${STATUS_COLOR[j.status]}`}>{j.status}</span></td>
                  <td>
                    {j.status === 'draft' && <button className="btn btn-sm btn-primary" onClick={() => publishJob(j.id)}>Publish</button>}
                    {j.status === 'open' && <button className="btn btn-sm" onClick={() => { loadCandidates(j.id); setTab('board'); }}>View pipeline</button>}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* ── DASHBOARD ─── */}
      {tab === 'dashboard' && dashboard && (
        <>
          <div className="metrics-grid" style={{ gridTemplateColumns: 'repeat(4,1fr)', marginBottom: 16 }}>
            <div className="metric-card"><div className="metric-label">Open roles</div><div className="metric-value">{dashboard.jobs.open}</div></div>
            <div className="metric-card"><div className="metric-label">Total candidates</div><div className="metric-value">{dashboard.pipeline.total_candidates}</div></div>
            <div className="metric-card"><div className="metric-label">Hired this year</div><div className="metric-value" style={{ color: 'var(--green)' }}>{dashboard.hired_this_year}</div></div>
            <div className="metric-card"><div className="metric-label">Offer acceptance</div><div className="metric-value">{dashboard.offer_acceptance_rate}%</div></div>
          </div>
          <div className="card">
            <div className="card-header"><h3>Pipeline funnel</h3></div>
            <div style={{ padding: 16 }}>
              {dashboard.pipeline.by_stage.map(s => (
                <div key={s.stage} style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 8 }}>
                  <div style={{ width: 100, fontSize: 12, color: 'var(--text2)', textTransform: 'capitalize' }}>{s.stage.replace('_',' ')}</div>
                  <div style={{ flex: 1, height: 18, background: 'var(--bg3)', borderRadius: 4, overflow: 'hidden' }}>
                    <div style={{ height: '100%', width: `${s.pct}%`, background: STAGE_COLOR[s.stage], borderRadius: 4, transition: 'width 0.4s', minWidth: s.count > 0 ? 4 : 0 }} />
                  </div>
                  <div style={{ width: 50, textAlign: 'right', fontSize: 12, fontWeight: 500 }}>{s.count}</div>
                </div>
              ))}
            </div>
          </div>
        </>
      )}
    </div>
  );
}
