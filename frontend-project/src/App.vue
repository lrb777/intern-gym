<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { formatCompact, formatDateTime, formatPrice, runtimeLabel } from './utils/marketFormat'
import { MarketFeedClient, type DeltaPayload, type MarketBar, type QueueLevel, type SnapshotPayload, type TradeAlert } from './services/marketFeed'

const symbols = ['02723.HK', '02675.HK', '00100.HK', '02513.HK', '06082.HK']
const activeSymbol = ref(symbols[0])
const status = ref<'open' | 'closed' | 'error'>('closed')
const search = ref('')
const snapshots = ref<Record<string, SnapshotPayload>>({})

let client: MarketFeedClient | null = null

const filteredSymbols = computed(() => {
  const query = search.value.trim().toUpperCase()
  if (!query) {
    return symbols
  }
  return symbols.filter((symbol) => {
    const name = snapshots.value[symbol]?.snapshot.name || ''
    return symbol.includes(query) || name.toUpperCase().includes(query)
  })
})

const activeSnapshot = computed(() => snapshots.value[activeSymbol.value])
const activeBars = computed(() => activeSnapshot.value?.minute_bars.slice(-80) || [])
const activeAlerts = computed(() => activeSnapshot.value?.alerts.slice(0, 8) || [])
const askLevels = computed(() => activeSnapshot.value?.broker_queue.ask.slice(0, 10) || [])
const bidLevels = computed(() => activeSnapshot.value?.broker_queue.bid.slice(0, 10) || [])
const maxVolume = computed(() => Math.max(1, ...activeBars.value.map((bar) => Number(bar.volume || 0))))
const connectionLabel = computed(() => (status.value === 'open' ? 'Live' : status.value === 'error' ? 'Error' : 'Warm'))

function applyDelta(symbol: string, payload: DeltaPayload) {
  const current = snapshots.value[symbol]
  if (!current) {
    return
  }
  const next: SnapshotPayload = { ...current, snapshot: { ...current.snapshot } }
  if (payload.delta_type === 'minute_bar' && payload.minute_bar) {
    next.minute_bars = upsertBar(current.minute_bars, payload.minute_bar)
    next.snapshot = {
      ...next.snapshot,
      price: payload.minute_bar.close,
      updatedAt: payload.minute_bar.timestamp,
      tradeDate: payload.minute_bar.timestamp.slice(0, 10).replaceAll('-', ''),
    }
  }
  if (payload.delta_type === 'trade_tick' && payload.alert) {
    next.alerts = upsertAlert(current.alerts, payload.alert)
    next.snapshot = {
      ...next.snapshot,
      price: payload.alert.price,
      updatedAt: payload.alert.timestamp,
      tradeDate: payload.alert.tradeDate,
    }
  }
  if (payload.delta_type === 'broker_queue' && payload.broker_queue) {
    next.broker_queue = payload.broker_queue
  }
  snapshots.value = { ...snapshots.value, [symbol]: next }
}

function upsertBar(bars: MarketBar[], bar: MarketBar) {
  const next = bars.filter((item) => item.timestamp !== bar.timestamp)
  next.push(bar)
  next.sort((a, b) => a.timestamp.localeCompare(b.timestamp))
  return next.slice(-420)
}

function upsertAlert(alerts: TradeAlert[], alert: TradeAlert) {
  if (alerts.some((item) => item.id === alert.id)) {
    return alerts
  }
  return [alert, ...alerts].slice(0, 100)
}

function levelWidth(level: QueueLevel) {
  const levels = [...askLevels.value, ...bidLevels.value]
  const max = Math.max(1, ...levels.map((item) => Number(item.volume || 0)))
  return `${Math.max(4, Math.round((Number(level.volume || 0) / max) * 100))}%`
}

function barHeight(bar: MarketBar) {
  return `${Math.max(3, Math.round((Number(bar.volume || 0) / maxVolume.value) * 100))}%`
}

onMounted(() => {
  client = new MarketFeedClient('ws://127.0.0.1:9021/ws', {
    onStatus: (value) => {
      status.value = value
    },
    onSnapshot: (symbol, payload) => {
      snapshots.value = { ...snapshots.value, [symbol]: payload }
    },
    onDelta: applyDelta,
  })
  client.connect()
  client.requestSnapshots(symbols)
})

onBeforeUnmount(() => {
  client?.close()
})
</script>

