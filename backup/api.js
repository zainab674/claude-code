/**
 * PayrollOS API client — centralised fetch wrapper.
 * Every API call in the frontend goes through here.
 */
const BASE = process.env.REACT_APP_API_URL || 'http://localhost:8000';

function getToken() {
  return localStorage.getItem('payroll_token');
}

async function request(path, options = {}) {
  const token = getToken();
  const isFormData = options.body instanceof FormData;
  const headers = {
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
    ...(isFormData ? {} : { 'Content-Type': 'application/json' }),
    ...options.headers,
  };

  const res = await fetch(`${BASE}${path}`, { ...options, headers });

  if (res.status === 401) {
    localStorage.removeItem('payroll_token');
    localStorage.removeItem('payroll_user');
    window.location.href = '/';
    return;
  }
  if (res.status === 204) return null;
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || `HTTP ${res.status}`);
  }
  return res.json();
}

const clean = (p) =>
  Object.fromEntries(Object.entries(p).filter(([, v]) => v !== undefined && v !== '' && v !== null));

const qs = (p = {}) => new URLSearchParams(clean(p)).toString();
const q = (p = {}) => { const s = qs(p); return s ? '?' + s : ''; };

// ── Auth ──────────────────────────────────────────────────────
export const login = (email, password) =>
  request('/auth/login', { method: 'POST', body: JSON.stringify({ email, password }) });
export const register = (data) =>
  request('/auth/register', { method: 'POST', body: JSON.stringify(data) });
export const forgotPassword = (email) =>
  request('/auth/forgot-password', { method: 'POST', body: JSON.stringify({ email }) });
export const resetPassword = (token, password) =>
  request('/auth/reset-password', { method: 'POST', body: JSON.stringify({ token, new_password: password }) });

// ── Company ───────────────────────────────────────────────────
export const getCompany = () => request('/company');
export const updateCompany = (data) =>
  request('/company', { method: 'PUT', body: JSON.stringify(data) });

// ── Users ─────────────────────────────────────────────────────
export const getMe = () => request('/users/me');
export const updateMe = (data) => request('/users/me', { method: 'PUT', body: JSON.stringify(data) });
export const getUsers = () => request('/users');
export const inviteUser = (data) =>
  request('/users/invite', { method: 'POST', body: JSON.stringify(data) });
export const updateUser = (id, data) =>
  request(`/users/${id}`, { method: 'PUT', body: JSON.stringify(data) });
export const deactivateUser = (id) =>
  request(`/users/${id}`, { method: 'DELETE' });

// ── Employees ─────────────────────────────────────────────────
export const getEmployees = (p = {}) => request(`/employees${q(p)}`);
export const getEmployee = (id) => request(`/employees/${id}`);
export const createEmployee = (data) =>
  request('/employees', { method: 'POST', body: JSON.stringify(data) });
export const updateEmployee = (id, data) =>
  request(`/employees/${id}`, { method: 'PUT', body: JSON.stringify(data) });
export const terminateEmployee = (id, data) =>
  request(`/employees/${id}/terminate`, { method: 'POST', body: JSON.stringify(data) });

// ── Time tracking ─────────────────────────────────────────────
export const getTimeEntries = (p = {}) => request(`/time${q(p)}`);
export const createTimeEntry = (data) =>
  request('/time', { method: 'POST', body: JSON.stringify(data) });
export const updateTimeEntry = (id, data) =>
  request(`/time/${id}`, { method: 'PUT', body: JSON.stringify(data) });
export const deleteTimeEntry = (id) =>
  request(`/time/${id}`, { method: 'DELETE' });
export const approveTimeEntry = (id) =>
  request(`/time/${id}/approve`, { method: 'POST' });
export const getTimeSummary = (p = {}) =>
  request(`/time/summary${q(p)}`);
export const clockIn = (employee_id) =>
  request('/time/clock-in', { method: 'POST', body: JSON.stringify({ employee_id }) });
export const clockOut = (employee_id) =>
  request('/time/clock-out', { method: 'POST', body: JSON.stringify({ employee_id }) });

// ── Pay periods ───────────────────────────────────────────────
export const getPayPeriods = (p = {}) => request(`/pay-periods${q(p)}`);
export const createPayPeriod = (data) =>
  request('/pay-periods', { method: 'POST', body: JSON.stringify(data) });
export const generatePayPeriods = (p = {}) =>
  request(`/pay-periods/generate${q(p)}`, { method: 'POST' });

