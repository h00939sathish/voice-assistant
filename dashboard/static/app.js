/* ── Store ────────────────────────────────────── */
const store = {
  state: 'idle',
  messages: [],
  thinking: null,
  metrics: { cpu: 0, ram: 0, gpu: 0, vram: 0, disk: 0, network: 0 },
  providers: [],
  memory: { name: 'Sathish', projects: [], recent: [], pinned: [] },
  agentLog: [],
  automations: [],
  alerts: [],
  model: { name: '—', provider: '—', context: '—', latency: '—', tokens: '—' },
  listeners: new Set(),
};

function setState(key, val) {
  if (typeof key === 'object') {
    Object.assign(store, key);
  } else {
    store[key] = val;
  }
  store.listeners.forEach(fn => fn());
}

function subscribe(fn) {
  store.listeners.add(fn);
  return () => store.listeners.delete(fn);
}

/* ── SSE Connection ───────────────────────────── */
function connectSSE() {
  const es = new EventSource('/stream');
  es.onmessage = e => {
    try {
      const data = JSON.parse(e.data);
      if (data.state) setState('state', data.state);
      if (data.metrics) setState('metrics', data.metrics);
      if (data.providers) setState('providers', data.providers);
      if (data.memory) setState('memory', data.memory);
      if (data.agent_log) {
        const log = store.agentLog.concat(data.agent_log).slice(-50);
        setState('agentLog', log);
      }
      if (data.automation) {
        const list = store.automations.filter(a => a.id !== data.automation.id).concat(data.automation);
        setState('automations', list);
      }
      if (data.alert) {
        const alerts = store.alerts.concat(data.alert).slice(-20);
        setState('alerts', alerts);
      }
      if (data.transcript) {
        const msg = { role: data.transcript.speaker === 'user' ? 'user' : 'assistant', text: data.transcript.text, ts: Date.now() };
        setState('messages', store.messages.concat(msg).slice(-100));
      }
    } catch {}
  };
  es.onerror = () => setTimeout(connectSSE, 3000);
}

/* ── API helpers ──────────────────────────────── */
async function api(path, body) {
  const opts = { headers: { 'Content-Type': 'application/json' } };
  if (body) { opts.method = 'POST'; opts.body = JSON.stringify(body); }
  const r = await fetch(path, opts);
  return r.json();
}

async function sendMessage(text) {
  if (!text.trim()) return;
  const msg = { role: 'user', text: text.trim(), ts: Date.now() };
  setState('messages', store.messages.concat(msg));
  document.getElementById('chat-input').value = '';
  setState('thinking', { text: 'Thinking...' });
  try {
    const res = await api('/api/chat', { message: text.trim(), speak: false });
    setState('thinking', null);
    if (res.ok) {
      const reply = { role: 'assistant', text: res.response, ts: Date.now() };
      setState('messages', store.messages.concat(reply));
    } else {
      const err = { role: 'assistant', text: `⚠️ Error: ${res.error || 'Unknown error'}`, ts: Date.now() };
      setState('messages', store.messages.concat(err));
    }
  } catch (e) {
    setState('thinking', null);
    const err = { role: 'assistant', text: `⚠️ Connection error: ${e.message}`, ts: Date.now() };
    setState('messages', store.messages.concat(err));
  }
}

async function fetchInitial() {
  try {
    const [status, metrics, memory, automations, alerts, agentLog] = await Promise.all([
      api('/api/status'),
      api('/api/operator'),
      api('/api/memory'),
      api('/api/automations'),
      api('/api/alerts'),
      api('/api/agent/log'),
    ]);
    if (status.state) setState('state', status.state);
    if (metrics) setState('metrics', { cpu: metrics.cpu || 0, ram: metrics.ram || 0, gpu: metrics.gpu || 0, vram: metrics.vram || 0, disk: metrics.disk || 0, network: metrics.network || 0 });
    if (memory) setState('memory', memory);
    if (Array.isArray(automations)) setState('automations', automations);
    if (Array.isArray(alerts)) setState('alerts', alerts);
    if (Array.isArray(agentLog)) setState('agentLog', agentLog);
  } catch {}
}

