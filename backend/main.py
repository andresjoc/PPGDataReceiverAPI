# backend/main.py
import os
import time
from pathlib import Path
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request
from fastapi.middleware.cors import CORSMiddleware
from data import ppg_dict_to_dataframe, store_ppg_dataframe_to_csv
from infer import Inferer, bandpass_filter, robust_normalize
from typing import List, Optional
import json
import numpy as np
from collections import deque
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

# importar recorder (asumimos que uvicorn se ejecuta desde la carpeta backend)
from video import GreenChannelVideoRecorder

# ---------------- App / CORS / Manager ----------------
app = FastAPI()
frontend_port = os.environ.get('FRONTEND_PORT') or 8080
FRONTEND_ORIGINS = [
    f"http://localhost:{frontend_port}",
    f"http://127.0.0.1:{frontend_port}",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=FRONTEND_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)

    async def broadcast(self, message: str):
        for connection in list(self.active_connections):
            try:
                await connection.send_text(message)
            except Exception:
                try:
                    self.disconnect(connection)
                except Exception:
                    pass

manager = ConnectionManager()

# ---------------- Inferer / Project paths ----------------
model_path = os.environ.get('PPG_MODEL_PATH') or None
inferer: Optional[Inferer] = None
if model_path is not None:
    print(f"Using PPG model path from env: {model_path}")
    try:
        inferer = Inferer(model_path)
    except Exception as e:
        print(f"Could not initialize Inferer: {e}")
        inferer = None

project_root = Path(__file__).resolve().parents[1]
DATA_DIR = Path(os.environ.get('PPG_DATA_DIR') or (project_root / 'data'))
DATA_DIR.mkdir(parents=True, exist_ok=True)

# ---------------- Video configuration (incluye Y-limits opcionales) ----------------
VIDEO_DIR = Path(os.environ.get('PPG_VIDEO_DIR') or (project_root / 'data' / 'videos'))
VIDEO_DIR.mkdir(parents=True, exist_ok=True)

VIDEO_FPS = int(os.environ.get('PPG_VIDEO_FPS', '25'))
VIDEO_WIDTH = int(os.environ.get('PPG_VIDEO_WIDTH', '800'))
VIDEO_HEIGHT = int(os.environ.get('PPG_VIDEO_HEIGHT', '240'))
VIDEO_WINDOW = int(os.environ.get('PPG_VIDEO_WINDOW', '250'))   # 250 muestras = 10s @25Hz
VIDEO_FS = float(os.environ.get('PPG_VIDEO_FS', '25.0'))        # frecuencia de muestreo
DISPLAY_WINDOW_SECONDS = float(os.environ.get('PPG_DISPLAY_WINDOW_SECONDS', '6.0'))  # 6s visual

# Opciones de eje Y (opcionales)
VIDEO_Y_MIN = os.environ.get('PPG_VIDEO_Y_MIN')  # e.g. "-5"
VIDEO_Y_MAX = os.environ.get('PPG_VIDEO_Y_MAX')  # e.g. "5"
VIDEO_Y_SMOOTH = float(os.environ.get('PPG_VIDEO_Y_SMOOTH', '0.2'))  # 0..1 para suavizado dinámico

if VIDEO_Y_MIN is not None:
    try:
        VIDEO_Y_MIN = float(VIDEO_Y_MIN)
    except Exception:
        VIDEO_Y_MIN = None
if VIDEO_Y_MAX is not None:
    try:
        VIDEO_Y_MAX = float(VIDEO_Y_MAX)
    except Exception:
        VIDEO_Y_MAX = None

# Instanciar recorder con parámetros Y
recorder = GreenChannelVideoRecorder(
    str(VIDEO_DIR),
    filename_prefix="GREEN_channel",
    fps=VIDEO_FPS,
    width=VIDEO_WIDTH,
    height=VIDEO_HEIGHT,
    window=VIDEO_WINDOW,
    fs=VIDEO_FS,
    y_min=VIDEO_Y_MIN,
    y_max=VIDEO_Y_MAX,
    y_smooth=VIDEO_Y_SMOOTH
)

# Rolling buffers (valores y timestamps en epoch seconds) — para ventana
green_values = deque(maxlen=VIDEO_WINDOW)
green_timestamps = deque(maxlen=VIDEO_WINDOW)

# FULL measurement accumulators (guardan la medición completa durante la sesión)
full_green_values: List[float] = []
full_green_timestamps: List[float] = []