// ── Payroll ───────────────────────────────────────────────────
export const calculatePaycheck = (data) =>
  request('/payroll/calculate', { method: 'POST', body: JSON.stringify(data) });
export const previewPayroll = (data) =>
  request('/payroll/preview', { method: 'POST', body: JSON.stringify(data) });
export const runPayroll = (data) =>
  request('/payroll/run', { method: 'POST', body: JSON.stringify(data) });
export const getPayrollHistory = (p = {}) => request(`/payroll/history${q(p)}`);
export const getPayRun = (id) => request(`/payroll/runs/${id}`);
export const voidPayRun = (id) =>
  request(`/payroll/runs/${id}/void`, { method: 'POST' });

// ── Paystubs ──────────────────────────────────────────────────
export const getPaystubs = (p = {}) => request(`/paystubs${q(p)}`);
export const getPaystub = (id) => request(`/paystubs/${id}`);
export const downloadPaystubUrl = (id) => `${BASE}/paystubs/${id}/download?token=${getToken()}`;

// ── Reports ───────────────────────────────────────────────────
export const getYtdSummary = (year) =>
  request(`/reports/ytd-summary${year ? '?year=' + year : ''}`);
export const getByDepartment = (year) =>
  request(`/reports/by-department${year ? '?year=' + year : ''}`);
export const getEmployeeYtd = (year) =>
  request(`/reports/employee-ytd${year ? '?year=' + year : ''}`);
export const getTaxLiability = (year) =>
  request(`/reports/tax-liability${year ? '?year=' + year : ''}`);

// ── Export ────────────────────────────────────────────────────
export const exportUrl = (path) => `${BASE}${path}`;

// ── Audit ─────────────────────────────────────────────────────
export const getAuditLog = (p = {}) => request(`/audit${q(p)}`);

// ── Webhooks ──────────────────────────────────────────────────
export const getWebhooks = () => request('/webhooks');
export const createWebhook = (data) =>
  request('/webhooks', { method: 'POST', body: JSON.stringify(data) });
export const deleteWebhook = (id) =>
  request(`/webhooks/${id}`, { method: 'DELETE' });
export const testWebhook = (id) =>
  request(`/webhooks/${id}/test`, { method: 'POST' });

// ── API Keys ──────────────────────────────────────────────────
export const getApiKeys = () => request('/api-keys');
export const createApiKey = (data) =>
  request('/api-keys', { method: 'POST', body: JSON.stringify(data) });
export const revokeApiKey = (id) =>
  request(`/api-keys/${id}`, { method: 'DELETE' });

// ── PTO ───────────────────────────────────────────────────────
export const getPtoPolicies = () => request('/pto/policies');
export const createPtoPolicy = (data) =>
  request('/pto/policies', { method: 'POST', body: JSON.stringify(data) });
export const getPtoBalances = (p = {}) => request(`/pto/balances${q(p)}`);
export const getPtoRequests = (p = {}) => request(`/pto/requests${q(p)}`);
export const createPtoRequest = (data) =>
  request('/pto/requests', { method: 'POST', body: JSON.stringify(data) });
export const reviewPtoRequest = (id, status) =>
  request(`/pto/requests/${id}/review`, { method: 'PUT', body: JSON.stringify({ status }) });
export const runPtoAccrual = (pay_period_end) =>
  request(`/pto/balances/accrue?pay_period_end=${pay_period_end}`, { method: 'POST' });

// ── Onboarding ────────────────────────────────────────────────
export const initOnboarding = (employee_id) =>
  request(`/onboarding/employees/${employee_id}/initialize`, { method: 'POST' });
export const getOnboarding = (employee_id) =>
  request(`/onboarding/employees/${employee_id}`);
export const completeTask = (task_id, data = {}) =>
  request(`/onboarding/tasks/${task_id}/complete`, { method: 'PUT', body: JSON.stringify(data) });
export const uncompleteTask = (task_id) =>
  request(`/onboarding/tasks/${task_id}/uncomplete`, { method: 'PUT' });
export const getPendingOnboarding = () => request('/onboarding/pending');

// ── Benefits ──────────────────────────────────────────────────
export const getBenefitPlans = (p = {}) => request(`/benefits/plans${q(p)}`);
export const createBenefitPlan = (data) =>
  request('/benefits/plans', { method: 'POST', body: JSON.stringify(data) });
export const getEnrollmentWindows = () => request('/benefits/windows');
export const createEnrollmentWindow = (data) =>
  request('/benefits/windows', { method: 'POST', body: JSON.stringify(data) });