/* ── Orb Canvas ───────────────────────────────── */
function initOrb() {
  const canvas = document.getElementById('orb-canvas');
  const ctx = canvas.getContext('2d');
  let w, h, cx, cy, radius = 40, phase = 0, audioLevel = 0, smoothAudio = 0;
  let particles = [], hover = false;

  function resize() {
    const rect = canvas.parentElement.getBoundingClientRect();
    const size = Math.min(rect.width, 140);
    dpr = window.devicePixelRatio || 1;
    canvas.width = size * dpr;
    canvas.height = size * dpr;
    canvas.style.width = size + 'px';
    canvas.style.height = size + 'px';
    ctx.scale(dpr, dpr);
    w = size; h = size; cx = w / 2; cy = h / 2;
    radius = w * 0.32;
  }

  let dpr = 1;
  resize();
  window.addEventListener('resize', resize);

  canvas.addEventListener('mouseenter', () => hover = true);
  canvas.addEventListener('mouseleave', () => hover = false);

  function burst(n) {
    for (let i = 0; i < n; i++) {
      const a = Math.random() * Math.PI * 2;
      const spd = 0.5 + Math.random() * 1.5;
      const life = 0.3 + Math.random() * 0.7;
      const size = 1 + Math.random() * 3;
      const hue = store.state === 'listening' ? 210 : store.state === 'speaking' ? 170 : store.state === 'error' ? 0 : store.state === 'thinking' ? 45 : 220;
      particles.push({ x: cx, y: cy, vx: Math.cos(a) * spd, vy: Math.sin(a) * spd, life, maxLife: life, size, r: hue, g: hue + 40, b: 255, a: 1 });
    }
  }

  let lastBurst = 0;
  function updateParticles(dt) {
    for (let i = particles.length - 1; i >= 0; i--) {
      const p = particles[i];
      p.x += p.vx; p.y += p.vy;
      p.vx *= 0.97; p.vy *= 0.97;
      p.life -= dt;
      p.a = Math.max(0, p.life / p.maxLife);
      if (p.life <= 0) particles.splice(i, 1);
    }
    if (store.state === 'listening' && Date.now() - lastBurst > 200) { burst(2); lastBurst = Date.now(); }
    if (store.state === 'speaking' && Date.now() - lastBurst > 300) { burst(3); lastBurst = Date.now(); }
    if (store.state === 'error' && Date.now() - lastBurst > 400) { burst(5); lastBurst = Date.now(); }
  }

  function getColors(state) {
    switch (state) {
      case 'listening': return { base: [59, 130, 246], glow: [59, 130, 246, 0.3], pulse: 0.7 };
      case 'thinking': return { base: [245, 158, 11], glow: [245, 158, 11, 0.25], pulse: 0.5 };
      case 'speaking': return { base: [45, 212, 191], glow: [45, 212, 191, 0.25], pulse: 0.8 };
      case 'error': return { base: [239, 68, 68], glow: [239, 68, 68, 0.3], pulse: 0.4 };
      default: return { base: [100, 100, 130], glow: [100, 100, 130, 0.15], pulse: 0.3 };
    }
  }

  let time = 0;
  function draw(t) {
    const dt = Math.min((t - (time || t)) / 1000, 0.05);
    time = t;
    phase += dt * (store.state === 'thinking' ? 1.5 : store.state === 'listening' ? 0.8 : store.state === 'speaking' ? 1.2 : 0.4);
    smoothAudio += (audioLevel - smoothAudio) * 0.1;

    ctx.clearRect(0, 0, w, h);
    const colors = getColors(store.state);
    const pulse = 1 + Math.sin(phase * 2) * colors.pulse * 0.12;
    const r = radius * pulse + smoothAudio * 15;

    // Outer glow
    const grad = ctx.createRadialGradient(cx, cy, r * 0.2, cx, cy, r * 2);
    grad.addColorStop(0, `rgba(${colors.glow[0]},${colors.glow[1]},${colors.glow[2]},${colors.glow[3] || 0.2})`);
    grad.addColorStop(0.5, `rgba(${colors.glow[0]},${colors.glow[1]},${colors.glow[2]},${(colors.glow[3] || 0.2) * 0.4})`);
    grad.addColorStop(1, 'transparent');
    ctx.fillStyle = grad;
    ctx.beginPath(); ctx.arc(cx, cy, r * 2, 0, Math.PI * 2); ctx.fill();

    // Core
    const core = ctx.createRadialGradient(cx - r * 0.2, cy - r * 0.2, 0, cx, cy, r);
    core.addColorStop(0, `rgba(${colors.base[0]},${colors.base[1]},${colors.base[2]},0.9)`);
    core.addColorStop(0.4, `rgba(${colors.base[0]},${colors.base[1]},${colors.base[2]},0.6)`);
    core.addColorStop(0.8, `rgba(${colors.base[0]},${colors.base[1]},${colors.base[2]},0.2)`);
    core.addColorStop(1, 'rgba(0,0,0,0)');
    ctx.fillStyle = core;
    ctx.beginPath(); ctx.arc(cx, cy, r, 0, Math.PI * 2); ctx.fill();

    // Bright center
    const bright = ctx.createRadialGradient(cx - r * 0.15, cy - r * 0.15, 0, cx, cy, r * 0.5);
    bright.addColorStop(0, `rgba(255,255,255,${0.3 + smoothAudio * 0.2})`);
    bright.addColorStop(1, 'transparent');
    ctx.fillStyle = bright;
    ctx.beginPath(); ctx.arc(cx, cy, r * 0.5, 0, Math.PI * 2); ctx.fill();

    // Rings
    for (let i = 0; i < 3; i++) {
      const ringR = r * (0.7 + i * 0.25) + Math.sin(phase * 1.5 + i * 1.2) * 3;
      ctx.strokeStyle = `rgba(${colors.base[0]},${colors.base[1]},${colors.base[2]},${0.1 - i * 0.02})`;
      ctx.lineWidth = 1;
      ctx.beginPath(); ctx.arc(cx, cy, ringR, 0, Math.PI * 2); ctx.stroke();
    }

    // Particles
    updateParticles(dt);
    for (const p of particles) {
      ctx.globalAlpha = p.a;
      ctx.fillStyle = `rgba(${p.r},${p.g},${p.b},${p.a})`;
      ctx.beginPath(); ctx.arc(p.x, p.y, p.size * p.a, 0, Math.PI * 2); ctx.fill();
    }
    ctx.globalAlpha = 1;

    // Hover glow
    if (hover) {
      ctx.fillStyle = `rgba(${colors.base[0]},${colors.base[1]},${colors.base[2]},0.05)`;
      ctx.beginPath(); ctx.arc(cx, cy, r * 1.5, 0, Math.PI * 2); ctx.fill();
    }

    requestAnimationFrame(draw);
  }
  requestAnimationFrame(draw);

  // Expose for audio level
  window.__orb = { setAudio: l => audioLevel = l };
}

