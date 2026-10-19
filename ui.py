"""Shared drawing primitives and bundled typography for the desktop UI."""
from functools import lru_cache
from pathlib import Path
import math

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont


def color(hex_value):
    value = hex_value.lstrip('#')
    return tuple(int(value[i:i+2], 16) for i in (4, 2, 0))


BG = color('#0B111C')
SURFACE = color('#111C2C')
RAISED = color('#19283B')
BORDER = color('#28394F')
WHITE = color('#EDF4FA')
MUTED = color('#91A2B9')
FAINT = color('#60748E')
MINT = color('#69E4C5')
AMBER = color('#F6C777')
RED = color('#FF817B')
BLUE = color('#91B8FF')
FONTS = Path(__file__).resolve().parent / 'assets' / 'fonts'


def mix(a, b, amount):
    return tuple(round(x*(1-amount)+y*amount) for x, y in zip(a, b))


@lru_cache(maxsize=64)
def font(size, bold=False):
    path = FONTS / ('FiraSans-SemiBold.ttf' if bold else 'FiraSans-Regular.ttf')
    try:
        return ImageFont.truetype(str(path), int(size))
    except OSError as exc:
        raise RuntimeError(f'Cannot load bundled UI font: {path}') from exc


def measure(value, size=16, bold=False):
    return math.ceil(font(size, bold).getlength(str(value)))


def fit(value, width, size=16, bold=False):
    value = str(value)
    if measure(value, size, bold) <= width:
        return value
    while value and measure(value+'…', size, bold) > width:
        value = value[:-1]
    return value+'…'


@lru_cache(maxsize=768)
def _letters(value, size, bold):
    mask = Image.new('L', (measure(value, size, bold)+4, size+12))
    ImageDraw.Draw(mask).text((1, 1), value, font=font(size, bold), fill=255, anchor='lt')
    return np.asarray(mask)