export const getBenefitElections = (p = {}) => request(`/benefits/elections${q(p)}`);
export const createBenefitElection = (data) =>
  request('/benefits/elections', { method: 'POST', body: JSON.stringify(data) });
export const waiveBenefitElection = (id) =>
  request(`/benefits/elections/${id}`, { method: 'DELETE' });
export const getEmployeeBenefitsSummary = (id) =>
  request(`/benefits/summary/employee/${id}`);

// ── Direct deposit ────────────────────────────────────────────
export const getBankAccount = (emp_id) =>
  request(`/direct-deposit/employees/${emp_id}`);
export const saveBankAccount = (emp_id, data) =>
  request(`/direct-deposit/employees/${emp_id}`, { method: 'POST', body: JSON.stringify(data) });
export const verifyBankAccount = (emp_id) =>
  request(`/direct-deposit/employees/${emp_id}/verify`, { method: 'PUT' });
export const removeBankAccount = (emp_id) =>
  request(`/direct-deposit/employees/${emp_id}`, { method: 'DELETE' });
export const getDirectDepositSummary = () => request('/direct-deposit/summary');

// ── Documents ─────────────────────────────────────────────────
export const getDocuments = (emp_id, p = {}) =>
  request(`/documents/employees/${emp_id}${q(p)}`);
export const uploadDocument = (emp_id, formData, category = 'other', description = '') => {
  const token = getToken();
  return fetch(`${BASE}/documents/employees/${emp_id}?category=${category}&description=${description}`, {
    method: 'POST',
    headers: { Authorization: `Bearer ${token}` },
    body: formData,
  }).then(r => r.json());
};
export const downloadDocumentUrl = (doc_id) =>
  `${BASE}/documents/${doc_id}/download`;
export const deleteDocument = (doc_id) =>
  request(`/documents/${doc_id}`, { method: 'DELETE' });

// ── Salary bands ──────────────────────────────────────────────
export const getSalaryBands = (p = {}) => request(`/salary-bands${q(p)}`);
export const createSalaryBand = (data) =>
  request('/salary-bands', { method: 'POST', body: JSON.stringify(data) });
export const updateSalaryBand = (id, data) =>
  request(`/salary-bands/${id}`, { method: 'PUT', body: JSON.stringify(data) });
export const getSalaryBandAnalysis = (p = {}) =>
  request(`/salary-bands/analysis${q(p)}`);

// ── Org chart ─────────────────────────────────────────────────
export const getOrgChart = () => request('/org-chart');
export const getOrgFlat = (p = {}) => request(`/org-chart/flat${q(p)}`);
export const setManager = (emp_id, manager_id) =>
  request(`/org-chart/employee/${emp_id}/manager?manager_id=${manager_id || ''}`, { method: 'PUT' });
export const getOrgStats = () => request('/org-chart/stats');

// ── Leave ─────────────────────────────────────────────────────
export const getLeaveTypes = () => request('/leave/types');
export const getLeave = (p = {}) => request(`/leave${q(p)}`);
export const createLeave = (data) =>
  request('/leave', { method: 'POST', body: JSON.stringify(data) });
export const reviewLeave = (id, status, notes) =>
  request(`/leave/${id}/review`, { method: 'PUT', body: JSON.stringify({ status, notes }) });
export const recordLeaveReturn = (id, return_date) =>
  request(`/leave/${id}/return?return_date=${return_date}`, { method: 'PUT' });
export const getActiveLeave = () => request('/leave/active');
export const getLeaveCalendar = (month, year) =>
  request(`/leave/calendar?month=${month}&year=${year}`);

// ── Contractors ───────────────────────────────────────────────
export const getContractors = () => request('/contractors');
export const createContractor = (data) =>
  request('/contractors', { method: 'POST', body: JSON.stringify(data) });
export const getContractorPayments = (id, year) =>
  request(`/contractors/${id}/payments${year ? '?year=' + year : ''}`);
export const recordContractorPayment = (id, data) =>
  request(`/contractors/${id}/payments`, { method: 'POST', body: JSON.stringify(data) });
export const get1099Report = (year) =>
  request(`/1099/report${year ? '?year=' + year : ''}`);
export const download1099XmlUrl = (year) =>
  `${BASE}/1099/xml${year ? '?year=' + year : ''}`;

// ── Performance ───────────────────────────────────────────────
export const getReviewCycles = () => request('/performance/cycles');
export const createReviewCycle = (data) =>
  request('/performance/cycles', { method: 'POST', body: JSON.stringify(data) });
