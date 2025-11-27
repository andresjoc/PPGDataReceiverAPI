// data-handler.js
// Parse incoming payloads and normalize to { columns, timestampsSec, columnsData }
export function parsePayload(payload, pageLoadTs) {
  if (!payload || typeof payload !== 'object') return null;

  let rawPayload = payload;
  let inference = null;

  if (payload.raw) {
    rawPayload = payload.raw;
    inference = payload.inference;
  }

  let result = null;

  // Legacy format: payload.samples = [[timestamp, value], ...]
  if (rawPayload.samples && Array.isArray(rawPayload.samples)) {
    const newTs = [];
    const colData = [[]];
    for (const s of rawPayload.samples) {
      if (Array.isArray(s) && s.length >= 2) {
        const sec = (Number(s[0]) - pageLoadTs) / 1000;
        newTs.push(sec);
        colData[0].push(s[1]);
      } else {
        const sec = (Date.now() - pageLoadTs) / 1000;
        newTs.push(sec);
        colData[0].push(Array.isArray(s) ? s[0] : s);
      }
    }
    result = { columns: ['PPG'], timestampsSec: newTs, columnsData: colData };
  }

  // Pandas orient='split' format: {columns: [...], index: [...], data: [[...], ...]}
  else if (rawPayload.columns && rawPayload.index && rawPayload.data) {
    const columns = rawPayload.columns;
    const index = rawPayload.index;
    const rows = rawPayload.data;
    const columnsData = columns.map(() => []);
    const newTs = [];
    for (let r = 0; r < rows.length; r++) {
      const ts = index[r];
      let ms = null;
      if (typeof ts === 'number') ms = ts;
      else {
        const parsed = Date.parse(ts);
        ms = isNaN(parsed) ? Date.now() : parsed;
      }
      const sec = (ms - pageLoadTs) / 1000;
      newTs.push(sec);
      for (let c = 0; c < columns.length; c++) {
        columnsData[c].push(rows[r][c]);
      }
    }
    result = { columns, timestampsSec: newTs, columnsData };
  }

  if (result) {
    result.inference = inference;
  }
  return result;
}
