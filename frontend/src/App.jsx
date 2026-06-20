import React, { useState, useEffect, useRef, useCallback } from 'react';
import ReactMarkdown from 'react-markdown';
import {
  Search, Cpu, Activity, CheckCircle2, Clock, AlertCircle,
  Database, Layers, Zap, BarChart2, Bot, Globe, Brain,
  FlaskConical, MemoryStick, ListChecks, ChevronDown, ChevronRight,
  Timer, TrendingUp, Terminal, Info, Trash2
} from 'lucide-react';
import './App.css';

const API_BASE = 'http://localhost:8000';

// ── Agent colour palette ──────────────────────────────────────────────────────
const AGENT_COLORS = {
  planner:  { color: '#a78bfa', bg: 'rgba(167,139,250,0.08)', border: 'rgba(167,139,250,0.3)', glow: '0 0 12px rgba(167,139,250,0.25)' },
  research: { color: '#38bdf8', bg: 'rgba(56,189,248,0.08)',  border: 'rgba(56,189,248,0.3)',  glow: '0 0 12px rgba(56,189,248,0.25)' },
  analyst:  { color: '#4ade80', bg: 'rgba(74,222,128,0.08)',  border: 'rgba(74,222,128,0.3)',  glow: '0 0 12px rgba(74,222,128,0.25)' },
};
const DEFAULT_COLOR = { color: '#94a3b8', bg: 'rgba(148,163,184,0.08)', border: 'rgba(148,163,184,0.2)', glow: 'none' };

const PIPELINE = [
  { key: 'planner',  label: 'Planner',  icon: Brain,       desc: 'Decomposes query into subtasks' },
  { key: 'research', label: 'Research', icon: Globe,        desc: 'Executes subtasks via web search' },
  { key: 'analyst',  label: 'Analyst',  icon: FlaskConical, desc: 'Synthesizes findings into answer' },
];

// ── Utility helpers ───────────────────────────────────────────────────────────
const fmt_ms  = (ms)  => ms >= 1000 ? `${(ms / 1000).toFixed(1)}s` : `${Math.round(ms)}ms`;
const fmt_tok = (n)   => n >= 1000 ? `${(n / 1000).toFixed(1)}k`  : (n || 0).toString();
const ts_hms  = (iso) => iso ? new Date(iso).toLocaleTimeString() : '—';

// ── Collapsible card ──────────────────────────────────────────────────────────
function Panel({ icon: Icon, title, badge, children, defaultOpen = true, accent }) {
  const [open, setOpen] = useState(defaultOpen);
  return (
    <div className="panel" style={{ '--accent': accent || 'var(--accent-blue)' }}>
      <button className="panel-header" onClick={() => setOpen(o => !o)}>
        <div className="panel-title-row">
          <Icon size={15} className="panel-icon" />
          <span className="panel-title">{title}</span>
          {badge != null && <span className="panel-badge">{badge}</span>}
        </div>
        {open ? <ChevronDown size={14} className="panel-chevron" /> : <ChevronRight size={14} className="panel-chevron" />}
      </button>
      {open && <div className="panel-body">{children}</div>}
    </div>
  );
}

// ── Timeline event row ────────────────────────────────────────────────────────
function TimelineEvent({ agent, event, timestamp, durationMs, tokensIn, tokensOut }) {
  const meta = AGENT_COLORS[agent] || DEFAULT_COLOR;
  const isEnd = event === 'agent_end';
  return (
    <div className="timeline-row">
      <div className="timeline-dot" style={{ background: meta.color, boxShadow: meta.glow }} />
      <div className="timeline-line" />
      <div className="timeline-content">
        <span className="timeline-agent" style={{ color: meta.color }}>{agent}</span>
        <span className="timeline-event">{isEnd ? 'Completed' : 'Started'}</span>
        {isEnd && durationMs != null && (
          <span className="timeline-meta">{fmt_ms(durationMs)}</span>
        )}
        {isEnd && tokensIn != null && (
          <span className="timeline-meta">↑{fmt_tok(tokensIn)} ↓{fmt_tok(tokensOut)}</span>
        )}
        <span className="timeline-time">{ts_hms(timestamp)}</span>
      </div>
    </div>
  );
}