export const launchCycle = (id) =>
  request(`/performance/cycles/${id}/launch`, { method: 'POST' });
export const getReviews = (p = {}) => request(`/performance/reviews${q(p)}`);
export const getReview = (id) => request(`/performance/reviews/${id}`);
export const updateReview = (id, data) =>
  request(`/performance/reviews/${id}`, { method: 'PUT', body: JSON.stringify(data) });
export const submitReview = (id) =>
  request(`/performance/reviews/${id}/submit`, { method: 'POST' });
export const acknowledgeReview = (id, comments) =>
  request(`/performance/reviews/${id}/acknowledge`, { method: 'POST', body: JSON.stringify({ comments }) });
export const getGoals = (p = {}) => request(`/performance/goals${q(p)}`);
export const createGoal = (data) =>
  request('/performance/goals', { method: 'POST', body: JSON.stringify(data) });
export const updateGoalProgress = (id, pct) =>
  request(`/performance/goals/${id}/progress?progress_pct=${pct}`, { method: 'PUT' });
export const getPerformanceSummary = (emp_id) =>
  request(`/performance/summary/${emp_id}`);

// ── Expenses ──────────────────────────────────────────────────
export const getExpenses = (p = {}) => request(`/expenses${q(p)}`);
export const submitExpense = (employee_id, data) =>
  request(`/expenses?employee_id=${employee_id}`, { method: 'POST', body: JSON.stringify(data) });
export const approveExpense = (id) =>
  request(`/expenses/${id}/approve`, { method: 'PUT' });
export const denyExpense = (id, reason) =>
  request(`/expenses/${id}/deny`, { method: 'PUT', body: JSON.stringify({ denied_reason: reason }) });
export const getPendingReimbursements = () => request('/expenses/pending-payroll');
export const batchReimburse = (ids, run_id) =>
  request(`/expenses/batch-reimburse${run_id ? '?pay_run_id=' + run_id : ''}`,
    { method: 'POST', body: JSON.stringify(ids) });
export const getExpenseReport = (year) =>
  request(`/expenses/report${year ? '?year=' + year : ''}`);

// ── Compliance ────────────────────────────────────────────────
export const runComplianceCheck = () => request('/compliance');
export const prePayrollCheck = () => request('/compliance/pre-payroll');

// ── Notifications ─────────────────────────────────────────────
export const getNotifications = (p = {}) => request(`/notifications${q(p)}`);
export const markNotificationRead = (id) =>
  request(`/notifications/${id}/read`, { method: 'POST' });
export const markAllNotificationsRead = () =>
  request('/notifications/read-all', { method: 'POST' });
export const dismissNotification = (id) =>
  request(`/notifications/${id}`, { method: 'DELETE' });

// ── Adjustments ───────────────────────────────────────────────
export const getAdjustments = (p = {}) => request(`/adjustments${q(p)}`);
export const createAdjustment = (data) =>
  request('/adjustments', { method: 'POST', body: JSON.stringify(data) });
export const bulkCreateAdjustments = (adjustments) =>
  request('/adjustments/bulk', { method: 'POST', body: JSON.stringify({ adjustments }) });
export const applyAdjustments = (ids, run_id) =>
  request(`/adjustments/apply?pay_run_id=${run_id}`,
    { method: 'POST', body: JSON.stringify(ids) });
export const cancelAdjustment = (id) =>
  request(`/adjustments/${id}`, { method: 'DELETE' });

// ── W-2 ───────────────────────────────────────────────────────
export const getW2Data = (year) => request(`/w2/${year}`);
export const downloadW2XmlUrl = (year) => `${BASE}/w2/${year}/xml`;

// ── Journal ───────────────────────────────────────────────────
export const getJournalEntries = (run_id) => request(`/journal/${run_id}`);
export const downloadJournalCsvUrl = (run_id) => `${BASE}/journal/${run_id}/csv`;
export const downloadJournalQboUrl = (run_id) => `${BASE}/journal/${run_id}/qbo`;

// ── Garnishments ──────────────────────────────────────────────
export const getGarnishments = (p = {}) => request(`/garnishments${q(p)}`);
export const createGarnishment = (data) =>
  request('/garnishments', { method: 'POST', body: JSON.stringify(data) });
export const deactivateGarnishment = (id) =>
  request(`/garnishments/${id}/deactivate`, { method: 'PUT' });