# ---------------- Util: parse index -> epoch seconds ----------------
def parse_index_to_seconds(idx):
    """
    Convierte un índice TIMESTAMP del DataFrame a segundos epoch (float).
    Maneja int/float (ms o s) y strings datetimelike.
    """
    try:
        if isinstance(idx, (int, np.integer, float, np.floating)):
            val = float(idx)
            # heurística: si el número > 1e11 -> ms
            if val > 1e11:
                return val / 1000.0
            if val > 1e9:
                return val
            # fallback: si es muy pequeño, usar time.time()
            return time.time()
        else:
            ts = pd.to_datetime(idx, errors='coerce')
            if pd.isna(ts):
                return time.time()
            return ts.timestamp()
    except Exception:
        return time.time()

# ---------------- WebSocket endpoint ----------------
@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    # permitir solo localhost por seguridad (igual que antes)
    client = websocket.client
    if client is not None:
        client_host = client[0]
        if client_host not in ("127.0.0.1", "::1", "localhost"):
            await websocket.close(code=1008)
            return

    await manager.connect(websocket)
    try:
        while True:
            data = await websocket.receive_text()
            await manager.broadcast(data)
    except WebSocketDisconnect:
        manager.disconnect(websocket)

# ---------------- Helper: save full-measurement image ----------------
def save_full_measurement_image(values: List[float], timestamps: List[float], out_dir: Path, filename_prefix: str = "measurement_full"):
    """
    Guarda una imagen PNG de la medición completa (solo señal procesada, normalizada).
    - values: lista de floats (raw)
    - timestamps: lista de epoch seconds floats (mismo largo)
    - out_dir: carpeta donde guardar la imagen (se crea si no existe)
    """
    if not values or not timestamps or len(values) != len(timestamps):
        print("No hay datos completos para guardar la imagen.")
        return None

    os.makedirs(out_dir, exist_ok=True)
    # Convertir a numpy
    raw = np.array(values, dtype=np.float32)
    ts = np.array(timestamps, dtype=np.float64)
    # Preprocesado sobre toda la serie: bandpass + robust normalize
    try:
        proc = bandpass_filter(raw, 0.5, 8.0, VIDEO_FS)
    except TypeError:
        proc = bandpass_filter(raw, 0.5, 8.0)
    try:
        proc = robust_normalize(proc)
    except Exception:
        # fallback: zscore-like
        proc = (proc - np.mean(proc)) / (np.std(proc) + 1e-8)

    # eje X: segundos relativos desde primer timestamp
    t0 = float(ts[0])
    x = ts - t0

    # Crear figura de tamaño amplio para toda la señal
    fig_w = 14
    fig_h = 4
    fig = plt.figure(figsize=(fig_w, fig_h), dpi=100)
    ax = fig.add_subplot(111)

    # Estética: sin título ni etiquetas, pero con ejes y ticks visibles como pediste
    ax.set_facecolor('white')
    ax.plot(x, proc, color='#2a9d5b', linewidth=1.0)

    # Mostrar ejes (left & bottom) y ticks
    for spine_name, spine in ax.spines.items():
        if spine_name in ('left', 'bottom'):
            spine.set_visible(True)
            spine.set_color('#111111')
            spine.set_linewidth(1.0)
        else:
            spine.set_visible(False)

    ax.tick_params(axis='both', which='both', labelsize=9, colors='#111111')

    # Ajustar límites Y simétricos opcionalmente: usaremos min/max del proc y un padding
    ymin = float(np.min(proc))
    ymax = float(np.max(proc))
    if ymax == ymin:
        ymax += 1.0
        ymin -= 1.0
    pad = (ymax - ymin) * 0.12
    ax.set_ylim(ymin - pad, ymax + pad)

    # X limits: desde 0 hasta último segundo
    ax.set_xlim(0.0, float(x[-1]))

    # Evitar labels grandes: no title, no xlabel/ylabel
    fig.tight_layout(pad=0.6)

    # Guardar
    ts_str = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    out_path = out_dir / f"{filename_prefix}_{ts_str}.png"
    try:
        fig.savefig(str(out_path), dpi=150, facecolor='white')
        print("Saved full-measurement image to:", str(out_path))
    except Exception as e:
        print("Error saving full measurement image:", e)
        out_path = None
    finally:
        plt.close(fig)

    return out_path

