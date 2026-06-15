export interface SnapshotPayload {
  symbol: string
  snapshot: {
    symbol: string
    name: string
    currency?: string
    price: number
    open?: number
    high?: number
    low?: number
    volume?: number
    turnover?: number
    updatedAt: string
    tradeDate: string
  }
  minute_bars: MarketBar[]
  alerts: TradeAlert[]
  broker_queue: {
    ask: QueueLevel[]
    bid: QueueLevel[]
    sourceDate?: string
    historical?: boolean
    fallback?: boolean
  }
  freshness: Record<string, unknown>
}

export interface MarketBar {
  timestamp: string
  price: number
  open: number
  high: number
  low: number
  close: number
  volume: number
  turnover: number
}

export interface TradeAlert {
  id: string
  timestamp: string
  tradeDate: string
  price: number
  volume: number
  turnover: number
  side: string
  thresholdVolume?: number
}

export interface QueueLevel {
  id: string
  side: 'ask' | 'bid'
  position: number
  gear: number
  price: number
  volume: number
  brokerCount: number
  brokers: Array<{ brokerCode: string; displayName: string; volume: number }>
}

export interface DeltaPayload {
  delta_type?: 'minute_bar' | 'trade_tick' | 'broker_queue'
  minute_bar?: MarketBar
  alert?: TradeAlert | null
  broker_queue?: SnapshotPayload['broker_queue']
}

interface ClientHandlers {
  onStatus?: (status: 'open' | 'closed' | 'error') => void
  onSnapshot?: (symbol: string, payload: SnapshotPayload) => void
  onDelta?: (symbol: string, payload: DeltaPayload) => void
}

export class MarketFeedClient {
  private ws: WebSocket | null = null
  private reconnectTimer: number | null = null
  private closedByClient = false
  private pendingCommands: string[] = []

  constructor(
    private readonly url: string,
    private readonly handlers: ClientHandlers = {},
  ) {}

  connect() {
    this.closedByClient = false
    if (this.ws?.readyState === WebSocket.OPEN || this.ws?.readyState === WebSocket.CONNECTING) {
      return
    }
    this.ws = new WebSocket(this.url)
    this.ws.onopen = () => {
      this.handlers.onStatus?.('open')
      this.flushPending()
    }
    this.ws.onerror = () => this.handlers.onStatus?.('error')
    this.ws.onclose = () => {
      this.handlers.onStatus?.('closed')
      if (!this.closedByClient) {
        this.reconnectTimer = window.setTimeout(() => this.connect(), 1000)
      }
    }
    this.ws.onmessage = (event) => this.handleMessage(event.data)
  }

  close() {
    this.closedByClient = true
    if (this.reconnectTimer !== null) {
      window.clearTimeout(this.reconnectTimer)
      this.reconnectTimer = null
    }
    this.ws?.close()
    this.ws = null
  }

  requestSnapshots(symbols: string[]) {
    this.sendCommand('snapshot_request', symbols)
  }

  setVisible(symbols: string[]) {
    this.sendCommand('visible_set', symbols)
  }

  private sendCommand(command: string, symbols: string[]) {
    const frame = {
      schema_version: 1,
      protocol: 'terminal-message-v3',
      command,
      request_id: `${command}-${Date.now()}`,
      symbols,
    }
    const encoded = JSON.stringify(frame)
    if (this.ws?.readyState === WebSocket.OPEN) {
      this.ws.send(encoded)
    } else {
      this.pendingCommands.push(encoded)
      this.connect()
    }
  }

  private flushPending() {
    if (this.ws?.readyState !== WebSocket.OPEN) {
      return
    }
    for (const command of this.pendingCommands.splice(0)) {
      this.ws.send(command)
    }
  }

  private handleMessage(raw: string) {
    const frame = JSON.parse(raw)
    if (frame.type === 'snapshot') {
      this.handlers.onSnapshot?.(frame.symbol, frame.payload)
    }
    if (frame.type === 'delta') {
      this.handlers.onDelta?.(frame.symbol, frame.payload)
    }
  }
}