export const calculateGarnishment = (emp_id, disposable_income) =>
  request(`/garnishments/employee/${emp_id}/calculate?net_disposable_income=${disposable_income}`);

// ── Offer letters ─────────────────────────────────────────────
export const generateOfferLetter = (data) =>
  request('/offer-letters', { method: 'POST', body: JSON.stringify(data) });
export const downloadOfferLetterUrl = (id) =>
  `${BASE}/offer-letters/${id}/download`;

// ── Scheduler ────────────────────────────────────────────────
export const getScheduleStatus = () => request('/scheduler/status');
export const setupSchedule = (data) =>
  request('/scheduler/setup', { method: 'POST', body: JSON.stringify(data) });
export const triggerScheduledPayroll = () =>
  request('/scheduler/trigger', { method: 'POST' });
export const cancelSchedule = () =>
  request('/scheduler/cancel', { method: 'DELETE' });

// ── Reconciliation ────────────────────────────────────────────
export const compareRuns = (run_a, run_b) =>
  request(`/reconciliation/compare?run_a=${run_a}&run_b=${run_b}`);
export const getVariance = (run_id) =>
  request(`/reconciliation/variance/${run_id}`);
export const getYtdCheck = (year) =>
  request(`/reconciliation/ytd-check/${year}`);

// ── ATS ───────────────────────────────────────────────────────
export const getJobs = (p = {}) => request(`/jobs${q(p)}`);
export const createJob = (data) =>
  request('/jobs', { method: 'POST', body: JSON.stringify(data) });
export const updateJob = (id, data) =>
  request(`/jobs/${id}`, { method: 'PUT', body: JSON.stringify(data) });
export const publishJob = (id) =>
  request(`/jobs/${id}/publish`, { method: 'PUT' });
export const closeJob = (id) =>
  request(`/jobs/${id}/close`, { method: 'PUT' });
export const deleteJob = (id) =>
  request(`/jobs/${id}`, { method: 'DELETE' });
export const getCandidates = (job_id, p = {}) =>
  request(`/jobs/${job_id}/candidates${q(p)}`);
export const addCandidate = (job_id, data) =>
  request(`/jobs/${job_id}/candidates`, { method: 'POST', body: JSON.stringify(data) });
export const updateCandidateStage = (cand_id, data) =>
  request(`/candidates/${cand_id}/stage`, { method: 'PUT', body: JSON.stringify(data) });
export const addHiringNote = (cand_id, data) =>
  request(`/candidates/${cand_id}/notes`, { method: 'POST', body: JSON.stringify(data) });
export const getHiringNotes = (cand_id) =>
  request(`/candidates/${cand_id}/notes`);
export const getAtsDashboard = () => request('/ats/dashboard');

// ── Custom fields ─────────────────────────────────────────────
export const getCustomFieldSchemas = (entity_type) =>
  request(`/custom-fields/schema${entity_type ? '?entity_type=' + entity_type : ''}`);
export const createCustomFieldSchema = (data) =>
  request('/custom-fields/schema', { method: 'POST', body: JSON.stringify(data) });
export const deleteCustomFieldSchema = (id) =>
  request(`/custom-fields/schema/${id}`, { method: 'DELETE' });
export const getCustomFieldValues = (entity_type, entity_id) =>
  request(`/custom-fields/values/${entity_type}/${entity_id}`);
export const setCustomFieldValues = (entity_type, entity_id, values) =>
  request(`/custom-fields/values/${entity_type}/${entity_id}`,
    { method: 'PUT', body: JSON.stringify(values) });

// ── Health ────────────────────────────────────────────────────
export const getHealth = () => request('/health');
export const getDetailedHealth = () => request('/health/detailed');

// ── Self-service (employee portal) ───────────────────────────
export const getMyProfile = () => request('/self-service/profile');
export const updateMyContact = (data) =>
  request('/self-service/profile/contact', { method: 'PUT', body: JSON.stringify(data) });
export const getMyPaystubs = () => request('/self-service/paystubs');
export const getMyPto = () => request('/self-service/pto');
export const getMyYtd = () => request('/self-service/ytd');
export const getMyOnboarding = () => request('/self-service/onboarding');

// ── Paystub email (added) ─────────────────────────────────
export const emailPaystub = (paystub_id) =>
  request(`/paystubs/${paystub_id}/email`, { method: 'POST' });
export const emailAllPaystubs = (pay_run_id) =>
  request(`/paystubs/run/${pay_run_id}/email-all`, { method: 'POST' });