# ---------------- HTTP POST endpoint ----------------
@app.post("/")
async def receive_data(request: Request, data: dict):
    """
    Endpoint principal. Convierte JSON -> DataFrame, guarda CSV, hace broadcast,
    y actualiza el video del canal GREEN (visualización de 6s con contadores de segundos).
    Además acumula toda la medición en full_green_values/timestamps.
    """
    try:
        df = ppg_dict_to_dataframe(data)
    except Exception as e:
        print(f"Error while parsing JSON: {e}")
        return {"status": "error", "message": f"Error while parsing JSON: {e}"}

    print(f"Received data with {len(df)} samples.")

    # respuesta / broadcast (igual que antes)
    response_payload = {"raw": df.to_dict(orient="split")}

    # Inferencia opcional
    if inferer is not None:
        try:
            results = inferer.classify(df)
            if results is not None:
                serializable_results = {}
                for channel in results:
                    serializable_results[channel] = {
                        "signal": results[channel]["preprocessed_signal"].tolist(),
                        "label": results[channel]["label"],
                        "confidence": float(results[channel]["confidence"])
                    }
                response_payload["inference"] = serializable_results
        except Exception as e:
            print(f"Error in inferer.classify: {e}")

    # Broadcast
    try:
        await manager.broadcast(json.dumps(response_payload))
    except Exception:
        pass

    # Guardar CSV
    try:
        filepath = store_ppg_dataframe_to_csv(str(DATA_DIR), df)
        print(f"Saved received PPG data to CSV: {filepath}")
    except Exception as e:
        print(f"Error saving PPG data to CSV: {e}")

    # ---------- Procesamiento del canal GREEN ----------
    try:
        if "GREEN" in df.columns:
            vals = df["GREEN"].astype(float).to_numpy()
            idxs = df.index.to_numpy()

            for i in range(len(vals)):
                sample = float(vals[i])
                idx = idxs[i]
                ts_sec = parse_index_to_seconds(idx)

                # Append real sample + timestamp to rolling buffers (window)
                green_values.append(sample)
                green_timestamps.append(ts_sec)

                # También acumular toda la medición completa
                full_green_values.append(sample)
                full_green_timestamps.append(ts_sec)

                # fijar start_time del recorder en el primer sample real (si no está)
                if recorder.start_time is None:
                    try:
                        recorder.start_time = float(green_timestamps[0])
                    except Exception:
                        recorder.start_time = float(ts_sec)

                # construir ventana EXACTA de tamaño VIDEO_WINDOW (pad por la izquierda si hace falta)
                n = len(green_values)
                if n < VIDEO_WINDOW:
                    pad_len = VIDEO_WINDOW - n
                    if n > 0:
                        first_val = green_values[0]
                        padded_vals = np.concatenate((np.full(pad_len, first_val, dtype=np.float32),
                                                      np.array(green_values, dtype=np.float32)))
                        first_ts = green_timestamps[0]
                        # timestamps: retroceder pad_len*dt para el padding
                        padded_ts = np.array(
                            [first_ts - (pad_len - j) * (1.0 / VIDEO_FS) for j in range(pad_len)]
                            + list(green_timestamps),
                            dtype=np.float64
                        )
                    else:
                        padded_vals = np.zeros(VIDEO_WINDOW, dtype=np.float32)
                        padded_ts = np.array(
                            [time.time() - (VIDEO_WINDOW - 1 - j) * (1.0 / VIDEO_FS) for j in range(VIDEO_WINDOW)],
                            dtype=np.float64
                        )
                else:
                    padded_vals = np.array(green_values, dtype=np.float32)
                    padded_ts = np.array(green_timestamps, dtype=np.float64)

                # Preprocesado: bandpass + robust_normalize (misma lógica que infer.py)
                try:
                    proc = bandpass_filter(padded_vals, 0.5, 8.0, VIDEO_FS)
                except TypeError:
                    # fallback si la firma de bandpass_filter es distinta
                    proc = bandpass_filter(padded_vals, 0.5, 8.0)

                proc = robust_normalize(proc)

                # Llamar al recorder con timestamps y ventana de visualización
                try:
                    recorder.write_frame_from_arrays_with_timestamps(
                        proc, padded_ts, display_window_seconds=DISPLAY_WINDOW_SECONDS
                    )
                except Exception as e:
                    print(f"Error writing GREEN frame: {e}")

        else:
            # no GREEN en este post: nada que hacer
            pass
    except Exception as e:
        print(f"Error while recording GREEN channel to video: {e}")

    return {"status": "ok", "received": True}

# ---------------- Shutdown event ----------------
@app.on_event("shutdown")
def shutdown_event():
    print("Shutting down - closing GREEN video recorder...")
    try:
        recorder.close()
        print("GREEN recorder closed. Video saved at:", recorder.get_video_path())
    except Exception as e:
        print("Error closing recorder:", e)

    # Guardar imagen de la medición completa (si hay datos)
    try:
        images_dir = DATA_DIR / "images"
        images_dir.mkdir(parents=True, exist_ok=True)
        saved = save_full_measurement_image(full_green_values, full_green_timestamps, images_dir, filename_prefix="measurement_full")
        if saved is not None:
            print("Full measurement image saved at:", saved)
        else:
            print("No full measurement image saved (no data).")
    except Exception as e:
        print("Error while saving full measurement image:", e)

# ---------------- Main runner for dev (optional) ----------------
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
