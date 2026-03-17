import React, { useState } from 'react';
import * as api from '../services/api';

const BASE = process.env.REACT_APP_API_URL || 'http://localhost:8000';
const token = () => localStorage.getItem('payroll_token');

function downloadUrl(path) {
  return `${BASE}${path}`;
}

async function downloadWithAuth(path, filename) {
  const res = await fetch(`${BASE}${path}`, {
    headers: { Authorization: `Bearer ${token()}` },
  });
  if (!res.ok) throw new Error('Download failed');
  const blob = await res.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}

export default function ExportImport() {
  const [tab, setTab] = useState('export');
  const year = new Date().getFullYear();

  // Export state
  const [exporting, setExporting] = useState({});
  const [exportError, setExportError] = useState('');

  // Import state
  const [file, setFile] = useState(null);
  const [dryRun, setDryRun] = useState(true);
  const [importing, setImporting] = useState(false);
  const [importResult, setImportResult] = useState(null);
  const [importError, setImportError] = useState('');

  const doExport = async (key, path, filename) => {
    setExporting(e => ({ ...e, [key]: true }));
    setExportError('');
    try {
      await downloadWithAuth(path, filename);
    } catch (e) {
      setExportError(e.message);
    } finally {
      setExporting(e => ({ ...e, [key]: false }));
    }
  };

  const doImport = async () => {
    if (!file) return;
    setImporting(true);
    setImportError('');
    setImportResult(null);
    try {
      const formData = new FormData();
      formData.append('file', file);
      const res = await fetch(`${BASE}/import/employees?dry_run=${dryRun}`, {
        method: 'POST',
        headers: { Authorization: `Bearer ${token()}` },
        body: formData,
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: 'Upload failed' }));
        throw new Error(err.detail);
      }
      const result = await res.json();
      setImportResult(result);
    } catch (e) {
      setImportError(e.message);
    } finally {
      setImporting(false);
    }
  };

  const EXPORTS = [
    {
      key: 'employees',
      label: 'All employees',
      desc: 'Employee roster with pay rates, deductions, tax settings',
      path: '/export/employees',
      filename: 'employees.csv',
      icon: '◉',
    },
    {
      key: 'ytd',
      label: `YTD summary ${year}`,
      desc: 'Per-employee year-to-date earnings and taxes — for W-2 prep',
      path: `/export/employee-ytd?year=${year}`,
      filename: `employee-ytd-${year}.csv`,
      icon: '◈',
    },
    {
      key: 'history',
      label: `Payroll history ${year}`,
      desc: 'All pay runs with gross, taxes, net totals',
      path: `/export/payroll-history?year=${year}`,
      filename: `payroll-history-${year}.csv`,
      icon: '◷',
    },
  ];

  return (
    <div className="page">
      <div className="page-header">
        <h1>Export &amp; Import</h1>
        <div className="tab-bar" style={{ margin: 0 }}>
          {[['export', 'Export CSV'], ['import', 'Import Employees']].map(([id, label]) => (
            <button key={id} className={`tab-btn ${tab === id ? 'active' : ''}`}
              onClick={() => setTab(id)}>{label}</button>
          ))}
        </div>
      </div>

      {/* ── Export tab ─────────────────────────── */}
      {tab === 'export' && (
        <>
          {exportError && <div className="alert alert-danger">{exportError}</div>}
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: 16, marginBottom: 16 }}>
            {EXPORTS.map(exp => (
              <div key={exp.key} className="card" style={{ padding: 0 }}>
                <div style={{ padding: '16px 16px 12px' }}>
                  <div style={{ fontSize: 24, marginBottom: 8 }}>{exp.icon}</div>
                  <div style={{ fontWeight: 500, marginBottom: 4 }}>{exp.label}</div>
                  <div style={{ fontSize: 12, color: 'var(--text3)', lineHeight: 1.5 }}>{exp.desc}</div>
                </div>
                <div style={{ padding: '12px 16px', borderTop: '1px solid var(--border)' }}>
                  <button
                    className="btn btn-primary"
                    style={{ width: '100%' }}
                    disabled={exporting[exp.key]}
                    onClick={() => doExport(exp.key, exp.path, exp.filename)}
                  >
                    {exporting[exp.key] ? 'Downloading…' : '↓ Download CSV'}
                  </button>
                </div>
              </div>
            ))}
          </div>

          <div className="card">
            <div className="card-header"><h3>Export notes</h3></div>
            <div style={{ padding: 16, fontSize: 13, color: 'var(--text2)', lineHeight: 1.8 }}>
              <div>• All exports are UTF-8 CSV files — open in Excel, Google Sheets, or any spreadsheet app.</div>
              <div>• YTD export covers only completed pay runs in the selected year.</div>
              <div>• YTD columns map directly to W-2 Box 1 (wages), Box 2 (federal), Box 4 (SS), Box 6 (Medicare), Box 12 (401k).</div>
              <div>• Pay run detail exports are available via <code style={{ background: 'var(--bg3)', padding: '1px 4px', borderRadius: 3 }}>GET /export/pay-run/{'{id}'}</code> in the API.</div>
            </div>
          </div>
        </>
      )}

      {/* ── Import tab ─────────────────────────── */}
      {tab === 'import' && (
        <>
          {importError && <div className="alert alert-danger">{importError}</div>}

          <div className="two-col">
            <div className="card">
              <div className="card-header"><h3>Upload employee CSV</h3></div>
              <div style={{ padding: 16 }}>
                <p style={{ fontSize: 13, color: 'var(--text2)', marginBottom: 16, lineHeight: 1.6 }}>
                  Upload a CSV file to create multiple employees at once.
                  Use dry run first to validate without saving.
                </p>

                <div style={{ marginBottom: 16 }}>
                  <button
                    className="btn"
                    onClick={() => downloadWithAuth('/import/employees/template', 'employee-import-template.csv')}
                  >
                    ↓ Download template CSV
                  </button>
                </div>

                <div className="form-group">
                  <label>CSV file</label>
                  <input
                    type="file"
                    accept=".csv"
                    onChange={e => { setFile(e.target.files[0]); setImportResult(null); }}
                    style={{ padding: '6px 0', border: 'none' }}
                  />
                </div>

                <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 16 }}>
                  <input
                    type="checkbox"
                    id="dryrun"
                    checked={dryRun}
                    onChange={e => setDryRun(e.target.checked)}
                    style={{ width: 'auto' }}
                  />
                  <label htmlFor="dryrun" style={{ fontSize: 13, cursor: 'pointer' }}>
                    Dry run — validate only, don't save
                  </label>
                </div>

                <button
                  className="btn btn-primary"
                  onClick={doImport}
                  disabled={!file || importing}
                  style={{ width: '100%' }}
                >
                  {importing ? 'Processing…' : dryRun ? '↻ Validate CSV' : '⬆ Import employees'}
                </button>
              </div>
            </div>

            {/* ── Result panel ────────────────── */}
            <div>
              {!importResult && (
                <div className="card" style={{ padding: 32, textAlign: 'center', color: 'var(--text3)' }}>
                  Upload a CSV to see results here
                </div>
              )}
              {importResult && (
                <div className="card">
                  <div className="card-header">
                    <h3>{importResult.dry_run ? 'Validation result' : 'Import result'}</h3>
                    <span className={`badge badge-${importResult.errors === 0 ? 'success' : 'warning'}`}>
                      {importResult.errors === 0 ? 'All valid' : `${importResult.errors} error(s)`}
                    </span>
                  </div>
                  <div style={{ padding: 16 }}>
                    <div className="metrics-grid" style={{ gridTemplateColumns: 'repeat(3,1fr)', marginBottom: 16 }}>
                      <div className="metric-card">
                        <div className="metric-label">Rows processed</div>
                        <div className="metric-value">{importResult.rows_processed}</div>
                      </div>
                      <div className="metric-card">
                        <div className="metric-label">{importResult.dry_run ? 'Valid rows' : 'Created'}</div>
                        <div className="metric-value" style={{ color: 'var(--green)' }}>
                          {importResult.dry_run ? importResult.valid : importResult.created}
                        </div>
                      </div>
                      <div className="metric-card">
                        <div className="metric-label">Errors</div>
                        <div className="metric-value" style={{ color: importResult.errors > 0 ? 'var(--red)' : 'inherit' }}>
                          {importResult.errors}
                        </div>
                      </div>
                    </div>

                    {importResult.error_details?.length > 0 && (
                      <div style={{ marginBottom: 12 }}>
                        <div style={{ fontWeight: 500, fontSize: 13, marginBottom: 8, color: 'var(--red)' }}>Errors:</div>
                        {importResult.error_details.map((e, i) => (
                          <div key={i} style={{ fontSize: 12, padding: '4px 8px', background: 'var(--red-bg)', borderRadius: 4, marginBottom: 4, color: 'var(--red)' }}>
                            Row {e.row}: {e.errors.join(', ')}
                          </div>
                        ))}
                      </div>
                    )}

                    {importResult.details?.length > 0 && (
                      <div>
                        <div style={{ fontWeight: 500, fontSize: 13, marginBottom: 8, color: 'var(--green)' }}>
                          {importResult.dry_run ? 'Valid rows:' : 'Created:'}
                        </div>
                        {importResult.details.slice(0, 10).map((d, i) => (
                          <div key={i} style={{ fontSize: 12, padding: '3px 8px', color: 'var(--text2)' }}>
                            ✓ Row {d.row}: {d.name}
                          </div>
                        ))}
                        {importResult.details.length > 10 && (
                          <div style={{ fontSize: 12, color: 'var(--text3)', padding: '3px 8px' }}>
                            …and {importResult.details.length - 10} more
                          </div>
                        )}
                      </div>
                    )}

                    {importResult.dry_run && importResult.errors === 0 && (
                      <div style={{ marginTop: 12 }}>
                        <button className="btn btn-primary" onClick={() => { setDryRun(false); doImport(); }}>
                          ✓ Looks good — import now
                        </button>
                      </div>
                    )}
                  </div>
                </div>
              )}
            </div>
          </div>

          <div className="card">
            <div className="card-header"><h3>Required CSV columns</h3></div>
            <div style={{ padding: 16 }}>
              <table className="table" style={{ fontSize: 12 }}>
                <thead><tr><th>Column</th><th>Required</th><th>Example</th><th>Notes</th></tr></thead>
                <tbody>
                  {[
                    ['first_name', '✓', 'Jane', ''],
                    ['last_name', '✓', 'Smith', ''],
                    ['hire_date', '✓', '2026-01-15', 'YYYY-MM-DD or MM/DD/YYYY'],
                    ['pay_type', '✓', 'salary', 'salary | hourly | contract'],
                    ['pay_rate', '✓', '75000', 'Annual salary or hourly rate'],
                    ['email', '', 'jane@co.com', 'For paystub notifications'],
                    ['pay_frequency', '', 'biweekly', 'weekly | biweekly | semimonthly | monthly'],
                    ['department', '', 'Engineering', ''],
                    ['job_title', '', 'Engineer', ''],
                    ['filing_status', '', 'single', 'single | married | head_of_household'],
                    ['state_code', '', 'NY', '2-letter state code'],
                    ['health_insurance_deduction', '', '300', 'Per-period pre-tax deduction ($)'],
                    ['retirement_401k_pct', '', '0.06', '6% = 0.06'],
                  ].map(([col, req, ex, note]) => (
                    <tr key={col}>
                      <td><code style={{ background: 'var(--bg3)', padding: '1px 4px', borderRadius: 3, fontSize: 11 }}>{col}</code></td>
                      <td style={{ color: req ? 'var(--green)' : 'var(--text3)' }}>{req || 'optional'}</td>
                      <td style={{ color: 'var(--text3)' }}>{ex}</td>
                      <td style={{ color: 'var(--text3)', fontSize: 11 }}>{note}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </>
      )}
    </div>
  );
}
