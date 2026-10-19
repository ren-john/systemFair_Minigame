"""Camera and MediaPipe Face Mesh on a worker, leaving the game responsive."""
from dataclasses import dataclass
import threading
import time

import cv2
import numpy as np

from face_geometry import mesh_measurements


@dataclass
class Observation:
    frame: object = None
    box: object = None
    ear: float = float('nan')
    inference_ms: float = 0
    timestamp: float = 0
    error: str = ''
    points: object = None


class Tracker:
    def __init__(self, source, confidence, eye_mode, width_ratio):
        self.settings = source, confidence, eye_mode, width_ratio
        self.latest = Observation()
        self.lock = threading.Lock()
        self.stop = threading.Event()
        self.thread = threading.Thread(target=self.run, name='face-tracker', daemon=True)
        self.thread.start()

    def snapshot(self):
        with self.lock:
            return self.latest

    def publish(self, result):
        with self.lock:
            self.latest = result

    def run(self):
        capture = mesh = None
        try:
            import mediapipe as mp
            source, confidence, mode, width_ratio = self.settings
            mesh = mp.solutions.face_mesh.FaceMesh(
                static_image_mode=False, max_num_faces=1, refine_landmarks=True,
                min_detection_confidence=confidence, min_tracking_confidence=.5)
            capture = cv2.VideoCapture(source)
            if not capture.isOpened():
                raise RuntimeError('Cannot open camera. Check --source and camera permissions.')
            capture.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
            capture.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
            capture.set(cv2.CAP_PROP_BUFFERSIZE, 1)
            while not self.stop.is_set():
                ok, frame = capture.read()
                if not ok:
                    raise RuntimeError('Camera stopped sending frames. Restart with R to reconnect.')
                captured_at = time.monotonic()
                rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                rgb.flags.writeable = False
                started = time.perf_counter()
                result = mesh.process(rgb)
                ms = (time.perf_counter()-started)*1000
                box, ear, points = None, float('nan'), None
                if result.multi_face_landmarks:
                    h, w = frame.shape[:2]
                    points = np.array([(p.x*w, p.y*h) for p in result.multi_face_landmarks[0].landmark])
                    box, ear = mesh_measurements(points, (w, h), mode, width_ratio)
                self.publish(Observation(frame, box, ear, ms, captured_at, points=points))
        except Exception as exc:
            self.publish(Observation(error=f'{type(exc).__name__}: {exc}'))
        finally:
            if capture is not None:
                capture.release()
            if mesh is not None:
                mesh.close()

    def close(self):
        self.stop.set()
        self.thread.join(timeout=2)