/* ── Polling ──────────────────────────────────── */
setInterval(async () => {
  try {
    const status = await api('/api/status');
    if (status.state) setState('state', status.state);
  } catch {}
}, 5000);

/* ── React Components ─────────────────────────── */
const { useState, useEffect, useRef, useCallback } = React;

function App() {
  const [, forceUpdate] = useState(0);
  useEffect(() => subscribe(() => forceUpdate(n => n + 1)), []);

  return (
    <div id="root">
      <LeftPanel />
      <CenterPanel />
      <RightPanel />
    </div>
  );
}

/* ── Left Panel ──────────────────── */
function LeftPanel() {
  const state = store.state;
  return (
    <div className="panel panel-left">
      <OrbSection state={state} />
      <VoiceStatus state={state} />
      <CurrentObjective state={state} />
      <TaskQueue state={state} />
    </div>
  );
}

function OrbSection({ state }) {
  const badgeClass = ['idle','listening','thinking','speaking','error'].includes(state) ? state : 'idle';
  const badgeLabel = state.charAt(0).toUpperCase() + state.slice(1);
  return (
    <div className="glass" style={{ textAlign: 'center', padding: '16px 14px 12px' }}>
      <div id="orb-container">
        <div className="orb-ring r1" />
        <div className="orb-ring r2" />
        <canvas id="orb-canvas" />
      </div>
      <div style={{ marginTop: 6, display: 'flex', justifyContent: 'center', gap: 6, alignItems: 'center' }}>
        <span className={`badge ${badgeClass}`}>{badgeLabel}</span>
      </div>
    </div>
  );
}

