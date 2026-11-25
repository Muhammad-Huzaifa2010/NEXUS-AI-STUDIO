import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { useCallback, useEffect, useRef, useState } from 'react'
import {
  Activity, ArrowUp, Bot, BrainCircuit, Check, ChevronDown,
  Command, FileText, History, LayoutDashboard,
  Network, Plus, ShieldCheck, Sparkles, Square,
  Terminal, Zap
} from 'lucide-react'
import './App.css'

const agents = [
  { name: 'Orchestrator', short: 'OR', color: '#536dfe', icon: Network },
  { name: 'Research Agent', short: 'RE', color: '#13a89e', icon: BrainCircuit },
  { name: 'Execution Agent', short: 'EX', color: '#f08a48', icon: Terminal },
  { name: 'Content Agent', short: 'CO', color: '#9874e8', icon: FileText },
  { name: 'Deep Analysis Agent', short: 'DA', color: '#e16b91', icon: BrainCircuit },
]

function isSafeExternalHref(href) {
  try {
    const url = new URL(href)
    return url.protocol === 'https:' || url.protocol === 'http:'
  } catch {
    return false
  }
}

function SafeMarkdownLink({ href, children }) {
  if (!isSafeExternalHref(href)) return children
  return <a href={href} target="_blank" rel="noopener noreferrer">{children}</a>
}

function SafeMarkdownImage({ alt }) {
  return <span>{alt || ''}</span>
}

