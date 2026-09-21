import { EventType, WSEvent } from '../types/events';

type EventCallback = (event: WSEvent) => void;

class WebSocketClient {
  private socket: WebSocket | null = null;
  private url = 'ws://127.0.0.1:8000/ws/events';
  private listeners: Map<string, Set<EventCallback>> = new Map();
  private reconnectTimeout: any = null;
  private pingInterval: any = null;
  private isExplicitlyClosed = false;

  public connect() {
    this.isExplicitlyClosed = false;
    if (this.socket && (this.socket.readyState === WebSocket.OPEN || this.socket.readyState === WebSocket.CONNECTING)) {
      return;
    }

    try {
      this.socket = new WebSocket(this.url);

      this.socket.onopen = () => {
        this.emit('connection', { type: 'connection', payload: { connected: true }, timestamp: Date.now() });
        this.startPing();
      };

      this.socket.onmessage = (event) => {
        try {
          const wsEvent: any = JSON.parse(event.data);
          const eventName = wsEvent.event || wsEvent.type;
          if (eventName) {
            this.emit(eventName, wsEvent);
          }
          if (wsEvent.type && wsEvent.type !== eventName) {
            this.emit(wsEvent.type, wsEvent);
          }
          this.emit('*', wsEvent);
        } catch (e) {
          console.error('Failed to parse WebSocket message', e);
        }
      };

      this.socket.onerror = (error) => {
        console.warn('WebSocket error', error);
      };

      this.socket.onclose = () => {
        this.stopPing();
        this.emit('connection', { type: 'connection', payload: { connected: false }, timestamp: Date.now() });
        if (!this.isExplicitlyClosed) {
          this.reconnectTimeout = setTimeout(() => this.connect(), 3000);
        }
      };
    } catch (err) {
      console.warn('Could not establish WebSocket connection', err);
      this.reconnectTimeout = setTimeout(() => this.connect(), 3000);
    }
  }

  public disconnect() {
    this.isExplicitlyClosed = true;
    clearTimeout(this.reconnectTimeout);
    this.stopPing();
    if (this.socket) {
      this.socket.close();
      this.socket = null;
    }
  }

  public send(type: string, payload: any = {}) {
    if (this.socket && this.socket.readyState === WebSocket.OPEN) {
      this.socket.send(JSON.stringify({ type, payload }));
    }
  }

  public subscribe(eventType: EventType | '*' | 'connection' | string, callback: EventCallback): () => void {
    if (!this.listeners.has(eventType)) {
      this.listeners.set(eventType, new Set());
    }
    this.listeners.get(eventType)!.add(callback);

    return () => {
      this.listeners.get(eventType)?.delete(callback);
    };
  }

  private emit(eventType: string, event: WSEvent | any) {
    const callbacks = this.listeners.get(eventType);
    if (callbacks) {
      callbacks.forEach((cb) => {
        try {
          cb(event);
        } catch (e) {
          console.error(`Error in WS callback for ${eventType}`, e);
        }
      });
    }
  }

  private startPing() {
    this.stopPing();
    this.pingInterval = setInterval(() => {
      this.send('ping');
    }, 20000);
  }

  private stopPing() {
    if (this.pingInterval) {
      clearInterval(this.pingInterval);
      this.pingInterval = null;
    }
  }
}

export const wsClient = new WebSocketClient();