// ── Context handoff card ──────────────────────────────────────────────────────
function ContextCard({ agent, input, output }) {
  const meta  = AGENT_COLORS[agent] || DEFAULT_COLOR;
  const [showOutput, setShowOutput] = useState(false);
  return (
    <div className="context-card" style={{ borderColor: meta.border, background: meta.bg }}>
      <div className="context-agent" style={{ color: meta.color }}>
        <Bot size={13} /> {agent}
      </div>
      <div className="context-section">
        <span className="context-label">Input</span>
        <div className="context-text">{input}</div>
      </div>
      {output && (
        <div className="context-section">
          <button className="context-toggle" onClick={() => setShowOutput(o => !o)}>
            <span className="context-label">Output</span>
            {showOutput ? <ChevronDown size={12} /> : <ChevronRight size={12} />}
          </button>
          {showOutput && <div className="context-text context-output">{output}</div>}
        </div>
      )}
    </div>
  );
}

// ── Tool call card ────────────────────────────────────────────────────────────
function ToolCallCard({ call, index }) {
  const [open, setOpen] = useState(false);
  return (
    <div className="tool-card">
      <div className="tool-header" onClick={() => setOpen(o => !o)}>
        <div className="tool-name-row">
          <Terminal size={13} style={{ color: '#38bdf8' }} />
          <span className="tool-name">{call.tool}</span>
          <span className="tool-index">#{index + 1}</span>
        </div>
        <div className="tool-meta-row">
          <span className="tool-duration">{fmt_ms(call.duration_ms)}</span>
          {open ? <ChevronDown size={12} /> : <ChevronRight size={12} />}
        </div>
      </div>
      <div className="tool-query">{call.input}</div>
      {open && (
        <div className="tool-output">
          <span className="context-label">Output</span>
          <div className="context-text">{call.output}</div>
        </div>
      )}
    </div>
  );
}

// ── Token bar ─────────────────────────────────────────────────────────────────
function TokenBar({ label, value, max, color }) {
  const pct = max > 0 ? (value / max) * 100 : 0;
  return (
    <div className="token-bar-row">
      <span className="token-bar-label">{label}</span>
      <div className="token-bar-track">
        <div className="token-bar-fill" style={{ width: `${pct}%`, background: color }} />
      </div>
      <span className="token-bar-value">{fmt_tok(value)}</span>
    </div>
  );
}

// ── Eval criterion ────────────────────────────────────────────────────────────
function EvalCriterion({ label, passed }) {
  return (
    <div className={`eval-criterion ${passed ? 'eval-pass' : 'eval-fail'}`}>
      {passed
        ? <CheckCircle2 size={14} style={{ color: '#4ade80' }} />
        : <AlertCircle  size={14} style={{ color: '#f87171' }} />}
      <span>{label}</span>
    </div>
  );
}