<template>
  <main class="terminal">
    <aside class="watchlist">
      <div class="search">
        <input v-model="search" type="search" placeholder="Search symbol" />
      </div>
      <button
        v-for="symbol in filteredSymbols"
        :key="symbol"
        :class="{ active: symbol === activeSymbol }"
        @click="activeSymbol = symbol"
      >
        <span>{{ snapshots[symbol]?.snapshot.name || symbol }}</span>
        <small>{{ symbol }}</small>
      </button>
    </aside>

    <section class="workspace">
      <header class="topbar">
        <div>
          <h1>{{ activeSnapshot?.snapshot.name || activeSymbol }}</h1>
          <span>{{ activeSymbol }} · {{ formatDateTime(activeSnapshot?.snapshot.updatedAt) }}</span>
        </div>
        <strong :class="['status', status]">{{ connectionLabel }}</strong>
      </header>

      <section class="quote-strip">
        <div>
          <span>Last</span>
          <strong>{{ formatPrice(activeSnapshot?.snapshot.price) }}</strong>
        </div>
        <div>
          <span>Open</span>
          <strong>{{ formatPrice(activeSnapshot?.snapshot.open) }}</strong>
        </div>
        <div>
          <span>High</span>
          <strong>{{ formatPrice(activeSnapshot?.snapshot.high) }}</strong>
        </div>
        <div>
          <span>Low</span>
          <strong>{{ formatPrice(activeSnapshot?.snapshot.low) }}</strong>
        </div>
        <div>
          <span>Volume</span>
          <strong>{{ formatCompact(activeSnapshot?.snapshot.volume) }}</strong>
        </div>
        <div>
          <span>State</span>
          <strong>{{ runtimeLabel(activeSnapshot?.freshness.runtime_state) }}</strong>
        </div>
      </section>

      <section class="market-grid">
        <section class="panel price-panel">
          <div class="panel-title">
            <h2>Minute</h2>
            <span>{{ activeSnapshot?.snapshot.tradeDate || '-' }}</span>
          </div>
          <div class="sparkline" aria-label="Minute price and volume preview">
            <div
              v-for="bar in activeBars"
              :key="bar.timestamp"
              class="bar"
              :title="`${formatDateTime(bar.timestamp)} ${formatPrice(bar.close)}`"
            >
              <i :style="{ height: barHeight(bar) }"></i>
            </div>
          </div>
        </section>

        <section class="panel alerts-panel">
          <div class="panel-title">
            <h2>Big Trades</h2>
            <span>{{ activeAlerts.length }}</span>
          </div>
          <table>
            <thead>
              <tr>
                <th>Time</th>
                <th>Side</th>
                <th>Price</th>
                <th>Volume</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="alert in activeAlerts" :key="alert.id">
                <td>{{ formatDateTime(alert.timestamp) }}</td>
                <td>{{ alert.side }}</td>
                <td>{{ formatPrice(alert.price) }}</td>
                <td>{{ formatCompact(alert.volume) }}</td>
              </tr>
              <tr v-if="!activeAlerts.length">
                <td colspan="4">No current-day alerts</td>
              </tr>
            </tbody>
          </table>
        </section>

        <section class="panel queue-panel">
          <div class="panel-title">
            <h2>Broker Queue</h2>
            <span v-if="activeSnapshot?.broker_queue.fallback">Fallback {{ activeSnapshot?.broker_queue.sourceDate }}</span>
            <span v-else>{{ activeSnapshot?.broker_queue.sourceDate || '-' }}</span>
          </div>
          <div class="queues">
            <div>
              <h3>Ask</h3>
              <ol>
                <li v-for="level in askLevels" :key="level.id">
                  <span>{{ level.position }}</span>
                  <strong>{{ formatPrice(level.price) }}</strong>
                  <em>{{ formatCompact(level.volume) }}</em>
                  <i :style="{ width: levelWidth(level) }"></i>
                </li>
              </ol>
            </div>
            <div>
              <h3>Bid</h3>
              <ol>
                <li v-for="level in bidLevels" :key="level.id">
                  <span>{{ level.position }}</span>
                  <strong>{{ formatPrice(level.price) }}</strong>
                  <em>{{ formatCompact(level.volume) }}</em>
                  <i :style="{ width: levelWidth(level) }"></i>
                </li>
              </ol>
            </div>
          </div>
        </section>
      </section>
    </section>
  </main>
</template>

