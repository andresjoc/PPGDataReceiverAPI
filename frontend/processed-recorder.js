let recorderState = {
  started: false,
  recorder: null,
  chunks: [],
  drawTimer: null,
  canvas: null,
  ctx: null,
<<<<<<< ours
  fps: 10
=======
  fps: 10,
  supportsRecorder: typeof window !== 'undefined' && !!window.MediaRecorder
>>>>>>> theirs
};

function selectMimeType() {
  const preferred = [
    'video/webm;codecs=vp9',
    'video/webm;codecs=vp8',
    'video/webm'
  ];
  if (!window.MediaRecorder) return null;
  for (const type of preferred) {
    if (MediaRecorder.isTypeSupported(type)) {
      return type;
    }
  }
  return '';
}

function buildRecordingCanvas() {
  const canvases = Array.from(document.querySelectorAll('#processed-charts-container canvas'));
  if (canvases.length === 0) return null;

  const width = Math.max(...canvases.map((canvas) => canvas.width));
  const padding = 12;
  const height = canvases.reduce((acc, canvas) => acc + canvas.height, 0) + padding * (canvases.length - 1);

  const recordCanvas = document.createElement('canvas');
  recordCanvas.width = width;
  recordCanvas.height = height;

  const ctx = recordCanvas.getContext('2d');
  ctx.fillStyle = '#ffffff';
  ctx.fillRect(0, 0, width, height);

  return { recordCanvas, ctx, canvases, padding };
}

function drawProcessedCharts() {
  if (!recorderState.canvas || !recorderState.ctx) return;
  const ctx = recorderState.ctx;
  const canvases = Array.from(document.querySelectorAll('#processed-charts-container canvas'));
  if (canvases.length === 0) return;

  const padding = 12;
  let offsetY = 0;
  ctx.fillStyle = '#ffffff';
  ctx.fillRect(0, 0, recorderState.canvas.width, recorderState.canvas.height);
  for (const canvas of canvases) {
    ctx.drawImage(canvas, 0, offsetY, canvas.width, canvas.height);
    offsetY += canvas.height + padding;
  }
}

function finalizeRecording() {
  if (!recorderState.chunks.length) return;
  const blob = new Blob(recorderState.chunks, { type: recorderState.recorder.mimeType || 'video/webm' });
  const timestamp = new Date().toISOString().replace(/[:.]/g, '-');
  const filename = `procesado-${timestamp}.webm`;
  const link = document.createElement('a');
  link.href = URL.createObjectURL(blob);
  link.download = filename;
  link.click();
  setTimeout(() => URL.revokeObjectURL(link.href), 1000);
  recorderState.chunks = [];
}

<<<<<<< ours
export function startProcessedRecording() {
  if (recorderState.started) return;
  if (!window.MediaRecorder) {
    console.warn('MediaRecorder not supported in this browser.');
    return;
=======
function setIndicator(isRecording) {
  const indicator = document.getElementById('processed-recording');
  if (indicator) indicator.style.display = isRecording ? 'inline-flex' : 'none';
}

function setStatus(message) {
  const status = document.getElementById('processed-recording-status');
  if (status) status.textContent = message;
}

export function isRecording() {
  return recorderState.started;
}

export function supportsRecording() {
  return recorderState.supportsRecorder;
}

export function startProcessedRecording() {
  if (recorderState.started) return true;
  if (!window.MediaRecorder) {
    console.warn('MediaRecorder not supported in this browser.');
    setStatus('Tu navegador no soporta grabación.');
    return false;
>>>>>>> theirs
  }

  const setup = buildRecordingCanvas();
  if (!setup) {
    console.warn('No processed canvases found to record.');
<<<<<<< ours
    return;
=======
    setStatus('No hay gráficos procesados para grabar.');
    return false;
>>>>>>> theirs
  }

  recorderState.started = true;
  recorderState.canvas = setup.recordCanvas;
  recorderState.ctx = setup.ctx;
  const mimeType = selectMimeType();
  const stream = recorderState.canvas.captureStream(recorderState.fps);
  recorderState.recorder = new MediaRecorder(stream, mimeType ? { mimeType } : undefined);

  recorderState.recorder.addEventListener('dataavailable', (event) => {
    if (event.data && event.data.size > 0) {
      recorderState.chunks.push(event.data);
    }
  });
  recorderState.recorder.addEventListener('stop', finalizeRecording);

  recorderState.drawTimer = window.setInterval(drawProcessedCharts, 1000 / recorderState.fps);
  recorderState.recorder.start(1000);
<<<<<<< ours

  const indicator = document.getElementById('processed-recording');
  if (indicator) indicator.style.display = 'inline-flex';
=======
  setIndicator(true);
  setStatus('Grabando...');
>>>>>>> theirs

  window.addEventListener('beforeunload', () => {
    stopProcessedRecording();
  }, { once: true });
<<<<<<< ours
=======
  return true;
>>>>>>> theirs
}

export function stopProcessedRecording() {
  if (!recorderState.started) return;
  recorderState.started = false;
  if (recorderState.drawTimer) {
    clearInterval(recorderState.drawTimer);
    recorderState.drawTimer = null;
  }
  if (recorderState.recorder && recorderState.recorder.state !== 'inactive') {
    recorderState.recorder.stop();
  }
<<<<<<< ours
  const indicator = document.getElementById('processed-recording');
  if (indicator) indicator.style.display = 'none';
=======
  setIndicator(false);
  setStatus('Grabación detenida. Descargando...');
>>>>>>> theirs
}
