/**
 * Buddy WebSocket Client
 * 
 * Connect to Buddy's API server and communicate via WebSocket.
 * Usage: Include this script in AionUI or any frontend.
 * 
 * Connect: ws://localhost:8765/ws
 * 
 * States: IDLE, LISTENING, THINKING, SPEAKING, ERROR
 */

class BuddyClient {
  constructor(url = 'ws://localhost:8765/ws') {
    this.url = url;
    this.ws = null;
    this.listeners = new Map();
    this.reconnectAttempts = 0;
    this.maxReconnectAttempts = 5;
    this.state = 'IDLE';
    this.stateHistory = [];
    this.stateCallbacks = {
      IDLE: [],
      LISTENING: [],
      THINKING: [],
      SPEAKING: [],
      ERROR: []
    };
  }

  /** Connect to Buddy */
  connect() {
    return new Promise((resolve, reject) => {
      this.ws = new WebSocket(this.url);
      
      this.ws.onopen = () => {
        console.log('[Buddy] Connected');
        this.reconnectAttempts = 0;
        resolve();
      };
      
      this.ws.onmessage = (event) => {
        const data = JSON.parse(event.data);
        const type = data.type;
        
        // Handle state changes
        if (type === 'state_change') {
          this._handleStateChange(data.state, data.previous);
          return;
        }
        
        // Handle wake triggered
        if (type === 'wake_triggered') {
          this._handleStateChange('LISTENING', this.state);
          return;
        }
        
        const callbacks = this.listeners.get(type) || [];
        callbacks.forEach(cb => cb(data));
      };
      
      this.ws.onerror = (err) => console.error('[Buddy] Error:', err);
      
      this.ws.onclose = () => {
        console.log('[Buddy] Disconnected');
        this._reconnect();
      };
    });
  }

  /** Handle state change */
  _handleStateChange(newState, previousState) {
    this.state = newState;
    this.stateHistory.push({
      from: previousState,
      to: newState,
      timestamp: Date.now()
    });
    
    // Notify state listeners
    const callbacks = this.stateCallbacks[newState] || [];
    callbacks.forEach(cb => cb(newState, previousState));
    
    // Notify general listeners
    const allCallbacks = this.listeners.get('state') || [];
    allCallbacks.forEach(cb => cb(newState, previousState));
  }

  /** Reconnect on disconnect */
  _reconnect() {
    if (this.reconnectAttempts < this.maxReconnectAttempts) {
      this.reconnectAttempts++;
      setTimeout(() => this.connect(), 1000 * this.reconnectAttempts);
    }
  }

  /** Send message to Buddy */
  send(message) {
    if (this.ws && this.ws.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify(message));
    }
  }

  /** Listen for events */
  on(eventType, callback) {
    if (!this.listeners.has(eventType)) {
      this.listeners.set(eventType, []);
    }
    this.listeners.get(eventType).push(callback);
  }

  /** Listen for state changes */
  onState(state, callback) {
    if (this.stateCallbacks[state]) {
      this.stateCallbacks[state].push(callback);
    }
  }

  /** Current state getters */
  getState() { return this.state; }
  isIdle() { return this.state === 'IDLE'; }
  isListening() { return this.state === 'LISTENING'; }
  isThinking() { return this.state === 'THINKING'; }
  isSpeaking() { return this.state === 'SPEAKING'; }
  isError() { return this.state === 'ERROR'; }

  /** Get state history */
  getStateHistory() { return this.stateHistory; }

  /** Make Buddy speak */
  speak(text) {
    this.send({ type: 'speak', text });
  }

  /** Chat with LLM (streaming) */
  chat(message) {
    return new Promise((resolve) => {
      const chunks = [];
      this.on('chat_chunk', (data) => chunks.push(data.content));
      this.on('chat_done', () => resolve(chunks.join('')));
      this.send({ type: 'chat_stream', message });
    });
  }

  /** Start wake word listening */
  startWakeWord() {
    this.send({ type: 'wake_word_listen' });
  }

  /** Stop wake word */
  stopWakeWord() {
    this.send({ type: 'wake_word_stop' });
  }

  /** Desktop action */
  desktopAction(action, target, params) {
    this.send({ type: 'desktop_action', action, target, params });
  }

  /** Ping */
  ping() {
    this.send({ type: 'ping' });
  }

  /** Check if connected */
  isConnected() {
    return this.ws && this.ws.readyState === WebSocket.OPEN;
  }
}

// Export for module usage
if (typeof module !== 'undefined') module.exports = BuddyClient;
if (typeof window !== 'undefined') window.BuddyClient = BuddyClient;