<style scoped>
.terminal {
  display: grid;
  grid-template-columns: 224px minmax(0, 1fr);
  min-height: 100vh;
  font-family: Inter, system-ui, sans-serif;
  color: #18212f;
  background: #f7f9fc;
}

.watchlist {
  border-right: 1px solid #d7dde5;
  background: #ffffff;
  padding: 12px;
}

.search {
  margin-bottom: 12px;
}

.search input {
  width: 100%;
  height: 36px;
  border: 1px solid #cfd7e2;
  border-radius: 6px;
  padding: 0 10px;
}

.watchlist button {
  display: block;
  width: 100%;
  margin-bottom: 8px;
  padding: 9px;
  text-align: left;
  border: 1px solid #d7dde5;
  border-radius: 6px;
  background: white;
}

.watchlist button.active {
  border-color: #0f62fe;
  box-shadow: inset 3px 0 0 #0f62fe;
}

.watchlist span,
.watchlist small {
  display: block;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.watchlist small {
  color: #667085;
}

.workspace {
  min-width: 0;
  padding: 16px;
}

.topbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 14px;
}

h1,
h2,
h3 {
  margin: 0;
}

h1 {
  font-size: 22px;
}

h2 {
  font-size: 15px;
}

h3 {
  font-size: 13px;
  margin-bottom: 8px;
}

.topbar span,
.panel-title span,
.quote-strip span {
  color: #667085;
  font-size: 12px;
}

.status {
  border-radius: 999px;
  padding: 6px 10px;
  background: #f1f4f9;
  color: #344054;
}

.status.open {
  background: #e9f8ef;
  color: #137333;
}

.status.error {
  background: #fdecec;
  color: #b42318;
}

.quote-strip {
  display: grid;
  grid-template-columns: repeat(6, minmax(0, 1fr));
  gap: 1px;
  overflow: hidden;
  border: 1px solid #d7dde5;
  border-radius: 8px;
  background: #d7dde5;
  margin-bottom: 14px;
}

.quote-strip div {
  background: #ffffff;
  padding: 12px;
  min-width: 0;
}

.quote-strip strong {
  display: block;
  margin-top: 4px;
  font-size: 18px;
}

.market-grid {
  display: grid;
  grid-template-columns: minmax(0, 1.3fr) minmax(300px, 0.7fr);
  gap: 14px;
}

.panel {
  border: 1px solid #d7dde5;
  border-radius: 8px;
  background: #ffffff;
  padding: 14px;
  min-width: 0;
}

.queue-panel {
  grid-column: 1 / -1;
}

.panel-title {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 12px;
}

.sparkline {
  display: flex;
  align-items: end;
  gap: 2px;
  height: 240px;
  border-left: 1px solid #e3e8ef;
  border-bottom: 1px solid #e3e8ef;
  padding: 8px 0 0 8px;
}

.bar {
  display: flex;
  align-items: end;
  flex: 1 1 3px;
  height: 100%;
  min-width: 2px;
}

.bar i {
  display: block;
  width: 100%;
  background: #0f62fe;
}

table {
  width: 100%;
  border-collapse: collapse;
  font-size: 13px;
}

th,
td {
  border-bottom: 1px solid #e3e8ef;
  padding: 8px 6px;
  text-align: left;
}

th {
  color: #667085;
  font-weight: 600;
}

.queues {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 16px;
}

ol {
  list-style: none;
  margin: 0;
  padding: 0;
}

li {
  position: relative;
  display: grid;
  grid-template-columns: 34px 1fr 72px;
  gap: 8px;
  align-items: center;
  min-height: 30px;
  border-bottom: 1px solid #eef2f6;
  font-size: 13px;
  overflow: hidden;
}

li i {
  position: absolute;
  inset: 6px 0 6px auto;
  display: block;
  background: #e8f1ff;
  z-index: 0;
}

li span,
li strong,
li em {
  position: relative;
  z-index: 1;
}

li em {
  color: #667085;
  font-style: normal;
  text-align: right;
}

@media (max-width: 900px) {
  .terminal {
    grid-template-columns: 1fr;
  }

  .watchlist {
    display: grid;
    grid-template-columns: repeat(5, minmax(132px, 1fr));
    gap: 8px;
    overflow-x: auto;
    border-right: 0;
    border-bottom: 1px solid #d7dde5;
  }

  .search {
    grid-column: 1 / -1;
  }

  .market-grid,
  .queues,
  .quote-strip {
    grid-template-columns: 1fr;
  }
}
</style>
