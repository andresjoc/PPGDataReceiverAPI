# backend/video.py
# Recorder que genera un video continuo del canal GREEN.
# Muestra únicamente la señal PROCESADA (normalizada) en la ventana visible.
# Conserva soporte para límites Y fijos o dinámicos suavizados.

import os
from datetime import datetime
from typing import Optional, Tuple
import numpy as np
import cv2
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.backends.backend_agg import FigureCanvasAgg as FigureCanvas

class GreenChannelVideoRecorder:
    def __init__(self,
                 out_dir: str,
                 filename_prefix: str = "GREEN_channel",
                 fps: int = 25,
                 width: int = 800,
                 height: int = 240,
                 window: int = 250,
                 fs: float = 25.0,
                 y_min: Optional[float] = None,
                 y_max: Optional[float] = None,
                 y_smooth: float = 0.2):
        """
        Args:
            out_dir: carpeta donde guardar el video.
            window: tamaño de ventana para el procesamiento (250).
            fs: frecuencia de muestreo (25.0).
            y_min, y_max: si se especifican ambos, el eje Y será fijo y usará estos límites.
            y_smooth: factor de suavizado exponencial [0..1] para límites dinámicos
                      (si y_min/y_max son None). 0 = sin suavizado, 1 = no cambia.
        """
        self.out_dir = os.path.abspath(out_dir)
        os.makedirs(self.out_dir, exist_ok=True)
        ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        self.video_path = os.path.join(self.out_dir, f"{filename_prefix}_{ts}.mp4")

        self.fps = int(fps)
        self.width = int(width)
        self.height = int(height)
        self.window = int(window)
        self.fs = float(fs)
        self.dt = 1.0 / self.fs
        self.window_seconds = (self.window - 1) * self.dt

        # Y-axis control
        self.y_min_fixed = None if y_min is None else float(y_min)
        self.y_max_fixed = None if y_max is None else float(y_max)
        if self.y_min_fixed is not None and self.y_max_fixed is not None:
            if self.y_min_fixed >= self.y_max_fixed:
                raise ValueError("y_min must be < y_max")

        self.y_smooth = float(y_smooth)
        if not (0.0 <= self.y_smooth <= 1.0):
            raise ValueError("y_smooth must be in [0.0, 1.0]")

        self._smoothed_ylim: Optional[Tuple[float, float]] = None

        self.writer = None

        # figura persistente
        self.dpi = 100
        self.fig_w = self.width / self.dpi
        self.fig_h = self.height / self.dpi

        # estética
        self.bg_color = 'white'
        self.proc_color =  '#1E90FF'

        # START TIME (se setea desde main al primer sample)
        self.start_time = None

        self._init_figure()
        self._closed = False

    def _init_figure(self):
        # Crear figura y ejes
        self.fig = plt.Figure(figsize=(self.fig_w, self.fig_h), dpi=self.dpi)
        self.canvas = FigureCanvas(self.fig)
        self.ax = self.fig.add_subplot(111)

        # Fondo y grid tenue
        self.ax.set_facecolor(self.bg_color)
        self.fig.patch.set_facecolor(self.bg_color)
        self.ax.grid(color='lightgray', linewidth=0.5, alpha=0.35)

        # Mostrar solo left & bottom spines (tener "los ejes" visibles) y ocultar top/right
        for spine_name, spine in self.ax.spines.items():
            if spine_name in ('left', 'bottom'):
                spine.set_visible(True)
                spine.set_color('#111111')
                spine.set_linewidth(1.0)
            else:
                spine.set_visible(False)

        # Línea persistente: processed (solo esta se dibuja)
        self.proc_line, = self.ax.plot([], [], color=self.proc_color, linewidth=1.8, alpha=1.0, zorder=2)

        # NO mostrar título ni etiquetas de eje (usuario pidió ocultarlas)
        # Mostrar ticks y valores
        self.ax.tick_params(axis='both', which='both', labelsize=9, colors='#111111')
        self.ax.minorticks_off()

        # Límite X inicial (se actualizará en cada frame)
        self.ax.set_xlim(0.0, min(6.0, self.window_seconds))

        self.fig.tight_layout(pad=0.6)

    def _ensure_writer(self):
        if self.writer is None:
            fourcc = cv2.VideoWriter_fourcc(*"mp4v")
            self.writer = cv2.VideoWriter(self.video_path, fourcc, float(self.fps), (self.width, self.height))
            if not self.writer.isOpened():
                raise RuntimeError(f"Could not open VideoWriter at {self.video_path}")

    # util RGBA -> RGB compositing sobre blanco
    def _rgba_to_rgb_uint8(self, rgba: np.ndarray, bg=(255,255,255)):
        if rgba.shape[2] != 4:
            raise ValueError("Expected RGBA with 4 channels")
        alpha = rgba[..., 3:4].astype(np.float32) / 255.0
        rgb = rgba[..., :3].astype(np.float32)
        bg_arr = np.array(bg, dtype=np.float32).reshape((1,1,3))
        composed = rgb * alpha + bg_arr * (1.0 - alpha)
        composed = np.clip(composed, 0, 255).astype(np.uint8)
        return composed

    def _get_canvas_rgb(self):
        renderer = self.canvas.get_renderer()
        try:
            buf = renderer.buffer_rgba()
            arr = np.asarray(buf)
            if arr.ndim == 3 and arr.shape[2] == 4:
                return self._rgba_to_rgb_uint8(arr, bg=(255,255,255))
        except Exception:
            pass
        try:
            buf2, (w_px, h_px) = self.canvas.print_to_buffer()
            arr2 = np.frombuffer(buf2, dtype=np.uint8)
            if arr2.size == (w_px * h_px * 4):
                rgba = arr2.reshape((h_px, w_px, 4))
                return self._rgba_to_rgb_uint8(rgba, bg=(255,255,255))
        except Exception:
            pass
        return np.full((self.height, self.width, 3), 255, dtype=np.uint8)

    def _compute_smoothed_ylim(self, ymin: float, ymax: float) -> Tuple[float, float]:
        """
        Si y_min_fixed/y_max_fixed están definidos, devuelvelos.
        Si no, aplica suavizado exponencial entre el valor previo y el actual.
        y_smooth es alpha en [0..1] donde 0 = no smoothing (usar current),
        y_smooth cercano a 1 = lenta adaptación.
        """
        if self.y_min_fixed is not None and self.y_max_fixed is not None:
            return (self.y_min_fixed, self.y_max_fixed)

        current = (float(ymin), float(ymax))
        if self._smoothed_ylim is None or self.y_smooth <= 0.0:
            self._smoothed_ylim = current
            return current

        alpha = self.y_smooth
        prev_min, prev_max = self._smoothed_ylim
        new_min = prev_min * (1.0 - alpha) + current[0] * alpha
        new_max = prev_max * (1.0 - alpha) + current[1] * alpha
        if new_max == new_min:
            new_max = new_min + 1.0
            new_min = new_min - 1.0
        self._smoothed_ylim = (new_min, new_max)
        return self._smoothed_ylim

    def write_frame_from_arrays_with_timestamps(self,
                                               processed: np.ndarray,
                                               timestamps: np.ndarray,
                                               display_window_seconds: float = 6.0):
        """
        processed/timestamps: arrays length == self.window
        display_window_seconds: rango visible en X (ej. 6)
        NOTE: ahora solo recibimos la señal procesada (normalizada) y las timestamps.
        """
        if self._closed:
            raise RuntimeError("Recorder already closed")
        if processed is None or timestamps is None:
            return
        if processed.shape[0] != self.window or timestamps.shape[0] != self.window:
            raise ValueError("processed/timestamps must have length == recorder.window")

        if self.start_time is None:
            self.start_time = float(timestamps[0])

        t_now = float(timestamps[-1])
        t0 = t_now - float(display_window_seconds)

        x_all = timestamps - t0
        mask = (x_all >= 0.0) & (x_all <= display_window_seconds)

        x_disp = x_all[mask]
        proc_disp = processed[mask]

        if x_disp.size == 0:
            img = np.full((self.height, self.width, 3), 255, dtype=np.uint8)
            bgr = cv2.cvtColor(img, cv2.COLOR_RGB2BGR)
            self._ensure_writer()
            self.writer.write(bgr)
            return

        # Actualizar la línea procesada
        self.proc_line.set_data(x_disp, proc_disp)

        # Mantener X en 0..display_window_seconds
        self.ax.set_xlim(0.0, display_window_seconds)

        # Calcular límites Y (fijos o suavizados) usando solo proc_disp
        ymin = float(np.min(proc_disp))
        ymax = float(np.max(proc_disp))
        if ymax == ymin:
            ymax += 1.0
            ymin -= 1.0

        ymin_use, ymax_use = self._compute_smoothed_ylim(ymin, ymax)
        self.ax.set_ylim(ymin_use, ymax_use)

        # ETIQUETAS X: segundos enteros que aumentan conforme pasa el tiempo
        step = 1.0
        ticks = np.arange(0.0, display_window_seconds + 0.001, step)
        self.ax.set_xticks(ticks)

        elapsed_start_int = int(np.floor(t0 - self.start_time))
        if elapsed_start_int < 0:
            elapsed_start_int = 0
        labels = [str(elapsed_start_int + int(t)) for t in ticks]
        self.ax.set_xticklabels(labels, rotation=0, fontsize=8, color='#111111')

        # Asegurar que los ticks/valores y ejes se vean bien
        self.ax.tick_params(axis='both', which='both', labelsize=9, colors='#111111')

        # Render y escribir frame
        self.canvas.draw()
        img_rgb = self._get_canvas_rgb()
        if (img_rgb.shape[0] != self.height) or (img_rgb.shape[1] != self.width):
            img_rgb = cv2.resize(img_rgb, (self.width, self.height), interpolation=cv2.INTER_LINEAR)
        bgr = cv2.cvtColor(img_rgb, cv2.COLOR_RGB2BGR)
        self._ensure_writer()
        self.writer.write(bgr)

    def close(self):
        if self._closed:
            return
        self._closed = True
        if self.writer is not None:
            try:
                self.writer.release()
            except Exception:
                pass
        try:
            plt.close(self.fig)
        except Exception:
            pass

    def get_video_path(self):
        return self.video_path