function App() {
  const [backend, setBackend] = useState('connecting')
  const [request, setRequest] = useState('')
  const [taskStatus, setTaskStatus] = useState('idle')
  const [activities, setActivities] = useState([])
  const [agentStates, setAgentStates] = useState({})
  const [result, setResult] = useState(null)
  const [error, setError] = useState('')
  const [activeTab, setActiveTab] = useState('workspace')
  const [workflow, setWorkflow] = useState('')
  const [historyItems, setHistoryItems] = useState([])
  const [historyLoading, setHistoryLoading] = useState(false)
  const [historyError, setHistoryError] = useState('')
  const [historyRefresh, setHistoryRefresh] = useState(0)
  const abortController = useRef(null)
  const textareaRef = useRef(null)
  const activityEndRef = useRef(null)

  const startNewTask = useCallback(() => {
    if (taskStatus === 'running') {
      abortController.current?.abort()
    }
    setRequest('')
    setTaskStatus('idle')
    setAgentStates({})
    setResult(null)
    setActivities([])
    setError('')
    setWorkflow('')
    setActiveTab('workspace')
    textareaRef.current?.focus()
  }, [taskStatus])

  useEffect(() => {
    fetch('/api/health')
      .then((response) => {
        if (!response.ok) throw new Error('Backend unavailable')
        return response.json()
      })
      .then((data) => setBackend(data.status))
      .catch(() => setBackend('offline'))

    return () => abortController.current?.abort()
  }, [])

  useEffect(() => {
    function handleNewTaskShortcut(event) {
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === 'k') {
        event.preventDefault()
        startNewTask()
      }
    }

    window.addEventListener('keydown', handleNewTaskShortcut)
    return () => window.removeEventListener('keydown', handleNewTaskShortcut)
  }, [startNewTask])

  useEffect(() => {
    activityEndRef.current?.scrollIntoView({ behavior: 'smooth', block: 'nearest' })
  }, [activities])

  useEffect(() => {
    if (activeTab === 'activity') {
      document.getElementById('activity-section')?.scrollIntoView({ behavior: 'smooth', block: 'start' })
      return
    }
    if (activeTab !== 'history') return

    let cancelled = false
    fetch('/api/tasks/history?limit=50')
      .then(async (response) => {
        if (!response.ok) throw new Error('Unable to load task history.')
        return response.json()
      })
      .then((data) => {
        if (!cancelled) {
          setHistoryItems(data.items || [])
          if (!data.persistence_enabled) {
            setHistoryError('PostgreSQL history is not enabled in this environment.')
          }
        }
      })
      .catch((err) => {
        if (!cancelled) setHistoryError(err.message || 'Unable to load task history.')
      })
      .finally(() => {
        if (!cancelled) setHistoryLoading(false)
      })

    return () => { cancelled = true }
  }, [activeTab, historyRefresh])

  function showHistory() {
    setHistoryError('')
    setHistoryLoading(true)
    if (activeTab === 'history') {
      setHistoryRefresh((value) => value + 1)
    } else {
      setActiveTab('history')
    }
  }

  function refreshHistory() {
    setHistoryError('')
    setHistoryLoading(true)
    setHistoryRefresh((value) => value + 1)
  }

  function handleActivity(payload) {
    const event = payload?.data || payload
    if (!event?.event) return

    setActivities((previous) => [...previous, event])

    if (event.agent) {
      const state =
        event.event === 'completed' ? 'completed' :
        event.event === 'agent_selected' ? 'selected' :
        event.event === 'started' ? 'running' :
        event.status === 'running' ? 'running' :
        event.status === 'executed' ? 'completed' : null

      if (state) {
        setAgentStates((previous) => ({
          ...previous,
          [event.agent]: state,
        }))
      }
    }
  }

  function handleSSEBlock(block) {
    let eventName = 'message'
    const dataLines = []

    for (const line of block.split('\n')) {
      if (line.startsWith('event:')) eventName = line.slice(6).trim()
      if (line.startsWith('data:')) dataLines.push(line.slice(5).trimStart())
    }

    if (!dataLines.length) return

    try {
      const data = JSON.parse(dataLines.join('\n'))

      if (eventName === 'status') {
        setTaskStatus(data.status === 'started' ? 'running' : (data.status || 'running'))
      } else if (eventName === 'activity') {
        handleActivity(data)
      } else if (eventName === 'result') {
        setResult(data)
        setWorkflow(data.workflow || '')
        setTaskStatus('completed')
        return true
      } else if (eventName === 'error') {
        setError(data.message || 'The task failed.')
        setTaskStatus('failed')
        return true
      }
    } catch {
      console.warn('Unable to parse a streaming event.')
    }

    return false
  }

  async function runTask(event) {
    event?.preventDefault()
    if (request.trim().length < 3 || taskStatus === 'running') return

    abortController.current?.abort()
    abortController.current = new AbortController()

    setTaskStatus('running')
    setActivities([])
    setAgentStates({})
    setResult(null)
    setError('')
    setWorkflow('')

    try {
      const response = await fetch('/api/tasks/stream', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Accept: 'text/event-stream',
        },
        body: JSON.stringify({ request: request.trim() }),
        signal: abortController.current.signal,
      })

      if (!response.ok) {
        throw new Error(await response.text() || `Server error: ${response.status}`)
      }

      if (!response.body) throw new Error('Streaming is not supported by this browser.')

      const reader = response.body.getReader()
      const decoder = new TextDecoder()
      let buffer = ''
      let receivedTerminalEvent = false

      while (true) {
        const { value, done } = await reader.read()
        if (done) break

        buffer += decoder.decode(value, { stream: true })
        buffer = buffer.replace(/\r\n/g, '\n')

        let boundary = buffer.indexOf('\n\n')
        while (boundary !== -1) {
          const block = buffer.slice(0, boundary)
          buffer = buffer.slice(boundary + 2)
          if (block.trim() && handleSSEBlock(block)) {
            receivedTerminalEvent = true
          }
          boundary = buffer.indexOf('\n\n')
        }
      }

      buffer += decoder.decode()
      if (buffer.trim() && handleSSEBlock(buffer)) {
        receivedTerminalEvent = true
      }

      if (!receivedTerminalEvent) {
        throw new Error('The server stream ended without a final result or error.')
      }
    } catch (err) {
      if (err.name === 'AbortError') return
      setError(err.message || 'Unable to connect to NEXUS.')
      setTaskStatus('failed')
    }
  }

  function stopTask() {
    abortController.current?.abort()
    setTaskStatus('stopped')
  }

  function statusText(status) {
    return ({
      running: 'Working',
      selected: 'Selected',
      completed: 'Complete',
    })[status] || 'Standby'
  }

  const isRunning = taskStatus === 'running'

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <a className="brand" href="#home" aria-label="NEXUS AI STUDIO home">
          <div className="brand-mark">
            <img src="/nexus-logo.svg" alt="NEXUS AI STUDIO logo" />
          </div>
          <div className="brand-copy">
            <strong>NEXUS <span>AI</span></strong>
            <small>INTELLIGENCE STUDIO</small>
          </div>
        </a>

        <button type="button" className="new-task-button" onClick={startNewTask}>
          <Plus size={17} /> New task
          <span>⌘ / Ctrl K</span>
        </button>

        <div className="nav-group">
          <p className="nav-caption">WORKSPACE</p>
          <button type="button" className={`nav-item ${activeTab === 'workspace' ? 'active' : ''}`} aria-current={activeTab === 'workspace' ? 'page' : undefined} onClick={() => setActiveTab('workspace')}>
            <LayoutDashboard size={17} /> Overview
          </button>
          <button type="button" className={`nav-item ${activeTab === 'activity' ? 'active' : ''}`} aria-current={activeTab === 'activity' ? 'page' : undefined} onClick={() => setActiveTab('activity')}>
            <Activity size={17} /> Activity
          </button>
          <button type="button" className={`nav-item ${activeTab === 'history' ? 'active' : ''}`} aria-current={activeTab === 'history' ? 'page' : undefined} onClick={showHistory}>
            <History size={17} /> Task history
          </button>
        </div>

        <div className="sidebar-agents">
          <p className="nav-caption">YOUR AGENTS <span>05</span></p>
          {agents.map((agent) => {
            const Icon = agent.icon
            const state = agentStates[agent.name]
            return (
              <div className="sidebar-agent" key={agent.name}>
                <span className="agent-avatar" style={{ '--agent-color': agent.color }}>
                  <Icon size={14} />
                </span>
                <span>{agent.name.replace(' Agent', '')}</span>
                <i className={`mini-state ${state || ''}`} />
              </div>
            )
          })}
        </div>

        <div className="sidebar-bottom">
          <div className="profile-row">
            <div className="profile-avatar">N</div>
            <div><strong>Studio workspace</strong><small>Personal environment</small></div>
            <ChevronDown size={15} />
          </div>
        </div>
      </aside>

      <main className="main-workspace">
        <header className="top-header">
          <div className="breadcrumb">Workspace <span>/</span> <strong>{activeTab === 'history' ? 'Task history' : activeTab === 'activity' ? 'Activity' : 'Overview'}</strong></div>
          <div className="header-right">
            <div className="system-pill">
              <i className={`system-indicator ${backend}`} />
              {backend === 'operational' ? 'All systems operational' :
                backend === 'connecting' ? 'Connecting' :
                backend === 'degraded' ? 'Backend degraded' :
                backend === 'offline' ? 'Backend offline' : 'Backend status unknown'}
            </div>
            <div className="header-date">NEXUS AI STUDIO <span>·</span> v1.0</div>
          </div>
        </header>

        {activeTab === 'history' ? (
          <div className="workspace-content history-content">
            <section className="welcome-row">
              <div>
                <div className="overline"><History size={13} /> PERSISTENT TASK RECORDS</div>
                <h1>Your execution<br /><span>history.</span></h1>
                <p>Completed and failed tasks saved in your PostgreSQL database.</p>
              </div>
              <button className="execute-button" onClick={refreshHistory}>Refresh history</button>
            </section>
            {historyLoading && <div className="history-empty">Loading saved tasks…</div>}
            {historyError && <div className="error-banner"><strong>History status</strong><p>{historyError}</p></div>}
            {!historyLoading && historyItems.length === 0 && (
              <div className="history-empty">No saved tasks yet. Run a task from Overview and it will appear here.</div>
            )}
            <section className="history-list">
              {historyItems.map((item) => (
                <article className="history-card" key={item.id}>
                  <div className="history-card-top">
                    <span className={`execution-state ${item.status}`}>{item.status}</span>
                    <time>{new Date(item.created_at).toLocaleString()}</time>
                  </div>
                  <h3>{item.request}</h3>
                  <div className="history-response markdown-content">
                    <ReactMarkdown
                      remarkPlugins={[remarkGfm]}
                      components={{
                        a: SafeMarkdownLink,
                        img: SafeMarkdownImage,
                      }}
                    >
                      {item.response || (item.status === 'failed' ? 'This task failed. Check backend logs for details.' : 'No response was saved.')}
                    </ReactMarkdown>
                  </div>
                  <div className="history-card-footer">
                    <span>{item.workflow || 'unknown'} · {item.selected_agent || 'No agent recorded'}</span>

                  </div>
                </article>
              ))}
            </section>
          </div>
        ) : (
        <div className={`workspace-content ${activeTab === 'activity' ? 'activity-content' : ''}`}>
          <section className="welcome-row">
            <div>
              <div className="overline"><Sparkles size={13} /> YOUR AI COMMAND CENTER</div>
              <h1>Good work starts with<br /><span>one intelligent command.</span></h1>
              <p>Coordinate your AI agents, execute workflows and turn ideas into outcomes.</p>
            </div>
            <div className="welcome-badge"><ShieldCheck size={17} /> Multi-agent workspace</div>
          </section>

          <section className="overview-strip">
            <div className="overview-stat">
              <span className="stat-icon blue"><Bot size={17} /></span>
              <div><strong>05</strong><small>AI agents</small></div>
            </div>
            <div className="stat-divider" />
            <div className="overview-stat">
              <span className="stat-icon teal"><Network size={17} /></span>
              <div><strong>01</strong><small>Orchestration flow</small></div>
            </div>
            <div className="stat-divider" />
            <div className="overview-stat">
              <span className="stat-icon orange"><Activity size={17} /></span>
              <div><strong>{activities.length.toString().padStart(2, '0')}</strong><small>Live events</small></div>
            </div>
            <div className="stat-divider" />
            <div className="overview-stat">
              <span className="stat-icon purple"><Zap size={17} /></span>
              <div><strong>{taskStatus === 'completed' ? 'Ready' : isRunning ? 'Active' : 'Idle'}</strong><small>Execution state</small></div>
            </div>
          </section>

          <section className="command-section">
            <div className="section-title-row">
              <div><span className="section-kicker">02 / COMMAND</span><h2>What are we working on?</h2></div>
              <span className="command-shortcut"><Command size={12} /> ENTER TO EXECUTE</span>
            </div>
            <form className="command-box" onSubmit={runTask}>
              <div className="command-topline"><Sparkles size={15} /><span>NEXUS COMMAND INTERFACE</span><span className="command-mode">GENERAL AI</span></div>
              <textarea
                ref={textareaRef}
                value={request}
                onChange={(event) => setRequest(event.target.value)}
                onKeyDown={(event) => {
                  if (event.key === 'Enter' && !event.shiftKey) {
                    event.preventDefault()
                    runTask(event)
                  }
                }}
                placeholder="Describe what you want NEXUS to accomplish..."
                maxLength={12000}
                disabled={isRunning}
              />
              <div className="command-footer">
                <span>Be specific. NEXUS will select the right agent and tools.</span>
                <div>
                  <span className="char-count">{request.length}/12000</span>
                  {isRunning ? (
                    <button className="execute-button stop" type="button" onClick={stopTask}><Square size={14} /> Stop</button>
                  ) : (
                    <button className="execute-button" type="submit" disabled={backend !== 'operational' || request.trim().length < 3}>
                      Execute task <ArrowUp size={16} />
                    </button>
                  )}
                </div>
              </div>
            </form>
            <div className="suggestion-row">
              <span>TRY A COMMAND</span>
              <button onClick={() => setRequest('Calculate 125 multiplied by 8, then convert the result from centimetres into inches.')}>Calculate and convert</button>
              <button onClick={() => setRequest('Write a concise research brief explaining how artificial intelligence agents work.')}>Research brief</button>
              <button onClick={() => setRequest('Conduct a deep analysis of the opportunities, limitations, risks, and future of artificial intelligence in education.')}>Deep analysis</button>
            </div>
          </section>

          {(activities.length > 0 || isRunning || result || error || activeTab === 'activity') && (
            <section className="execution-section" id="activity-section">
              <div className="section-title-row">
                <div><span className="section-kicker">03 / SYSTEM ACTIVITY</span><h2>Execution monitor</h2></div>
                <span className={`execution-state ${taskStatus}`}>{taskStatus.toUpperCase()}</span>
              </div>
              <div className="execution-layout">
                <div className="activity-panel">
                  <div className="panel-heading"><strong>Live activity</strong><span>{activities.length} EVENTS</span></div>
                  <div className="activity-feed">
                    {activities.length === 0 && <p className="empty-activity">Waiting for agent activity...</p>}
                    {activities.map((item, index) => (
                      <div className="feed-item" key={`${item.step}-${index}`}>
                        <span className={`feed-dot ${item.status}`} />
                        <div className="feed-copy">
                          <strong>{item.agent || 'System'}{item.tool ? ` · ${item.tool}` : ''}</strong>
                          <small>{item.event.replaceAll('_', ' ')}{item.round ? ` · Round ${item.round}` : ''}</small>
                        </div>
                        <span className={`feed-status ${item.status}`}>{item.status}</span>
                      </div>
                    ))}
                    <div ref={activityEndRef} />
                  </div>
                </div>
                <div className="agent-status-panel">
                  <div className="panel-heading"><strong>Agent status</strong><span>5 AGENTS</span></div>
                  {agents.map((agent) => {
                    const state = agentStates[agent.name]
                    return (
                      <div className="agent-status-row" key={agent.name}>
                        <span className="agent-status-icon" style={{ '--agent-color': agent.color }}><agent.icon size={14} /></span>
                        <span>{agent.name}</span>
                        <small className={state || ''}>{statusText(state)}</small>
                      </div>
                    )
                  })}
                </div>
              </div>
            </section>
          )}

          {error && <div className="error-banner"><strong>Execution error</strong><p>{error}</p></div>}

          {result && (
            <section className="result-section">
              <div className="section-title-row">
                <div><span className="section-kicker">04 / OUTPUT</span><h2>Task completed</h2></div>
                <span className="result-complete"><Check size={14} /> SUCCESS</span>
              </div>
              <div className="output-card">
                <div className="output-header"><div><Sparkles size={16} /><strong>NEXUS response</strong></div><span>{result.executed_agents?.length ? `Ran: ${result.executed_agents.join(' → ')}` : result.selected_agent} · {workflow}</span></div>
                <div className="output-body markdown-content">
                    <ReactMarkdown
                      remarkPlugins={[remarkGfm]}
                      components={{
                        a: SafeMarkdownLink,
                        img: SafeMarkdownImage,
                      }}
                    >
                      {result.response || ''}
                    </ReactMarkdown>
                  </div>



                {result.tool_events?.length > 0 && (
                  <div className="output-tools">
                    <h3><Terminal size={15} /> Tool execution</h3>
                    {result.tool_events.map((tool, index) => (
                      <div className="output-tool-row" key={`${tool.tool}-${index}`}>
                        <div><strong>{tool.tool}</strong><small>Round {tool.round} · {JSON.stringify(tool.arguments)}</small></div>
                        <span>{tool.status}</span>
                        <pre>{tool.result}</pre>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </section>
          )}

          <footer className="workspace-footer">
            <span>© 2026 NEXUS AI STUDIO</span>
            <span>BUILT FOR INTELLIGENT WORKFLOWS</span>
          </footer>
        </div>
        )}
      </main>
    </div>
  )
}

export default App
