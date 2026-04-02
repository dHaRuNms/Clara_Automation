import { useState, useEffect, useCallback } from 'react'

const API = ''

function useApi() {
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)

  const fetchAccounts = useCallback(async () => {
    setLoading(true)
    try {
      const res = await fetch(`${API}/api/accounts`)
      const json = await res.json()
      setData(json.accounts || [])
    } catch { setData([]) }
    setLoading(false)
  }, [])

  const fetchAgent = useCallback(async (id) => {
    const res = await fetch(`${API}/api/agent/${id}`)
    return res.json()
  }, [])

  const fetchCalls = useCallback(async (id) => {
    const res = await fetch(`${API}/api/calls/${id}`)
    return res.json()
  }, [])

  const fetchCallers = useCallback(async (id) => {
    const res = await fetch(`${API}/api/callers/${id}`)
    return res.json()
  }, [])

  const fetchAgentLog = useCallback(async (id) => {
    const res = await fetch(`${API}/api/agent-log/${id}`)
    return res.json()
  }, [])

  const fetchMode = useCallback(async () => {
    try {
      const res = await fetch(`${API}/api/mode`)
      return res.json()
    } catch { return { mode: 'classic' } }
  }, [])

  const deploy = useCallback(async (id) => {
    const res = await fetch(`${API}/api/deploy/${id}`, { method: 'POST' })
    return res.json()
  }, [])

  const process = useCallback(async (id) => {
    const res = await fetch(`${API}/api/process/${id}`, { method: 'POST' })
    return res.json()
  }, [])

  const batch = useCallback(async () => {
    const res = await fetch(`${API}/api/batch`, { method: 'POST' })
    return res.json()
  }, [])

  useEffect(() => { fetchAccounts() }, [fetchAccounts])

  return { accounts: data, loading, refresh: fetchAccounts, fetchAgent, fetchCalls, fetchCallers, fetchAgentLog, fetchMode, deploy, process, batch }
}

// ── Toast System ──
let toastId = 0
function ToastContainer({ toasts }) {
  return (
    <div className="toast-container">
      {toasts.map(t => (
        <div key={t.id} className={`toast toast-${t.type}`}>
          {t.type === 'success' ? '✓' : t.type === 'error' ? '✕' : 'ℹ'} {t.msg}
        </div>
      ))}
    </div>
  )
}

