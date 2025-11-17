import { initCharts, ensureChartsForColumns, appendBatch } from './chart-setup.js';
import { connect } from './ws-client.js';
import { parsePayload } from './data-handler.js';

const pageLoadTs = Date.now();

// Initialize three separate charts (IR, RED, GREEN)
initCharts();

// start websocket and feed parsed payloads into the chart
connect('ws://localhost:8000/ws', (payload) => {
  const parsed = parsePayload(payload, pageLoadTs);
  if (!parsed) {
    console.warn('Unhandled payload format', payload);
    return;
  }
  ensureChartsForColumns(parsed.columns);
  appendBatch(parsed.timestampsSec, parsed.columns, parsed.columnsData);
});