function VoiceStatus({ state }) {
  const connected = state !== 'error';
  return (
    <div className="glass">
      <div className="sec-title"><span className="dot" />Voice Status</div>
      <div className="status-grid">
        <span className="label">Wake Word</span><span className="value">Jarvis</span>
        <span className="label">Microphone</span><span className={`value ${connected ? 'online' : 'offline'}`}>{connected ? 'Connected' : 'Disconnected'}</span>
        <span className="label">TTS</span><span className={`value ${connected ? 'online' : 'offline'}`}>{connected ? 'Online' : 'Offline'}</span>
        <span className="label">STT</span><span className={`value ${connected ? 'online' : 'offline'}`}>{connected ? 'Online' : 'Offline'}</span>
        <span className="label">Current State</span><span className={`value ${state}`}>{state}</span>
      </div>
    </div>
  );
}

function CurrentObjective({ state }) {
  const objectives = {
    idle: 'Monitoring system...',
    listening: 'Listening for commands...',
    thinking: 'Processing request...',
    speaking: 'Responding...',
    error: 'Error — check alerts',
  };
  return (
    <div className="glass">
      <div className="sec-title"><span className="dot" />Objective</div>
      <div className="objective">
        <span className="label">Current Focus</span>
        <span className={state === 'idle' ? 'idle' : 'active'}>{objectives[state] || 'Idle'}</span>
      </div>
    </div>
  );
}