// ── Sidebar ──
const NAV = [
  { id: 'dashboard', label: 'Dashboard', icon: <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><rect x="3" y="3" width="7" height="7" /><rect x="14" y="3" width="7" height="7" /><rect x="3" y="14" width="7" height="7" /><rect x="14" y="14" width="7" height="7" /></svg> },
  { id: 'customers', label: 'Accounts', icon: <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M3 9l9-7 9 7v11a2 2 0 01-2 2H5a2 2 0 01-2-2z" /><polyline points="9 22 9 12 15 12 15 22" /></svg> },
  { id: 'callers', label: 'Callers', icon: <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M17 21v-2a4 4 0 00-4-4H5a4 4 0 00-4 4v2" /><circle cx="9" cy="7" r="4" /><path d="M23 21v-2a4 4 0 00-3-3.87" /><path d="M16 3.13a4 4 0 010 7.75" /></svg> },
  { id: 'agents', label: 'Agents', icon: <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M22 16.92v3a2 2 0 01-2.18 2 19.79 19.79 0 01-8.63-3.07 19.5 19.5 0 01-6-6 19.79 19.79 0 01-3.07-8.67A2 2 0 014.11 2h3a2 2 0 012 1.72 12.84 12.84 0 00.7 2.81 2 2 0 01-.45 2.11L8.09 9.91a16 16 0 006 6l1.27-1.27a2 2 0 012.11-.45 12.84 12.84 0 002.81.7A2 2 0 0122 16.92z" /></svg> },
]

function Sidebar({ page, setPage }) {
  return (
    <aside className="sidebar">
      <div className="sidebar-brand">
        <div className="brand-mark">C</div>
        <div>
          <div className="brand-name">Clara AI</div>
          <div className="brand-sub">Customer Management</div>
        </div>
      </div>
      <nav className="sidebar-nav">
        {NAV.map(n => (
          <button key={n.id} className={`nav-link ${page === n.id ? 'active' : ''}`} onClick={() => setPage(n.id)}>
            {n.icon} {n.label}
          </button>
        ))}
      </nav>
      <div className="sidebar-bottom">
        <div className="system-status"><div className="status-dot"></div> System Online</div>
      </div>
    </aside>
  )
}

// ── Customer Detail Drawer ──
function AgentTracePanel({ trace }) {
  if (!trace || trace.length === 0) {
    return (
      <div className="detail-section">
        <h3>Agent Trace</h3>
        <p style={{ color: 'var(--gray-400)', fontSize: 13 }}>No trace available. This account was processed in classic (Gemini) mode, or has not been processed yet.</p>
      </div>
    )
  }
  const AGENT_COLORS = {
    extractor: { bg: '#eff6ff', color: '#2563eb', border: '#bfdbfe' },
    researcher: { bg: '#f0fdf4', color: '#16a34a', border: '#bbf7d0' },
    qa: { bg: '#fffbeb', color: '#d97706', border: '#fde68a' },
    config_generator: { bg: '#faf5ff', color: '#9333ea', border: '#e9d5ff' },
    fallback: { bg: '#fef2f2', color: '#dc2626', border: '#fecaca' },
  }
  return (
    <div className="detail-section">
      <h3>🧠 Multi-Agent Trace</h3>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 10, marginTop: 12 }}>
        {trace.map((t, i) => {
          const c = AGENT_COLORS[t.agent] || AGENT_COLORS.fallback
          const isOk = t.status === 'success'
          return (
            <div key={i} style={{ border: `1px solid ${c.border}`, borderRadius: 8, padding: '12px 14px', background: c.bg }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 6 }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                  <span style={{ fontWeight: 700, color: c.color, fontSize: 13, textTransform: 'capitalize' }}>{t.agent.replace('_', ' ')}</span>
                  <span style={{ fontSize: 11, color: 'var(--gray-400)', fontFamily: 'monospace' }}>{t.model?.split('/').pop() || ''}</span>
                </div>
                <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                  {t.duration_ms && <span style={{ fontSize: 11, color: 'var(--gray-500)' }}>{(t.duration_ms / 1000).toFixed(1)}s</span>}
                  <span style={{ fontSize: 11, fontWeight: 600, color: isOk ? '#16a34a' : '#dc2626' }}>{isOk ? '✓' : '⚠'} {t.status}</span>
                </div>
              </div>
              <p style={{ margin: 0, fontSize: 12, color: 'var(--gray-600)', lineHeight: 1.5 }}>{t.summary}</p>
            </div>
          )
        })}
      </div>
    </div>
  )
}

function CustomerDrawer({ account, onClose, onDeploy, onReprocess, agentData, agentTrace }) {
  const [tab, setTab] = useState('overview')
  if (!account) return null

  const memo = agentData?.memo || {}
  const deployment = agentData?.deployment
  const unknowns = memo.questions_or_unknowns || []
  const services = memo.services_supported || []
  const emergencies = memo.emergency_definition || []

  return (
    <>
      <div className={`drawer-overlay ${account ? 'open' : ''}`} onClick={onClose} />
      <div className={`drawer ${account ? 'open' : ''}`}>
        <div className="drawer-head">
          <h2>{memo.company_name || account.account_id}</h2>
          <button className="btn-icon" onClick={onClose}>
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><line x1="18" y1="6" x2="6" y2="18" /><line x1="6" y1="6" x2="18" y2="18" /></svg>
          </button>
        </div>
        <div className="drawer-tabs">
          {['overview', 'contact', 'issues', 'agent-trace', 'agent-spec', 'changelog'].map(t => (
            <button key={t} className={`drawer-tab ${tab === t ? 'active' : ''}`} onClick={() => setTab(t)}>
              {t === 'overview' ? 'Overview' : t === 'contact' ? 'Contact Info' : t === 'issues' ? `Issues (${unknowns.length})` : t === 'agent-trace' ? '🧠 Agent Trace' : t === 'agent-spec' ? 'Agent Spec' : 'Changelog'}
            </button>
          ))}
        </div>
        <div className="drawer-content">
          {tab === 'overview' && (
            <>
              <div className="detail-section">
                <h3>Company Information</h3>
                <div className="field-grid">
                  <Field label="Company Name" value={memo.company_name} />
                  <Field label="Account ID" value={memo.account_id} />
                  <Field label="Business Hours" value={memo.business_hours} />
                  <Field label="Timezone" value={memo.timezone} />
                  <Field label="CRM System" value={memo.crm_system} />
                  <Field label="Version" value={memo.version} />
                </div>
              </div>
              <div className="detail-section">
                <h3>Services Offered</h3>
                <div>{services.length > 0 ? services.map(s => <span key={s} className="tag">{s}</span>) : <span className="field-value empty">No services listed</span>}</div>
              </div>
              <div className="detail-section">
                <h3>Emergency Triggers</h3>
                <div>{emergencies.length > 0 ? emergencies.map(e => <span key={e} className="tag" style={{ background: '#fef2f2', color: '#dc2626' }}>{e}</span>) : <span className="field-value empty">Not configured</span>}</div>
              </div>
              {deployment && (
                <div className="detail-section">
                  <h3>Deployment</h3>
                  <div className="field-grid">
                    <Field label="Agent ID" value={deployment.agent_id} mono />
                    <Field label="LLM ID" value={deployment.llm_id} mono />
                    <Field label="Deployed At" value={fmtDate(deployment.deployed_at)} />
                    <Field label="Voice" value={deployment.voice_id || 'retell-Cimo'} />
                  </div>
                </div>
              )}
            </>
          )}

          {tab === 'contact' && (
            <>
              <div className="detail-section">
                <h3>Contact Details</h3>
                <div className="field-grid">
                  <Field label="Phone Number" value={memo.contact_phone} icon="📞" />
                  <Field label="Email" value={memo.contact_email} icon="✉️" />
                  <Field label="Office Address" value={memo.office_address} icon="📍" full />
                  <Field label="Emergency Phone" value={memo.emergency_phone} icon="🚨" />
                </div>
              </div>
              <div className="detail-section">
                <h3>Routing Rules</h3>
                <div className="field-grid">
                  <Field label="Emergency Routing" value={memo.emergency_routing_rules} full />
                  <Field label="Non-Emergency Routing" value={memo.non_emergency_routing_rules} full />
                  <Field label="Call Transfer Rules" value={memo.call_transfer_rules} full />
                  <Field label="Transfer Timeout" value={memo.transfer_timeout_seconds ? `${memo.transfer_timeout_seconds} seconds` : ''} />
                  <Field label="Integration Constraints" value={memo.integration_constraints} full />
                </div>
              </div>
            </>
          )}

          {tab === 'issues' && (
            <div className="detail-section">
              <h3>Open Issues & Missing Information</h3>
              {unknowns.length > 0 ? (
                <ul className="issue-list">
                  {unknowns.map((q, i) => (
                    <li key={i} className="issue-item">
                      <div className="issue-icon">
                        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><circle cx="12" cy="12" r="10" /><line x1="12" y1="8" x2="12" y2="12" /><line x1="12" y1="16" x2="12.01" y2="16" /></svg>
                      </div>
                      {q}
                    </li>
                  ))}
                </ul>
              ) : (
                <p style={{ color: 'var(--gray-400)', fontSize: 13 }}>No open issues. All information has been collected. ✓</p>
              )}
            </div>
          )}

          {tab === 'agent-trace' && <AgentTracePanel trace={agentTrace} />}

          {tab === 'agent-spec' && (
            <>
              {agentData?.llm_config && (
                <div className="detail-section">
                  <h3>Retell LLM Configuration</h3>
                  <pre className="code-block">{JSON.stringify(agentData.llm_config, null, 2)}</pre>
                </div>
              )}
              {agentData?.agent_config && (
                <div className="detail-section">
                  <h3>Agent Configuration</h3>
                  <pre className="code-block">{JSON.stringify(agentData.agent_config, null, 2)}</pre>
                </div>
              )}
            </>
          )}

          {tab === 'changelog' && (
            <div className="detail-section">
              <h3>Changes (v1 → v2)</h3>
              {agentData?.changelog ? (
                agentData.changelog.split('\n').filter(l => l.startsWith('- ')).map((l, i) => (
                  <div key={i} className="changelog-entry"><div className="cl-icon"></div>{l.substring(2)}</div>
                ))
              ) : (
                <p style={{ color: 'var(--gray-400)', fontSize: 13 }}>No changelog available. Run the onboarding pipeline to generate changes.</p>
              )}
            </div>
          )}
        </div>
        <div className="drawer-footer">
          <button className="btn btn-primary" onClick={() => onDeploy(account.account_id)}>Deploy to Retell</button>
          <button className="btn btn-outline" onClick={() => onReprocess(account.account_id)}>Reprocess</button>
        </div>
      </div>
    </>
  )
}

function Field({ label, value, icon, mono, full }) {
  return (
    <div className={`field ${full ? 'field-full' : ''}`}>
      <span className="field-label">{label}</span>
      <span className={`field-value ${!value ? 'empty' : ''}`} style={mono ? { fontFamily: 'monospace', fontSize: 11 } : {}}>
        {icon && value ? `${icon} ` : ''}{value || 'Not set'}
      </span>
    </div>
  )
}

// ── Dashboard Page ──
function DashboardPage({ accounts, onSelect, onViewAll }) {
  const deployed = accounts.filter(a => a.deployed).length
  const issues = accounts.reduce((sum, a) => sum + (a.issues || 0), 0)

  return (
    <>
      <div className="metrics-row">
        <div className="metric-card"><span className="metric-label">Total Customers</span><span className="metric-value">{accounts.length}</span></div>
        <div className="metric-card"><span className="metric-label">Agents Deployed</span><span className="metric-value">{deployed}</span><span className="metric-sub">{accounts.length > 0 ? Math.round(deployed / accounts.length * 100) : 0}% of accounts</span></div>
        <div className="metric-card"><span className="metric-label">Open Issues</span><span className="metric-value">{issues}</span></div>
        <div className="metric-card"><span className="metric-label">Total Calls</span><span className="metric-value">–</span><span className="metric-sub">Deploy agents to track</span></div>
      </div>
      <div className="card">
        <div className="card-header">
          <h2>Recent Customers</h2>
          <button className="btn-text" onClick={onViewAll}>View All →</button>
        </div>
        <table className="data-table">
          <thead>
            <tr>
              <th>Company</th>
              <th>Contact</th>
              <th>Phone</th>
              <th>Status</th>
              <th>Issues</th>
            </tr>
          </thead>
          <tbody>
            {accounts.length === 0 ? (
              <tr className="empty-row"><td colSpan="5">No customers yet. Add transcripts and process them.</td></tr>
            ) : accounts.map(a => (
              <tr key={a.account_id} onClick={() => onSelect(a)}>
                <td><strong>{a.company || a.account_id}</strong><br /><span style={{ fontSize: 11, color: 'var(--gray-400)' }}>{a.account_id}</span></td>
                <td style={{ fontSize: 12, color: 'var(--gray-500)' }}>{a.email || '—'}</td>
                <td style={{ fontSize: 12 }}>{a.phone || '—'}</td>
                <td><span className={`badge ${a.deployed ? 'badge-live' : 'badge-draft'}`}><span className="badge-dot"></span> {a.deployed ? 'Live' : 'Draft'}</span></td>
                <td>{a.issues > 0 ? <span style={{ color: 'var(--orange-600)', fontWeight: 600 }}>{a.issues}</span> : <span style={{ color: 'var(--green-600)' }}>✓</span>}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </>
  )
}

// ── Customers Page ──
function CustomersPage({ accounts, onSelect }) {
  const [search, setSearch] = useState('')
  const filtered = accounts.filter(a =>
    (a.company || a.account_id).toLowerCase().includes(search.toLowerCase()) ||
    (a.email || '').toLowerCase().includes(search.toLowerCase()) ||
    (a.phone || '').includes(search)
  )

  return (
    <div className="card">
      <div className="card-header">
        <h2>All Customers ({accounts.length})</h2>
        <div className="search-box">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><circle cx="11" cy="11" r="8" /><line x1="21" y1="21" x2="16.65" y2="16.65" /></svg>
          <input type="text" placeholder="Search by name, email, phone..." value={search} onChange={e => setSearch(e.target.value)} />
        </div>
      </div>
      <table className="data-table">
        <thead>
          <tr>
            <th>Company</th>
            <th>Email</th>
            <th>Phone</th>
            <th>Services</th>
            <th>CRM</th>
            <th>Agent Status</th>
            <th>Issues</th>
          </tr>
        </thead>
        <tbody>
          {filtered.length === 0 ? (
            <tr className="empty-row"><td colSpan="7">No customers match your search.</td></tr>
          ) : filtered.map(a => (
            <tr key={a.account_id} onClick={() => onSelect(a)}>
              <td><strong>{a.company || a.account_id}</strong><br /><span style={{ fontSize: 11, color: 'var(--gray-400)' }}>{a.account_id}</span></td>
              <td style={{ fontSize: 12 }}>{a.email || '—'}</td>
              <td style={{ fontSize: 12, fontWeight: 500 }}>{a.phone || '—'}</td>
              <td>{(a.services || []).map(s => <span key={s} className="tag">{s}</span>)}</td>
              <td>{a.crm || '—'}</td>
              <td><span className={`badge ${a.deployed ? 'badge-live' : 'badge-draft'}`}><span className="badge-dot"></span> {a.deployed ? 'Live' : 'Draft'}</span></td>
              <td>{a.issues > 0 ? <span style={{ color: 'var(--orange-600)', fontWeight: 600 }}>{a.issues}</span> : <span style={{ color: 'var(--green-600)' }}>✓</span>}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

// ── Agents Page ──
function AgentsPage({ accounts, onSelect }) {
  return (
    <div className="card">
      <div className="card-header"><h2>Voice Agents</h2></div>
      <table className="data-table">
        <thead>
          <tr>
            <th>Agent Name</th>
            <th>Customer</th>
            <th>Agent ID</th>
            <th>Versions</th>
            <th>Deployed At</th>
            <th>Status</th>
          </tr>
        </thead>
        <tbody>
          {accounts.length === 0 ? (
            <tr className="empty-row"><td colSpan="6">No agents configured yet.</td></tr>
          ) : accounts.map(a => (
            <tr key={a.account_id} onClick={() => onSelect(a)}>
              <td><strong>Clara AI – {a.company || a.account_id}</strong></td>
              <td>{a.company || a.account_id}</td>
              <td style={{ fontFamily: 'monospace', fontSize: 11 }}>{a.agent_id ? `${a.agent_id.substring(0, 20)}...` : '—'}</td>
              <td>{(a.versions || []).map(v => <span key={v} className="tag">{v}</span>)}</td>
              <td style={{ fontSize: 12 }}>{a.deployed_at ? fmtDate(a.deployed_at) : '—'}</td>
              <td><span className={`badge ${a.deployed ? 'badge-live' : 'badge-draft'}`}><span className="badge-dot"></span> {a.deployed ? 'Live' : 'Draft'}</span></td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

// ── Urgency Badge ──
function UrgencyBadge({ level }) {
  const styles = {
    critical: { bg: '#fef2f2', color: '#dc2626', border: '#fee2e2' },
    high: { bg: '#fff7ed', color: '#ea580c', border: '#ffedd5' },
    medium: { bg: '#fffbeb', color: '#d97706', border: '#fef3c7' },
    low: { bg: '#f0fdf4', color: '#16a34a', border: '#dcfce7' },
  };
  const s = styles[level?.toLowerCase()] || styles.medium;
  return level ? <span className="badge" style={{ background: s.bg, color: s.color, border: `1px solid ${s.border}` }}>{level}</span> : <span style={{ color: 'var(--gray-400)' }}>—</span>;
}

// ── Callers Page (people calling the business) ──
function CallersPage({ accounts, fetchCallers }) {
  const [selected, setSelected] = useState(accounts.length > 0 ? accounts[0].account_id : '')
  const [callers, setCallers] = useState([])
  const [loading, setLoading] = useState(false)
  const [expandedId, setExpandedId] = useState(null)

  const loadCallers = useCallback(async (id) => {
    if (!id) return
    setLoading(true)
    try {
      const data = await fetchCallers(id)
      setCallers(data?.callers || [])
    } catch { setCallers([]) }
    setLoading(false)
  }, [fetchCallers])

  useEffect(() => { if (selected) loadCallers(selected) }, [selected, loadCallers])

  return (
    <>
      <div style={{ marginBottom: 16, display: 'flex', alignItems: 'center', gap: 12 }}>
        <label style={{ fontSize: 13, fontWeight: 500, color: 'var(--gray-600)' }}>Account:</label>
        <select
          value={selected}
          onChange={e => setSelected(e.target.value)}
          style={{ padding: '6px 12px', border: '1px solid var(--gray-300)', borderRadius: 6, fontSize: 13, fontFamily: 'inherit', background: 'white' }}
        >
          {accounts.map(a => <option key={a.account_id} value={a.account_id}>{a.company || a.account_id}</option>)}
        </select>
        <button className="btn btn-outline btn-sm" onClick={() => loadCallers(selected)}>Refresh</button>
      </div>

      <div className="card">
        <div className="card-header">
          <h2>Incoming Callers ({callers.length})</h2>
        </div>
        {loading ? (
          <div style={{ padding: 40, textAlign: 'center' }}><div className="spinner" style={{ margin: '0 auto' }}></div></div>
        ) : (
          <table className="data-table">
            <thead>
              <tr>
                <th>Caller</th>
                <th>Phone</th>
                <th>Problem</th>
                <th>Urgency</th>
                <th>Schedule</th>
                <th>Action</th>
                <th>When</th>
              </tr>
            </thead>
            <tbody>
              {callers.length === 0 ? (
                <tr className="empty-row"><td colSpan="7">No calls received yet. Make test calls from the <a href="https://dashboard.retellai.com" target="_blank" rel="noreferrer" style={{ color: 'var(--blue-600)' }}>Retell Dashboard</a> to see callers here.</td></tr>
              ) : callers.map(c => (
                <>
                  <tr key={c.call_id} onClick={() => setExpandedId(expandedId === c.call_id ? null : c.call_id)} style={{ cursor: 'pointer' }}>
                    <td><strong>{c.name || 'Unknown'}</strong></td>
                    <td style={{ fontWeight: 500 }}>{c.phone || '—'}</td>
                    <td style={{ maxWidth: 220 }}>{c.problem || '—'}</td>
                    <td><UrgencyBadge level={c.urgency} /></td>
                    <td>{c.schedule || '—'}</td>
                    <td><span className="tag">{c.action_taken || '—'}</span></td>
                    <td style={{ fontSize: 12, color: 'var(--gray-500)' }}>{c.timestamp ? fmtDate(new Date(c.timestamp * 1000).toISOString()) : '—'}</td>
                  </tr>
                  {expandedId === c.call_id && (
                    <tr key={`${c.call_id}-detail`} style={{ background: 'var(--gray-50)', cursor: 'default' }}>
                      <td colSpan="7" style={{ padding: '16px 24px' }}>
                        <div className="field-grid">
                          <Field label="Full Summary" value={c.summary} full />
                          <Field label="Address" value={c.address} icon="📍" />
                          <Field label="Call Type" value={c.call_type} />
                          <Field label="Duration" value={c.duration_sec ? `${c.duration_sec}s` : ''} />
                          <Field label="Sentiment" value={c.sentiment} />
                          <Field label="Call Successful" value={c.successful === true ? '✓ Yes' : c.successful === false ? '✕ No' : ''} />
                          <Field label="Call ID" value={c.call_id} mono />
                        </div>
                      </td>
                    </tr>
                  )}
                </>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </>
  )
}

// ── Helpers ──
function fmtDate(s) {
  if (!s) return ''
  try { return new Date(s).toLocaleDateString('en-US', { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' }) } catch { return s }
}

// ── Main App ──
export default function App() {
  const [page, setPage] = useState('dashboard')
  const [selectedAccount, setSelectedAccount] = useState(null)
  const [agentData, setAgentData] = useState(null)
  const [agentTrace, setAgentTrace] = useState([])
  const [mode, setMode] = useState({ mode: 'classic' })
  const [toasts, setToasts] = useState([])
  const [batchLoading, setBatchLoading] = useState(false)
  const api = useApi()

  // Fetch mode on mount
  useEffect(() => {
    api.fetchMode && api.fetchMode().then(m => setMode(m || { mode: 'classic' }))
  }, [])

  const toast = (msg, type = 'info') => {
    const id = ++toastId
    setToasts(prev => [...prev, { id, msg, type }])
    setTimeout(() => setToasts(prev => prev.filter(t => t.id !== id)), 4000)
  }

  // Enrich accounts with memo data
  const [enriched, setEnriched] = useState([])
  useEffect(() => {
    if (!api.accounts) return
    const enrich = async () => {
      const results = await Promise.all(api.accounts.map(async (a) => {
        try {
          const data = await api.fetchAgent(a.account_id)
          const memo = data?.memo || {}
          return {
            ...a,
            email: memo.contact_email || '',
            phone: memo.contact_phone || '',
            services: memo.services_supported || [],
            crm: memo.crm_system || '',
            issues: (memo.questions_or_unknowns || []).length,
          }
        } catch {
          return { ...a, email: '', phone: '', services: [], crm: '', issues: 0 }
        }
      }))
      setEnriched(results)
    }
    enrich()
  }, [api.accounts])

  const openDrawer = async (account) => {
    setSelectedAccount(account)
    setAgentTrace([])
    try {
      const [data, log] = await Promise.all([
        api.fetchAgent(account.account_id),
        api.fetchAgentLog(account.account_id)
      ])
      setAgentData(data)
      setAgentTrace(log?.trace || [])
    } catch { setAgentData(null); setAgentTrace([]) }
  }

  const closeDrawer = () => { setSelectedAccount(null); setAgentData(null) }

  const handleDeploy = async (id) => {
    toast(`Deploying ${id}...`, 'info')
    const res = await api.deploy(id)
    if (res?.status === 'success' || res?.status === 'updated') {
      toast(`${id} deployed! Agent: ${res.agent_id}`, 'success')
      api.refresh()
    } else {
      toast(`Deploy failed: ${res?.message || 'Unknown error'}`, 'error')
    }
  }

  const handleReprocess = async (id) => {
    toast(`Reprocessing ${id}...`, 'info')
    const res = await api.process(id)
    if (res?.status === 'success') {
      toast('Reprocessed successfully', 'success')
      api.refresh()
      const data = await api.fetchAgent(id)
      setAgentData(data)
    } else {
      toast('Reprocessing failed', 'error')
    }
  }

  const handleBatch = async () => {
    setBatchLoading(true)
    toast('Processing all accounts...', 'info')
    const res = await api.batch()
    setBatchLoading(false)
    if (res) {
      toast(`Batch complete: ${res.success || 0} success, ${res.failed || 0} failed`, res.failed > 0 ? 'error' : 'success')
      api.refresh()
    } else {
      toast('Batch failed', 'error')
    }
  }

  const titles = { dashboard: 'Dashboard', customers: 'Accounts', callers: 'Callers', agents: 'Agents' }

  return (
    <div className="layout">
      <Sidebar page={page} setPage={setPage} />
      <div className="main-wrap">
        <header className="topbar">
          <h1 className="page-title">{titles[page]}</h1>
          <div className="topbar-actions">
            {mode.mode === 'multi-agent' ? (
              <span style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 12, fontWeight: 600, color: '#7c3aed', background: '#f5f3ff', border: '1px solid #ddd6fe', borderRadius: 20, padding: '4px 12px' }}>
                🧠 Multi-Agent Mode
              </span>
            ) : (
              <span style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 12, color: 'var(--gray-400)', background: 'var(--gray-100)', border: '1px solid var(--gray-200)', borderRadius: 20, padding: '4px 12px' }}>
                ⚡ Classic Mode
              </span>
            )}
            <button className="btn-icon" onClick={api.refresh} title="Refresh">
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M1 4v6h6M23 20v-6h-6" /><path d="M20.49 9A9 9 0 005.64 5.64L1 10m22 4l-4.64 4.36A9 9 0 013.51 15" /></svg>
            </button>
            <button className="btn btn-primary" onClick={handleBatch} disabled={batchLoading}>
              {batchLoading ? <><div className="spinner"></div> Processing...</> : <>▸ Process All</>}
            </button>
          </div>
        </header>
        <div className="content">
          {api.loading ? (
            <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', height: 200 }}><div className="spinner"></div></div>
          ) : (
            <>
              {page === 'dashboard' && <DashboardPage accounts={enriched} onSelect={openDrawer} onViewAll={() => setPage('customers')} />}
              {page === 'customers' && <CustomersPage accounts={enriched} onSelect={openDrawer} />}
              {page === 'callers' && <CallersPage accounts={enriched} fetchCallers={api.fetchCallers} />}
              {page === 'agents' && <AgentsPage accounts={enriched} onSelect={openDrawer} />}
            </>
          )}
        </div>
      </div>

      <CustomerDrawer
        account={selectedAccount}
        agentData={agentData}
        agentTrace={agentTrace}
        onClose={closeDrawer}
        onDeploy={handleDeploy}
        onReprocess={handleReprocess}
      />
      <ToastContainer toasts={toasts} />
    </div>
  )
}