def text(image, value, x, y, size=16, ink=WHITE, bold=False, align='left', width=None):
    value = fit(value, width, size, bold) if width is not None else str(value)
    if not value:
        return
    if align == 'center':
        x -= measure(value, size, bold)/2
    elif align == 'right':
        x -= measure(value, size, bold)
    mask = _letters(value, int(size), bold)
    x, y = round(x), round(y)
    h, w = mask.shape
    x0, y0 = max(0, x), max(0, y)
    x1, y1 = min(image.shape[1], x+w), min(image.shape[0], y+h)
    if x1 <= x0 or y1 <= y0:
        return
    alpha = mask[y0-y:y1-y, x0-x:x1-x, None].astype(np.uint16)
    area = image[y0:y1, x0:x1]
    area[:] = ((area.astype(np.uint16)*(255-alpha) + np.array(ink, dtype=np.uint16)*alpha+127)//255).astype(np.uint8)


def wrap(image, value, x, y, width, size=16, ink=MUTED, line_height=None, max_lines=None):
    line_height = line_height or round(size*1.5)
    lines, line = [], ''
    for word in value.split():
        candidate = f'{line} {word}'.strip()
        if line and measure(candidate, size) > width:
            lines.append(line)
            line = word
        else:
            line = candidate
    if line:
        lines.append(line)
    if max_lines and len(lines) > max_lines:
        lines = lines[:max_lines]
        lines[-1] = fit(lines[-1]+'…', width, size)
    for line in lines:
        text(image, line, x, y, size, ink, width=width)
        y += line_height
    return y


def rounded(image, x, y, w, h, fill=SURFACE, radius=16, stroke=None):
    x, y, w, h = map(round, (x, y, w, h))
    if w <= 0 or h <= 0:
        return
    if stroke is not None:
        rounded(image, x, y, w, h, stroke, radius)
        rounded(image, x+1, y+1, w-2, h-2, fill, max(0, radius-1))
        return
    r = min(round(radius), (w-1)//2, (h-1)//2)
    if r <= 0:
        cv2.rectangle(image, (x, y), (x+w-1, y+h-1), fill, -1)
        return
    cv2.rectangle(image, (x+r, y), (x+w-r-1, y+h-1), fill, -1)
    cv2.rectangle(image, (x, y+r), (x+w-1, y+h-r-1), fill, -1)
    for cx, cy in ((x+r, y+r), (x+w-r-1, y+r), (x+r, y+h-r-1), (x+w-r-1, y+h-r-1)):
        cv2.circle(image, (cx, cy), r, fill, -1, cv2.LINE_AA)


def card(image, x, y, w, h, fill=SURFACE, radius=18, stroke=BORDER):
    rounded(image, x, y+5, w, h, mix(BG, (0, 0, 0), .24), radius)
    rounded(image, x, y, w, h, fill, radius, stroke)


def pill(image, value, x, y, ink=MINT, size=11, fill=None):
    w = measure(value, size, True)+22
    rounded(image, x, y, w, 25, fill or mix(SURFACE, ink, .12), 8)
    text(image, value, x+11, y+6, size, ink, True)
    return w


def keycap(image, value, x, y, size=11, ink=WHITE, fill=RAISED):
    w = max(24, measure(value, size, True)+14)
    rounded(image, x, y, w, 24, fill, 6, mix(fill, WHITE, .12))
    text(image, value, x+w/2, y+6, size, ink, True, align='center')
    return w


def shortcut(image, key, label, x, y, size=12):
    w = keycap(image, key, x, y)
    text(image, label, x+w+7, y+6, size, MUTED)
    return x+w+measure(label, size)+24


def button(image, label, key, x, y, w, primary=True, ink=MINT):
    fill = ink if primary else RAISED
    fg = BG if primary else WHITE
    rounded(image, x, y, w, 50, fill, 12, None if primary else BORDER)
    kw = keycap(image, key, x+13, y+13, 11, fg, mix(fill, BG, .12))
    text(image, label, x+kw+26, y+17, 16, fg, True)
    text(image, '→', x+w-18, y+15, 20, fg, align='right')


def bar(image, x, y, w, value, ink=MINT, h=5):
    rounded(image, x, y, w, h, BORDER, h//2)
    if value > 0:
        rounded(image, x, y, max(h, w*min(1., value)), h, ink, h//2)


@lru_cache(maxsize=16)
def _photo_mask(w, h, radius):
    mask = np.zeros((h, w), np.uint8)
    rounded(mask, 0, 0, w, h, 255, radius)
    return mask[:, :, None].astype(np.uint16)


def photo(image, frame, x, y, radius=10):
    h, w = frame.shape[:2]
    alpha = _photo_mask(w, h, radius)
    area = image[y:y+h, x:x+w]
    area[:] = ((area.astype(np.uint16)*(255-alpha)+frame.astype(np.uint16)*alpha+127)//255).astype(np.uint8)


def icon(image, kind, x, y, size=32, ink=MINT):
    """Small native vector marks; x/y locate the icon's center."""
    x, y, r = round(x), round(y), max(4, round(size/2))
    if kind in ('eye', 'closed'):
        cv2.ellipse(image, (x, y), (r, r//2), 0, 0, 360, ink, 2, cv2.LINE_AA)
        if kind == 'eye':
            cv2.circle(image, (x, y), max(2, r//4), ink, -1, cv2.LINE_AA)
        else:
            cv2.line(image, (x-r, y+r//2), (x+r, y-r//2), ink, 2, cv2.LINE_AA)
    elif kind == 'head':
        cv2.circle(image, (x, y-r//3), r//2, ink, 2, cv2.LINE_AA)
        cv2.ellipse(image, (x, y+r), (r, r*2//3), 0, 190, 350, ink, 2, cv2.LINE_AA)
    elif kind == 'wheel':
        cv2.circle(image, (x, y), r, ink, 2, cv2.LINE_AA)
        cv2.circle(image, (x, y), max(2, r//4), ink, 2, cv2.LINE_AA)
        for dx, dy in ((-r, -r//3), (r, -r//3), (0, r)):
            cv2.line(image, (x, y), (x+dx, y+dy), ink, 2, cv2.LINE_AA)
    elif kind == 'flag':
        cv2.line(image, (x-r//2, y-r), (x-r//2, y+r), ink, 2, cv2.LINE_AA)
        for row in range(2):
            for col in range(3):
                if (row+col) % 2 == 0:
                    cv2.rectangle(image, (x-r//2+col*r//2, y-r+row*r//2),
                                  (x-r//2+(col+1)*r//2, y-r+(row+1)*r//2), ink, -1)
    elif kind == 'pause':
        for dx in (-r//2, r//2):
            rounded(image, x+dx-2, y-r, 5, r*2, ink, 2)
    elif kind == 'alert':
        cv2.circle(image, (x, y), r, ink, 2, cv2.LINE_AA)
        cv2.line(image, (x, y-r//2), (x, y+1), ink, 2, cv2.LINE_AA)
        cv2.circle(image, (x, y+r//2), 1, ink, -1, cv2.LINE_AA)
    elif kind == 'trophy':
        cup = np.array([(x-r, y-r), (x+r, y-r), (x+r*3//4, y+r//4),
                        (x, y+r*2//3), (x-r*3//4, y+r//4)], dtype=np.int32)
        cv2.fillConvexPoly(image, cup, ink, cv2.LINE_AA)
        for sign in (-1, 1):
            cv2.ellipse(image, (x+sign*r, y-r//3), (r//2, r*2//3), 0, 0, 360, ink, 3, cv2.LINE_AA)
        cv2.line(image, (x, y+r//2), (x, y+r+6), ink, 4)
        rounded(image, x-r//2, y+r+4, r, 5, ink, 2)
