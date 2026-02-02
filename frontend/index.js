import { initCharts, ensureChartsForColumns, appendBatch, initProcessedCharts, updateProcessedCharts } from './chart-setup.js';
import { connect } from './ws-client.js';
import { parsePayload } from './data-handler.js';
<<<<<<< ours
import { startProcessedRecording } from './processed-recorder.js';
=======
import { startProcessedRecording, stopProcessedRecording, isRecording, supportsRecording } from './processed-recorder.js';
>>>>>>> theirs

const pageLoadTs = Date.now();

// Initialize three separate charts (IR, RED, GREEN)
initCharts();
initProcessedCharts();

// Tab handling
const tabRaw = document.getElementById('tab-raw');
const tabProcessed = document.getElementById('tab-processed');
const viewRaw = document.getElementById('view-raw');
const viewProcessed = document.getElementById('view-processed');

if (tabRaw && tabProcessed && viewRaw && viewProcessed) {
  tabRaw.addEventListener('click', () => {
    tabRaw.classList.add('active');
    tabProcessed.classList.remove('active');
    viewRaw.style.display = 'block';
    viewProcessed.style.display = 'none';
  });

  tabProcessed.addEventListener('click', () => {
    tabProcessed.classList.add('active');
    tabRaw.classList.remove('active');
    viewProcessed.style.display = 'block';
    viewRaw.style.display = 'none';
  });
}

const startButton = document.getElementById('processed-start');
const stopButton = document.getElementById('processed-stop');
const statusLabel = document.getElementById('processed-recording-status');

if (!supportsRecording() && statusLabel) {
  statusLabel.textContent = 'Tu navegador no soporta grabación.';
}

function updateRecordingButtons() {
  if (!startButton || !stopButton) return;
  const recording = isRecording();
  startButton.disabled = recording;
  stopButton.disabled = !recording;
}

if (startButton) {
  startButton.addEventListener('click', () => {
    if (!supportsRecording()) {
      console.warn('MediaRecorder not supported in this browser.');
      return;
    }
    startProcessedRecording();
    updateRecordingButtons();
  });
}

if (stopButton) {
  stopButton.addEventListener('click', () => {
    stopProcessedRecording();
    updateRecordingButtons();
  });
}

// start websocket and feed parsed payloads into the chart
connect('ws://localhost:8000/ws', (payload) => {
  const parsed = parsePayload(payload, pageLoadTs);
  if (!parsed) {
    console.warn('Unhandled payload format', payload);
    return;
  }

  // Handle both wrapped and legacy formats
  const rawData = parsed.raw || (parsed.columns ? parsed : null);
  const inferenceData = parsed.inference;

  if (rawData) {
    ensureChartsForColumns(rawData.columns);
    appendBatch(rawData.timestampsSec, rawData.columns, rawData.columnsData);
  }

  if (inferenceData) {
    updateProcessedCharts(inferenceData);
<<<<<<< ours
    startProcessedRecording();
=======
    if (supportsRecording() && !isRecording()) {
      startProcessedRecording();
      updateRecordingButtons();
    }
>>>>>>> theirs
  }
});