function TaskQueue() {
  const tasks = [
    { label: 'Research trading opportunities', status: 'active' },
    { label: 'Monitor Railway deployment', status: 'pending' },
    { label: 'Daily security scan', status: 'scheduled' },
    { label: 'System backup', status: 'scheduled' },
  ];
  return (
    <div className="glass" style={{ flex: 1 }}>
      <div className="sec-title"><span className="dot" />Task Queue</div>
      <div>
        {tasks.map((t, i) => (
          <div className="task-item" key={i}>
            <span className={`task-dot ${t.status}`} />
            <span className="task-label">{t.label}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

/* ── Center Panel ────────────────── */
function CenterPanel() {
  return (
    <div className="panel-center">
      <Messages />
      <ThinkingIndicator />
      <QuickActions />
      <InputArea />
    </div>
  );
}

function Messages() {
  const msgs = store.messages;
  const endRef = useRef(null);
  useEffect(() => { endRef.current?.scrollIntoView({ behavior: 'smooth' }); }, [msgs.length]);

  if (msgs.length === 0) {
    return (
      <div id="messages">
        <div className="welcome">
          <h2>Welcome to JARVIS</h2>
          <p>Your AI operating system. Ask me anything.</p>
          <p style={{ marginTop: 8, fontSize: 10, color: 'var(--muted)' }}>
            ⌘K to search &bull; Voice commands always active
          </p>
        </div>
      </div>
    );
  }

  return (
    <div id="messages">
      {msgs.map((m, i) => (
        <div className={`msg ${m.role}`} key={i}>
          <div className="label">{m.role === 'user' ? 'You' : 'JARVIS'}</div>
          <div>{m.text}</div>
        </div>
      ))}
      <div ref={endRef} />
    </div>
  );
}

function ThinkingIndicator() {
  const t = store.thinking;
  if (!t) return null;
  return (
    <div className="thinking">
      <span className="dot" />
      <span className="dot" style={{ animationDelay: '0.2s' }} />
      <span className="dot" style={{ animationDelay: '0.4s' }} />
      <span style={{ marginLeft: 6 }}>{t.text}</span>
    </div>
  );
}

function QuickActions() {
  const actions = [
    { label: 'Research', action: 'Research' },
    { label: 'Code', action: 'Write code for' },
    { label: 'Analyze', action: 'Analyze' },
    { label: 'Automate', action: 'Create automation for' },
    { label: 'Search Memory', action: 'Search memory for' },
    { label: 'Monitor', action: 'Monitor' },
    { label: 'Create Task', action: 'Create task:' },
  ];

  return (
    <div className="quick-actions">
      {actions.map(a => (
        <button className="qck" key={a.label} onClick={() => {
          const input = document.getElementById('chat-input');
          input.value = a.action + ' ';
          input.focus();
        }}>
          {a.label}
        </button>
      ))}
    </div>
  );
}

function InputArea() {
  const [text, setText] = useState('');
  const handleSend = () => { sendMessage(text); setText(''); };
  const handleKey = e => {
    if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); handleSend(); }
  };

  return (
    <div id="input-area">
      <div className="input-wrap">
        <textarea
          id="chat-input"
          placeholder="Ask JARVIS anything…"
          value={text}
          onChange={e => setText(e.target.value)}
          onKeyDown={handleKey}
          rows={1}
        />
        <div className="input-actions">
          <button className="ia-btn" title="Voice" onClick={() => api('/api/wake', {})}>🎤</button>
          <button className="ia-btn" title="Attach">📎</button>
          <button className="ia-btn send" onClick={handleSend} disabled={!text.trim()}>↵</button>
        </div>
      </div>
    </div>
  );
}

/* ── Right Panel ─────────────────── */
function RightPanel() {
  return (
    <div className="panel panel-right">
      <SystemStatus />
      <ActiveModel />
      <MemoryPanel />
      <AgentFeed />
      <Automations />
      <Alerts />
    </div>
  );
}

function SystemStatus() {
  const m = store.metrics || {};
  const providers = store.providers.length > 0 ? store.providers : [];
  const defaultProviders = [
    { name: 'Ollama', status: 'offline' },
    { name: 'OpenRouter', status: 'offline' },
    { name: 'Gemini', status: 'offline' },
    { name: 'Groq', status: 'offline' },
    { name: 'NVIDIA', status: 'offline' },
  ];

  const bars = [
    { label: 'CPU', value: m.cpu || 0, color: m.cpu > 80 ? 'var(--red)' : m.cpu > 50 ? 'var(--amber)' : 'var(--blue)' },
    { label: 'RAM', value: m.ram || 0, color: m.ram > 80 ? 'var(--red)' : m.ram > 50 ? 'var(--amber)' : 'var(--blue)' },
    { label: 'GPU', value: m.gpu || 0, color: m.gpu > 80 ? 'var(--red)' : m.gpu > 50 ? 'var(--amber)' : 'var(--blue)' },
    { label: 'VRAM', value: m.vram || 0, color: m.vram > 80 ? 'var(--red)' : m.vram > 50 ? 'var(--amber)' : 'var(--blue)' },
    { label: 'Disk', value: m.disk || 0, color: m.disk > 80 ? 'var(--red)' : m.disk > 50 ? 'var(--amber)' : 'var(--blue)' },
    { label: 'Net', value: m.network || 0, color: 'var(--blue)' },
  ];

  return (
    <div className="rp-section">
      <div className="glass">
        <div className="sec-title"><span className="dot" />System Status</div>
        {bars.map(b => (
          <div className="metric" key={b.label}>
            <span className="metric-label">{b.label}</span>
            <div className="metric-bar">
              <div className="metric-bar-fill" style={{ width: Math.min(b.value, 100) + '%', background: b.color }} />
            </div>
            <span className="metric-value">{Math.round(b.value)}%</span>
          </div>
        ))}
        <div className="provider-list">
          {(providers.length > 0 ? providers : defaultProviders).map(p => (
            <span className={`prov-item ${p.status}`} key={p.name}>
              <span className="prov-dot" />{p.name}
            </span>
          ))}
        </div>
      </div>
    </div>
  );
}

function ActiveModel() {
  const model = store.model;
  return (
    <div className="rp-section">
      <div className="glass">
        <div className="sec-title"><span className="dot" />Active Model</div>
        {model.name && model.name !== '—' ? (
          <div className="model-card">
            <div className="model-stat"><span className="val">{model.name}</span><span className="lbl">Model</span></div>
            <div className="model-stat"><span className="val">{model.provider}</span><span className="lbl">Provider</span></div>
            <div className="model-stat"><span className="val">{model.context}</span><span className="lbl">Context</span></div>
            <div className="model-stat"><span className="val">{model.latency}</span><span className="lbl">Latency</span></div>
            <div className="model-stat"><span className="val">{model.tokens}</span><span className="lbl">Tokens</span></div>
          </div>
        ) : (
          <div className="empty-state">
            <div className="icon">⚡</div>
            <div>No active model</div>
          </div>
        )}
      </div>
    </div>
  );
}

function MemoryPanel() {
  const mem = store.memory || {};
  return (
    <div className="rp-section">
      <div className="glass">
        <div className="sec-title"><span className="dot" />Memory</div>
        <div className="mem-section">
          <div className="mem-label">Name</div>
          <div className="mem-value">{mem.name || '—'}</div>
        </div>
        <div className="mem-section">
          <div className="mem-label">Projects</div>
          <div>{(mem.projects || ['JARVIS']).map((p, i) => <span className="mem-tag" key={i}>{p}</span>)}</div>
        </div>
        <div className="mem-section">
          <div className="mem-label">Recent</div>
          {(mem.recent || ['System initialized']).slice(0, 3).map((r, i) => (
            <div className="mem-item" key={i}>{typeof r === 'string' ? r : r.text || JSON.stringify(r)}</div>
          ))}
        </div>
      </div>
    </div>
  );
}

function AgentFeed() {
  const log = store.agentLog;
  return (
    <div className="rp-section">
      <div className="glass">
        <div className="sec-title"><span className="dot" />Agent Activity</div>
        <div style={{ maxHeight: 120, overflowY: 'auto' }}>
          {log.length === 0 ? (
            <div className="empty-state">
              <div className="icon">◇</div>
              <div>No recent activity</div>
            </div>
          ) : (
            log.slice(-15).reverse().map((item, i) => (
              <div className="feed-item" key={i}>
                <span className="ts">{item.timestamp || '--:--'}</span>
                <span>{item.message || JSON.stringify(item)}</span>
              </div>
            ))
          )}
        </div>
      </div>
    </div>
  );
}

function Automations() {
  const auto = store.automations;
  return (
    <div className="rp-section">
      <div className="glass">
        <div className="sec-title"><span className="dot" />Automations</div>
        {auto.length === 0 ? (
          <div className="empty-state">
            <div className="icon">⚙</div>
            <div>No automations configured</div>
          </div>
        ) : (
          auto.slice(0, 6).map(a => (
            <div className="auto-item" key={a.id || a.name}>
              <span className={`auto-status ${a.status || 'scheduled'}`}>{a.status || 'scheduled'}</span>
              <span className="auto-name">{a.name}</span>
            </div>
          ))
        )}
      </div>
    </div>
  );
}

function Alerts() {
  const alerts = store.alerts;
  if (alerts.length === 0) {
    return (
      <div className="rp-section">
        <div className="glass" style={{ borderColor: 'rgba(34,197,94,0.2)' }}>
          <div className="sec-title"><span className="dot" style={{ background: 'var(--green)' }} />Alerts</div>
          <div className="empty-state" style={{ color: 'var(--green)' }}>
            <div>✓ All systems operational</div>
          </div>
        </div>
      </div>
    );
  }
  return (
    <div className="rp-section">
      <div className="glass">
        <div className="sec-title"><span className="dot" style={{ background: alerts.some(a => a.type === 'critical' || a.type === 'error') ? 'var(--red)' : 'var(--amber)' }} />Alerts</div>
        {alerts.slice(0, 5).map((a, i) => (
          <div className={`alert-item ${a.type || 'warning'}`} key={i}>
            <span className="alert-icon">{a.type === 'error' || a.type === 'critical' ? '⚠' : '!'}</span>
            <span className="alert-msg">{a.message}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

/* ── Mount ────────────────────────────────────── */
// Babel standalone evaluates this after DOM is ready, so no DOMContentLoaded needed
(function boot() {
  const root = document.getElementById('root');
  if (root) ReactDOM.createRoot(root).render(React.createElement(App));
  initOrb();
  connectSSE();
  fetchInitial();
})();
