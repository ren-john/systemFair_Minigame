"""EAR and face bounds from MediaPipe Face Mesh in camera pixel coordinates."""
import numpy as np

EAR_THRESHOLD = .22
# Subject's anatomical right/left, before the preview is mirrored.
RIGHT_EYE = (33, 160, 158, 133, 153, 144)
LEFT_EYE = (362, 385, 387, 263, 373, 380)


def assess_eye(eye, frame_size):
    eye = np.asarray(eye, dtype=float)
    if eye.shape != (6, 2) or not np.isfinite(eye).all():
        return float('nan'), 0., False
    width = float(np.linalg.norm(eye[0] - eye[3]))
    if width < 3:
        return float('nan'), width, False
    ear = float((np.linalg.norm(eye[1]-eye[5]) + np.linalg.norm(eye[2]-eye[4])) / (2*width))
    fw, fh = frame_size
    inside = ((eye[:, 0] >= 0) & (eye[:, 0] < fw) & (eye[:, 1] >= 0) & (eye[:, 1] < fh)).all()
    along = (eye-eye[0]) @ ((eye[3]-eye[0])/width) / width
    valid = (inside and ear <= .8 and ((along >= -.15) & (along <= 1.15)).all()
             and along[1] <= along[2]+.1 and along[5] <= along[4]+.1)
    return ear, width, bool(valid)


def mesh_measurements(points, frame_size, eye_mode='auto', width_ratio=.60):
    """Return face rectangle and EAR; unavailable eye data remains NaN."""
    points = np.asarray(points, dtype=float)
    if points.ndim != 2 or points.shape[0] < 468 or points.shape[1] != 2 or not np.isfinite(points).all():
        return None, float('nan')
    fw, fh = frame_size
    lo = np.maximum(points.min(axis=0), [0, 0])
    hi = np.minimum(points.max(axis=0), [fw, fh])
    if np.any(hi-lo < 10):
        return None, float('nan')
    box = np.array([*lo, *hi])
    eyes = {'right': assess_eye(points[list(RIGHT_EYE)], frame_size),
            'left': assess_eye(points[list(LEFT_EYE)], frame_size)}
    valid = {name: item for name, item in eyes.items() if item[2]}
    if eye_mode != 'auto':
        return box, valid[eye_mode][0] if eye_mode in valid else float('nan')
    if not valid:
        return box, float('nan')
    if len(valid) == 1:
        return box, next(iter(valid.values()))[0]
    largest = max(valid.values(), key=lambda item: item[1])
    smallest = min(valid.values(), key=lambda item: item[1])
    ear = largest[0] if smallest[1]/largest[1] < width_ratio else (largest[0]+smallest[0])/2
    return box, ear