// ── Main App ─────────────────────────────────────────────────────────────────
export default function App() {
  const [query, setQuery]       = useState('');
  const [loading, setLoading]   = useState(false);
  const [result, setResult]     = useState(null);
  const [error, setError]       = useState(null);
  const [timeline, setTimeline] = useState([]);     // raw SSE events for timeline
  const [liveAgent, setLiveAgent] = useState(null); // currently active agent
  const [memory, setMemory]     = useState(null);
  const [memoryContextTokens, setMemoryContextTokens] = useState(0);
  const esRef = useRef(null);

  // Load memory on mount
  useEffect(() => {
    fetch(`${API_BASE}/memory`).then(r => r.json()).then(setMemory).catch(() => {});
  }, []);

  const handleSearch = useCallback(async (e) => {
    e?.preventDefault();
    if (!query.trim() || loading) return;

    // Reset state
    setLoading(true);
    setError(null);
    setResult(null);
    setTimeline([]);
    setLiveAgent(null);
    setMemoryContextTokens(0);

    const sessionId = `mars-lite-${Date.now()}`;
    const url = `${API_BASE}/run/stream?query=${encodeURIComponent(query)}&session_id=${sessionId}`;

    // Close previous EventSource if any
    if (esRef.current) esRef.current.close();

    const es = new EventSource(url);
    esRef.current = es;

    es.addEventListener('agent_start', (e) => {
      const data = JSON.parse(e.data);
      setLiveAgent(data.agent);
      if (data.memory_context_tokens !== undefined) {
        setMemoryContextTokens(data.memory_context_tokens);
      }
      setTimeline(prev => [...prev, { type: 'agent_start', ...data }]);
    });

    es.addEventListener('agent_end', (e) => {
      const data = JSON.parse(e.data);
      if (data.memory_context_tokens !== undefined) {
        setMemoryContextTokens(data.memory_context_tokens);
      }
      setTimeline(prev => [...prev, { type: 'agent_end', ...data }]);
    });

    es.addEventListener('result', (e) => {
      const data = JSON.parse(e.data);
      setResult(data);
      setMemory(data.memory);
      if (data.memory_context_tokens !== undefined) {
        setMemoryContextTokens(data.memory_context_tokens);
      }
      setLiveAgent(null);
      setLoading(false);
      es.close();
    });

    es.addEventListener('error', (e) => {
      let msg = 'Pipeline error';
      try { msg = JSON.parse(e.data).detail; } catch (_) {}
      setError(msg);
      setLiveAgent(null);
      setLoading(false);
      es.close();
    });

    es.onerror = () => {
      if (loading) {
        setError('Connection lost. Is the backend running?');
        setLoading(false);
      }
      es.close();
    };
  }, [query, loading]);

  const handleClearTraces = useCallback(async () => {
    if (loading) return;
    try {
      const res = await fetch(`${API_BASE}/traces`, { method: 'DELETE' });
      if (res.ok) {
        setTimeline([]);
        setResult(null);
      }
    } catch (err) {
      console.error('Failed to clear traces:', err);
    }
  }, [loading]);

  const handleClearMemory = useCallback(async () => {
    if (loading) return;
    try {
      const res = await fetch(`${API_BASE}/memory`, { method: 'DELETE' });
      if (res.ok) {
        setMemory(null);
        setMemoryContextTokens(0);
      }
    } catch (err) {
      console.error('Failed to clear memory:', err);
    }
  }, [loading]);


  // Derived data
  const agentEndEvents = timeline.filter(e => e.type === 'agent_end');
  const totalDuration  = agentEndEvents.reduce((s, e) => s + (e.duration_ms || 0), 0);
  const totalTokens    = agentEndEvents.reduce((s, e) => s + (e.total_tokens || 0), 0) + memoryContextTokens;
  const maxTokens      = Math.max(...agentEndEvents.map(e => e.total_tokens || 0), memoryContextTokens, 1);

  // Extract subtasks, tool calls, and answer dynamically from timeline events, falling back to final result
  const plannerEnd = timeline.find(e => e.type === 'agent_end' && e.agent_name === 'planner');
  const subtasks = plannerEnd?.subtasks || result?.subtasks;

  const researchEnds = timeline.filter(e => e.type === 'agent_end' && e.agent_name === 'research');
  const toolCalls = researchEnds.length > 0
    ? researchEnds.flatMap(e => e.tool_calls || [])
    : (result?.tool_calls || []);

  const analystEnd = timeline.find(e => e.type === 'agent_end' && e.agent_name === 'analyst');
  const answer = analystEnd?.synthesized_answer || result?.answer;

  // Construct context handoffs array incrementally
  const contextHandoffs = [];
  if (subtasks && subtasks.length > 0) {
    contextHandoffs.push({
      agent: 'planner',
      input: query,
      output: subtasks.join('\n'),
    });

    const researchActive = liveAgent === 'research';
    const hasEnded = timeline.some(e => e.type === 'agent_end' && e.agent_name === 'research');
    if (researchActive || hasEnded || result) {
      contextHandoffs.push({
        agent: 'research',
        input: subtasks.join(' | '),
        output: toolCalls.length > 0
          ? `${toolCalls.length} web search(es) executed`
          : (hasEnded || result) ? 'No tool calls recorded' : 'Running research...',
      });
    }
  }

  if (answer) {
    contextHandoffs.push({
      agent: 'analyst',
      input: 'Research notes from all subtasks',
      output: answer.slice(0, 300) + (answer.length > 300 ? '…' : ''),
    });
  }

  return (
    <div className="app">
      {/* ── Header ──────────────────────────────────────────────────────── */}
      <header className="app-header">
        <div className="header-brand">
          <Cpu size={28} className="brand-icon" />
          <div>
            <span className="brand-title">MARS-Lite</span>
            <span className="brand-subtitle">Multi-Agent Research System</span>
          </div>
        </div>
        <div className="header-status">
          {loading
            ? <><Activity size={14} className="pulse" style={{color:'#38bdf8'}}/> <span style={{color:'#38bdf8',fontSize:'12px'}}>{liveAgent ? `${liveAgent} running…` : 'Starting…'}</span></>
            : result
            ? <><CheckCircle2 size={14} style={{color:'#4ade80'}}/> <span style={{color:'#4ade80',fontSize:'12px'}}>Complete</span></>
            : <><div className="status-dot idle"/> <span style={{fontSize:'12px',color:'var(--text-dim)'}}>Idle</span></>
          }
        </div>
      </header>

      {/* ── Search Bar ──────────────────────────────────────────────────── */}
      <div className="search-section">
        <form className="search-form" onSubmit={handleSearch}>
          <Search size={20} className="search-icon" />
          <input
            id="query-input"
            type="text"
            className="search-input"
            placeholder="Ask anything… e.g. What is RAG in AI?"
            value={query}
            onChange={e => setQuery(e.target.value)}
            disabled={loading}
          />
          <button id="execute-btn" type="submit" className="search-btn" disabled={loading || !query.trim()}>
            {loading ? <><Activity size={14} className="pulse" /> Analyzing</> : <><Zap size={14} /> Execute</>}
          </button>
        </form>

        {/* Agent pipeline indicators */}
        <div className="pipeline-bar">
          {PIPELINE.map((stage, i) => {
            const isDone   = agentEndEvents.some(e => e.agent_name === stage.key);
            const isActive = liveAgent === stage.key;
            const meta     = AGENT_COLORS[stage.key];
            return (
              <React.Fragment key={stage.key}>
                <div className={`pipe-stage ${isDone ? 'done' : isActive ? 'active' : 'idle'}`}
                     style={{ '--c': meta.color }}>
                  <stage.icon size={13} />
                  <span>{stage.label}</span>
                  {isActive && <Activity size={11} className="pulse" />}
                  {isDone    && <CheckCircle2 size={11} />}
                </div>
                {i < PIPELINE.length - 1 && (
                  <div className={`pipe-arrow ${isDone ? 'done' : ''}`}>→</div>
                )}
              </React.Fragment>
            );
          })}
        </div>
      </div>

      {/* ── Error ───────────────────────────────────────────────────────── */}
      {error && (
        <div className="error-bar">
          <AlertCircle size={16} /> {error}
        </div>
      )}

      {/* ── Main grid ───────────────────────────────────────────────────── */}
      <div className="dashboard-grid">

        {/* ── Left column ─────────────────────────────────────────────── */}
        <div className="col-left">

          {/* 1. Timeline */}
          <Panel icon={Clock} title="Timeline" badge={timeline.length} accent="#a78bfa">
            {timeline.length === 0
              ? <div className="empty-hint"><Info size={13}/> Run a query to see events</div>
              : <>
                  <div className="timeline">
                    {timeline.map((evt, i) => (
                      <TimelineEvent
                        key={i}
                        agent={evt.agent || evt.agent_name}
                        event={evt.type}
                        timestamp={evt.timestamp || evt.start_time}
                        durationMs={evt.duration_ms}
                        tokensIn={evt.tokens_in}
                        tokensOut={evt.tokens_out}
                      />
                    ))}
                    {loading && liveAgent && (
                      <div className="timeline-row timeline-live">
                        <div className="timeline-dot pulse" style={{ background: AGENT_COLORS[liveAgent]?.color }} />
                        <div className="timeline-content">
                          <span className="timeline-agent" style={{ color: AGENT_COLORS[liveAgent]?.color }}>{liveAgent}</span>
                          <span className="timeline-event">running…</span>
                          <Activity size={12} className="pulse" style={{color:'#38bdf8'}}/>
                        </div>
                      </div>
                    )}
                  </div>
                  {timeline.length > 0 && (
                    <button className="clear-btn" onClick={handleClearTraces} disabled={loading}>
                      <Trash2 size={12} /> Clear Traces
                    </button>
                  )}
                </>
            }
          </Panel>

          {/* 2. Context Handoff */}
          <Panel icon={Layers} title="Context Handoff" badge={contextHandoffs.filter(c=>c.output).length} accent="#38bdf8">
            {contextHandoffs.length === 0
              ? <div className="empty-hint"><Info size={13}/> Handoffs appear after execution</div>
              : contextHandoffs.map((c, i) => <ContextCard key={i} {...c} />)
            }
          </Panel>

          {/* 3. Tool Calls */}
          <Panel icon={Terminal} title="Tool Calls" badge={toolCalls.length} accent="#fb923c">
            {toolCalls.length === 0
              ? <div className="empty-hint"><Info size={13}/> web_search calls appear here</div>
              : toolCalls.map((c, i) => <ToolCallCard key={i} call={c} index={i} />)
            }
          </Panel>
        </div>

        {/* ── Right column ────────────────────────────────────────────── */}
        <div className="col-right">

          {/* 4. Token Metrics */}
          <Panel icon={BarChart2} title="Token Metrics" badge={totalTokens ? fmt_tok(totalTokens) : null} accent="#4ade80">
            {agentEndEvents.length === 0
              ? <div className="empty-hint"><Info size={13}/> Token counts appear after execution</div>
              : <>
                  <div className="token-section">
                    {memoryContextTokens > 0 && (
                      <div className="token-agent-block" style={{ borderLeft: '2px solid #ec4899', paddingLeft: '8px', marginBottom: '12px' }}>
                        <div className="token-agent-name" style={{ color: '#ec4899' }}>
                          <MemoryStick size={12}/> Context Memory
                          <span className="token-model">local-cache</span>
                        </div>
                        <TokenBar label="In"    value={memoryContextTokens}    max={maxTokens} color="#ec4899" />
                        <TokenBar label="Total" value={memoryContextTokens} max={maxTokens} color="#ec4899" />
                      </div>
                    )}
                    {agentEndEvents.map((e, i) => {
                      const meta = AGENT_COLORS[e.agent_name] || DEFAULT_COLOR;
                      return (
                        <div key={i} className="token-agent-block">
                          <div className="token-agent-name" style={{ color: meta.color }}>
                            <Bot size={12}/> {e.agent_name}
                            <span className="token-model">{e.model?.split('/').pop()}</span>
                          </div>
                          <TokenBar label="In"    value={e.tokens_in}    max={maxTokens} color={meta.color} />
                          <TokenBar label="Out"   value={e.tokens_out}   max={maxTokens} color={meta.color} />
                          <TokenBar label="Total" value={e.total_tokens} max={maxTokens} color={meta.color} />
                        </div>
                      );
                    })}
                  </div>
                  <div className="token-total">
                    <Zap size={12}/> Total: <strong>{fmt_tok(totalTokens)}</strong> tokens
                  </div>
                </>
            }
          </Panel>

          {/* 5. Latency Metrics */}
          <Panel icon={Timer} title="Latency" badge={totalDuration ? fmt_ms(totalDuration) : null} accent="#f59e0b">
            {agentEndEvents.length === 0
              ? <div className="empty-hint"><Info size={13}/> Latency data appears after execution</div>
              : <>
                  {agentEndEvents.map((e, i) => {
                    const meta = AGENT_COLORS[e.agent_name] || DEFAULT_COLOR;
                    const pct  = totalDuration > 0 ? (e.duration_ms / totalDuration) * 100 : 0;
                    return (
                      <div key={i} className="latency-row">
                        <span className="latency-agent" style={{ color: meta.color }}>{e.agent_name}</span>
                        <div className="latency-bar-track">
                          <div className="latency-bar-fill" style={{ width: `${pct}%`, background: meta.color }} />
                        </div>
                        <span className="latency-value">{fmt_ms(e.duration_ms)}</span>
                      </div>
                    );
                  })}
                  <div className="latency-total">
                    <TrendingUp size={12}/> Total: <strong>{fmt_ms(totalDuration)}</strong>
                  </div>
                </>
            }
          </Panel>

          {/* 6. Memory Panel */}
          <Panel icon={MemoryStick} title="Memory" accent="#ec4899">
            {!memory?.last_query
              ? <div className="empty-hint"><Info size={13}/> Memory stores the last query context</div>
              : <>
                  <div className="memory-grid">
                    <div className="mem-item"><span className="mem-label">Last Query</span><span className="mem-value">{memory.last_query}</span></div>
                    <div className="mem-item"><span className="mem-label">Category</span><span className="mem-value mem-tag">{memory.last_category}</span></div>
                    {memory.last_budget && <div className="mem-item"><span className="mem-label">Budget</span><span className="mem-value">{memory.last_budget}</span></div>}
                    <div className="mem-item"><span className="mem-label">Stored At</span><span className="mem-value">{ts_hms(memory.timestamp)}</span></div>
                    {memory.history?.length > 0 && (
                      <div className="mem-history">
                        <span className="mem-label">History ({memory.history.length})</span>
                        {memory.history.slice(0, 5).map((h, i) => (
                          <div key={i} className="mem-history-item">
                            <span className="mem-hist-cat">{h.last_category}</span>
                            <span className="mem-hist-q">{h.last_query?.slice(0, 50)}{h.last_query?.length > 50 ? '…' : ''}</span>
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                  <button className="clear-btn" onClick={handleClearMemory} disabled={loading}>
                    <Trash2 size={12} /> Clear Memory
                  </button>
                </>
            }
          </Panel>

          {/* 7. Evaluation Panel */}
          <Panel icon={ListChecks} title="Evaluation" badge={result?.evaluation ? `${result.evaluation.score}/100` : null} accent="#a78bfa">
            {!result?.evaluation
              ? <div className="empty-hint"><Info size={13}/> Evaluation runs after completion</div>
              : <>
                  <div className="eval-score-ring" style={{ '--score': result.evaluation.score }}>
                    <div className="eval-score-num">{result.evaluation.score}</div>
                    <div className="eval-score-label">/ 100</div>
                  </div>
                  <div className="eval-criteria">
                    <EvalCriterion label="Workflow Completed" passed={result.evaluation.workflow_completed} />
                    <EvalCriterion label="Tool Called"        passed={result.evaluation.tool_called} />
                    <EvalCriterion label="Task Completed"     passed={result.evaluation.task_completed} />
                  </div>
                  {result.evaluation.details && (
                    <div className="eval-details">
                      <span className="mem-label">Details</span>
                      <div className="eval-detail-row"><span>Agents seen</span><span>{result.evaluation.details.agents_seen?.join(', ')}</span></div>
                      <div className="eval-detail-row"><span>Tool calls</span><span>{result.evaluation.details.tool_calls_count}</span></div>
                      <div className="eval-detail-row"><span>Answer length</span><span>{result.evaluation.details.answer_length} chars</span></div>
                    </div>
                  )}
                </>
            }
          </Panel>
        </div>
      </div>

      {/* ── Answer ──────────────────────────────────────────────────────── */}
      {answer && (
        <div className="answer-section">
          <Panel icon={FlaskConical} title="Research Answer" accent="#4ade80" defaultOpen={true}>
            <div className="markdown-body">
              <ReactMarkdown>{answer}</ReactMarkdown>
            </div>
          </Panel>
        </div>
      )}

      {/* ── Loading empty state ──────────────────────────────────────────── */}
      {!result && !loading && !error && (
        <div className="empty-state">
          <Cpu size={56} className="empty-icon pulse-slow" />
          <h2>MARS-Lite Dashboard</h2>
          <p>Enter a query and click Execute to watch the agent pipeline run in real time.</p>
          <div className="empty-hints">
            <span>Try: <em>What is RAG in AI?</em></span>
            <span>Try: <em>How does LangGraph work?</em></span>
            <span>Try: <em>Latest advances in AI agents 2025</em></span>
          </div>
        </div>
      )}
    </div>
  );
}
