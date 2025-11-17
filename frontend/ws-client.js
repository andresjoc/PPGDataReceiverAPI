// ws-client.js
export function connect(url, onPayload) {
  const ws = new WebSocket(url);
  ws.onopen = () => console.log('ws open');
  ws.onerror = (e) => console.error('WebSocket error', e);
  ws.onclose = (e) => console.log('ws closed', e);
  ws.onmessage = (e) => {
    let payload = null;
    try {
      payload = JSON.parse(e.data);
    } catch (err) {
      console.error('Failed to parse WS message', err);
      return;
    }
    try {
      onPayload(payload);
    } catch (err) {
      console.error('onPayload handler error', err);
    }
  };
  return ws;
}
