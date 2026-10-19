"""OpenCV arcade rendering using the supplied transparent PNG artwork."""
from pathlib import Path
import math

import cv2
import numpy as np

from game_core import ROAD_LEFT, ROAD_RIGHT, ROAD_TOP, ROAD_BOTTOM, ASLEEP_SECONDS, DIFFICULTIES
from drivers import DriverUI, format_time

WIDTH, HEIGHT = 1280, 800
BG = (22, 17, 12)
PANEL = (35, 29, 22)
WHITE = (238, 241, 233)
MUTED = (154, 158, 143)
TEAL = (183, 231, 73)
AMBER = (81, 192, 255)
RED = (107, 100, 249)
FONT = cv2.FONT_HERSHEY_SIMPLEX


def text(image, value, x, y, size=.55, color=WHITE, weight=1):
    cv2.putText(image, str(value), (int(x), int(y)), FONT, size, color, weight, cv2.LINE_AA)


def fit_text(value, width, size=.45):
    if cv2.getTextSize(value, FONT, size, 1)[0][0] <= width:
        return value
    while value and cv2.getTextSize(value+'...', FONT, size, 1)[0][0] > width:
        value = value[:-1]
    return value+'...'


def wrapped(image, value, x, y, max_width, size=.45, color=MUTED, line_height=22):
    line = ''
    for word in value.split():
        candidate = f'{line} {word}'.strip()
        if cv2.getTextSize(candidate, FONT, size, 1)[0][0] > max_width and line:
            text(image, line, x, y, size, color)
            y += line_height
            line = word
        else:
            line = candidate
    text(image, line, x, y, size, color)
    return y + line_height


def sprite(image, asset, rect):
    x, y, w, h = [int(round(v)) for v in (rect.x, rect.y, rect.w, rect.h)]
    if w <= 0 or h <= 0:
        return
    ah, aw = asset.shape[:2]
    scale = min(w / aw, h / ah)
    sw, sh = max(1, int(aw * scale)), max(1, int(ah * scale))
    resized = cv2.resize(asset, (sw, sh), interpolation=cv2.INTER_AREA if scale < 1 else cv2.INTER_LINEAR)
    x += (w - sw) // 2
    y += (h - sh) // 2
    x0, y0 = max(x, 0), max(y, 0)
    x1, y1 = min(x + sw, image.shape[1]), min(y + sh, image.shape[0])
    if x1 <= x0 or y1 <= y0:
        return
    cut = resized[y0-y:y1-y, x0-x:x1-x]
    alpha = cut[:, :, 3:4].astype(np.float32) / 255
    image[y0:y1, x0:x1] = cut[:, :, :3] * alpha + image[y0:y1, x0:x1] * (1-alpha)


class Renderer:
    def __init__(self, assets):
        self.cars = [self.load(assets / f'car{i}.png') for i in range(1, 4)]
        self.motors = [self.load(assets / f'Motor{i}.png') for i in range(1, 4)]

    @staticmethod
    def load(path):
        raw = cv2.imread(str(path), cv2.IMREAD_UNCHANGED)
        if raw is None or raw.ndim != 3 or raw.shape[2] != 4:
            raise RuntimeError(f'Expected transparent PNG asset: {path}')
        ys, xs = np.where(raw[:, :, 3] > 0)
        if not len(xs):
            raise RuntimeError(f'PNG is empty: {path}')
        return raw[ys.min():ys.max()+1, xs.min():xs.max()+1]

    def draw(self, game, obs, tracking, closed, car, audio_status, threshold, demo=False,
             selected_difficulty=None, steering_status='live', eyes_valid=True, ui=None, selected_car=None):
        ui = ui or DriverUI()
        image = np.full((HEIGHT, WIDTH, 3), BG, dtype=np.uint8)
        text(image, 'SYSTEMS FAIR  /  INTERACTIVE DRIVE LAB', 38, 32, .43, TEAL)
        text(image, 'NIGHT SHIFT', 36, 83, 1.35, WHITE, 2)
        driver_label = (f"{ui.driver['name']} / {ui.driver['id']} / BEST {format_time(ui.driver['best_seconds'])}"
                        if ui.driver else 'Stay alert. Find your gap.')
        text(image, fit_text(driver_label, 480, .42), 39, 112, .42, MUTED)
        text(image, 'DODGED', 546, 38, .39, MUTED)
        text(image, f'{game.score:02}', 544, 84, 1.3, TEAL, 2)
        text(image, 'DRIVE TIME', 686, 38, .39, MUTED)
        minutes, seconds = divmod(int(game.elapsed), 60)
        text(image, f'{minutes:02}:{seconds:02}', 682, 83, 1, WHITE, 2)
        text(image, f'{game.difficulty.upper()}  /  EACH BIKE FASTER', 546, 112, .40, AMBER)
        cv2.line(image, (902, 25), (902, 756), (58, 54, 43), 1)

        # Road and moving markings. Player and hazards share these coordinates.
        cv2.rectangle(image, (44, ROAD_TOP), (877, ROAD_BOTTOM), (29, 31, 21), -1)
        cv2.rectangle(image, (ROAD_LEFT, ROAD_TOP), (ROAD_RIGHT, ROAD_BOTTOM), (45, 39, 31), -1)
        offset = int(game.elapsed * 190) % 90
        for y in range(ROAD_TOP - 90 + offset, ROAD_BOTTOM, 90):
            y0, y1 = max(ROAD_TOP, y), min(ROAD_BOTTOM, y + 42)
            if y1 > y0:
                for x in (330, 590):
                    cv2.rectangle(image, (x-2, y0), (x+2, y1), (91, 87, 70), -1)
                for x in (55, 860):
                    cv2.rectangle(image, (x, y0), (x+5, y1), TEAL, -1)
        for x in (ROAD_LEFT, ROAD_RIGHT):
            cv2.line(image, (x, ROAD_TOP), (x, ROAD_BOTTOM), (140, 161, 83), 2)
        for i in range(30):
            y = ROAD_TOP + i
            image[y, ROAD_LEFT:ROAD_RIGHT] = image[y, ROAD_LEFT:ROAD_RIGHT] * (0.35 + i / 46)
        text(image, 'INCOMING TRAFFIC', 380, 169, .38, MUTED)
        # Draw only inside the road so incoming artwork cannot cover the header.
        road = image[ROAD_TOP:ROAD_BOTTOM, ROAD_LEFT:ROAD_RIGHT]
        from game_core import Rect
        for bike in game.bikes:
            r = bike.rect
            sprite(road, self.motors[bike.style], Rect(r.x-ROAD_LEFT, r.y-ROAD_TOP, r.w, r.h))
        p = game.player
        x0, y0, x1, y1 = int(p.x), int(p.y), int(p.x+p.w), int(p.y+p.h)
        color = RED if game.state == 'over' else AMBER if tracking and steering_status != 'live' else TEAL if tracking else MUTED
        cv2.rectangle(image, (x0, y0), (x1, y1), color, 1)
        for x, dx in ((x0, 1), (x1, -1)):
            for y, dy in ((y0, 1), (y1, -1)):
                cv2.line(image, (x, y), (x+dx*14, y), color, 3)
                cv2.line(image, (x, y), (x, y+dy*14), color, 3)
        sprite(image, self.cars[car], p)
        text(image, 'FACE HITBOX', x0, y0-9, .34, color)

        # Driver instrument panel.
        x = 934
        text(image, 'DRIVER MONITOR', x, 47, .57, WHITE, 1)
        status = ('STEERING / '+steering_status.upper() if tracking and steering_status != 'live'
                  else 'LIVE / LOCAL CAMERA' if not demo else 'DEMO / SIMULATED INPUT')
        text(image, status, x, 73, .38, color)
        cv2.rectangle(image, (x, 95), (1244, 307), PANEL, -1)
        if obs.frame is not None:
            frame = cv2.flip(obs.frame, 1).copy()
            fh, fw = frame.shape[:2]
            if obs.box is not None:
                bx0, by0, bx1, by1 = obs.box
                cv2.rectangle(frame, (int(fw-bx1), int(by0)), (int(fw-bx0), int(by1)), color, 2)
            scale = min(310 / fw, 212 / fh)
            preview = cv2.resize(frame, (max(1, int(fw*scale)), max(1, int(fh*scale))))
            ph, pw = preview.shape[:2]
            px, py = x + (310-pw)//2, 95 + (212-ph)//2
            image[py:py+ph, px:px+pw] = preview
        else:
            text(image, 'HEAD LEFT  < >  HEAD RIGHT', x+24, 189, .42, MUTED)
            text(image, 'Camera preview appears here', x+28, 217, .38, MUTED)
        state = ('WAITING FOR TRACKING' if not tracking else 'EYES UNAVAILABLE' if not eyes_valid else 'ASLEEP' if game.asleep
                 else 'EYES CLOSED' if closed else 'EYES OPEN')
        state_color = MUTED if not tracking or not eyes_valid else RED if game.asleep else AMBER if closed else TEAL
        cv2.circle(image, (x+6, 338), 5, state_color, -1, cv2.LINE_AA)
        text(image, state, x+22, 344, .53, state_color)
        ear = f'{obs.ear:.3f}' if eyes_valid and math.isfinite(obs.ear) else '--'
        text(image, f'EAR  {ear}    /    LIMIT  {threshold:.2f}', x, 371, .4, MUTED)
        text(image, f'CLOSED  {min(game.closed_seconds, ASLEEP_SECONDS):.1f} / {ASLEEP_SECONDS:.1f} SECONDS',
             x, 394, .35, state_color)

        cv2.rectangle(image, (x, 418), (1244, 535), PANEL, -1)
        pending = game.pending is not None
        text(image, 'NEXT MOTORCYCLE' if pending else 'ROAD WATCH', x+17, 445, .4, MUTED)
        text(image, f'{max(0, game.pending):04.1f} s' if pending else 'STAY SHARP', x+16, 489, .91 if pending else .69,
             AMBER if pending else WHITE, 2)
        text(image, 'Armed after 3 seconds of closed eyes' if pending else '3s closed eyes, then a 3-5s timer', x+17, 518, .35, MUTED)

        text(image, 'LONGEST DRIVES', x, 562, .46, WHITE)
        text(image, 'ALL LEVELS    /    B  VIEW RANKINGS', x, 583, .34, TEAL)
        for i, driver in enumerate(ui.rankings[:5]):
            y = 610+i*28
            active = ui.driver and driver['id'] == ui.driver['id']
            color = TEAL if active else WHITE
            text(image, str(driver['rank']), x, y, .42, color)
            text(image, fit_text(driver['name'], 172, .42), x+25, y, .42, color)
            text(image, format_time(driver['best_seconds']), x+225, y, .43, AMBER)
        if not ui.rankings:
            wrapped(image, 'No drives yet. Your first run will appear here.', x, 620, 300, .45)
        text(image, audio_status, x, 750, .35, MUTED)
        footer = ('TYPE NAME   BACKSPACE Delete   ENTER Continue   ESC Exit' if game.state == 'name' else
                  'ENTER Start   G Settings   B Rankings   P Pause   R New driver   M Sound   F Fullscreen   ESC Exit')
        text(image, footer, 40, 784, .40, MUTED)

        if game.state == 'name':
            self.name_overlay(image, ui)
        elif game.state == 'ready':
            self.overlay(image, 'YOUR HEAD. YOUR WHEEL.', [
                f"Welcome, {ui.driver['name']}. Move your head to steer." if ui.driver else 'Move left and right to dodge incoming motorcycles.',
                '3 seconds of closed eyes arms a 3-5 second timer.',
                'G: settings and car selection. B: longest drives.'
            ], 'PRESS ENTER TO DRIVE' if tracking else 'WAITING FOR YOUR FACE', TEAL)
        elif game.state == 'over':
            reason = {'left road edge': 'You hit the left side of the road.',
                      'right road edge': 'You hit the right side of the road.',
                      'motorcycle': 'You collided with a motorcycle.'}.get(game.crash_reason, 'Your car crashed.')
            self.overlay(image, 'YOU CRASHED', [
                f'{game.score} motorcycles dodged in {int(game.elapsed)} seconds.',
                reason,
                ui.result_message or 'Stay inside the road and avoid incoming traffic.'
            ], 'PRESS R FOR THE NEXT DRIVER', RED)
        elif game.state == 'paused':
            self.overlay(image, 'TAKE A BREATHER', ['Your drive and spawn timer are paused.',
                                                    'Get comfortable, then continue.'], 'PRESS P TO RESUME', TEAL)
        elif game.state == 'settings':
            self.settings_overlay(image, selected_difficulty or game.difficulty, car if selected_car is None else selected_car)
        elif game.state == 'rankings':
            self.rankings_overlay(image, ui)
        elif not tracking:
            self.overlay(image, 'TRACKING PAUSED', ['Keep your face and eyes inside the camera view.',
                                                   'The road resumes when tracking returns.'], 'WAITING FOR YOUR FACE', AMBER)
        if obs.error:
            cv2.rectangle(image, (90, 551), (830, 704), PANEL, -1)
            text(image, 'CAMERA NEEDS ATTENTION', 113, 581, .5, RED)
            wrapped(image, obs.error, 113, 611, 692, .43, WHITE)
        if ui.save_error:
            cv2.rectangle(image, (100, 560), (840, 688), PANEL, -1)
            text(image, 'RECORD NOT SAVED', 121, 587, .55, RED, 2)
            wrapped(image, ui.save_error[:180], 121, 614, 690, .38, WHITE, 19)
            text(image, 'Check folder access, then press ENTER to retry.', 121, 672, .43, AMBER)
        if demo:
            text(image, 'DEMO: MOUSE / A,D STEER   SPACE EYES   L TRACKING LOSS', 120, 737, .42, AMBER)
        return image

    def settings_overlay(self, image, selected, car):
        from game_core import Rect
        shade = image[165:655, 133:788]
        shade[:] = shade * .10 + np.array(PANEL) * .90
        cv2.rectangle(image, (133, 165), (788, 655), (70, 74, 57), 1)
        text(image, 'DRIVE SETTINGS', 165, 208, .85, WHITE, 2)
        text(image, 'DIFFICULTY  /  PRESS 1-4', 168, 235, .39, MUTED)
        descriptions = ['A gentle start. Small speed increases.',
                        'A brisk start. Steady speed increases.',
                        'Fast from the start. Bigger increases.',
                        'Extreme speed. Relentless increases.']
        for i, (name, description) in enumerate(zip(DIFFICULTIES, descriptions)):
            y = 250 + i * 37
            active = name == selected
            if active:
                cv2.rectangle(image, (158, y), (761, y+32), (60, 65, 35), -1)
                cv2.rectangle(image, (158, y), (761, y+32), TEAL, 1)
            text(image, f'{i+1}  {name.upper()}', 172, y+24, .48, TEAL if active else WHITE, 2 if active else 1)
            text(image, description, 377, y+24, .42, MUTED)
        text(image, 'YOUR CAR  /  LEFT & RIGHT ARROWS', 168, 420, .39, MUTED)
        for i, asset in enumerate(self.cars):
            gx = 168+i*198
            cv2.rectangle(image, (gx, 434), (gx+178, 524), PANEL, -1)
            cv2.rectangle(image, (gx, 434), (gx+178, 524), TEAL if i == car else (70, 74, 57), 1)
            sprite(image, asset, Rect(gx+40, 440, 98, 66))
            text(image, ['GRAPHITE', 'RED', 'BLUE'][i], gx+49, 518, .36, TEAL if i == car else MUTED)
        text(image, 'Every motorcycle is faster than the last.', 168, 553, .43, WHITE)
        text(image, 'A new difficulty saves this run and asks for a driver.', 168, 580, .40, MUTED)
        text(image, 'ENTER Apply     ESC Cancel', 168, 623, .55, TEAL, 2)

    @staticmethod
    def name_overlay(image, ui):
        cv2.rectangle(image, (133, 235), (788, 570), PANEL, -1)
        cv2.rectangle(image, (133, 235), (788, 570), (70, 74, 57), 1)
        text(image, "WHO'S DRIVING?", 167, 286, .88, WHITE, 2)
        text(image, 'DRIVER NAME', 168, 326, .40, MUTED)
        cv2.rectangle(image, (167, 341), (752, 401), BG, -1)
        cv2.rectangle(image, (167, 341), (752, 401), TEAL, 1)
        value = ui.name_input or 'Type your name...'
        text(image, value, 183, 381, .75, WHITE if ui.name_input else MUTED)
        if ui.name_input:
            cursor = 186+cv2.getTextSize(ui.name_input, FONT, .75, 1)[0][0]
            cv2.line(image, (cursor, 354), (cursor, 388), TEAL, 1)
        if ui.name_error:
            wrapped(image, ui.name_error[:180], 168, 435, 570, .42, RED, 21)
        elif ui.name_match:
            text(image, f"RETURNING DRIVER  /  {ui.name_match['id']}", 168, 438, .48, TEAL)
            text(image, f"Personal best: {format_time(ui.name_match['best_seconds'])}", 168, 469, .48, WHITE)
        else:
            text(image, 'New name? Your driver ID will be created automatically.', 168, 438, .44, MUTED)
            text(image, 'Use the same name next time to improve your record.', 168, 469, .44, MUTED)
        text(image, 'ENTER Continue     BACKSPACE Delete', 168, 536, .52, TEAL, 2)

    @staticmethod
    def rankings_overlay(image, ui):
        cv2.rectangle(image, (110, 175), (865, 700), PANEL, -1)
        cv2.rectangle(image, (110, 175), (865, 700), (70, 74, 57), 1)
        text(image, 'LONGEST DRIVES', 143, 225, .90, WHITE, 2)
        text(image, 'ALL DIFFICULTIES  /  PERSONAL BEST ACTIVE DRIVING TIME', 145, 251, .36, MUTED)
        for label, x in [('RANK', 143), ('DRIVER', 218), ('ID', 470), ('TIME', 582), ('LEVEL', 714)]:
            text(image, label, x, 286, .37, MUTED)
        for i, driver in enumerate(ui.rankings[ui.ranking_page*8:ui.ranking_page*8+8]):
            y = 325+i*37
            color = TEAL if ui.driver and driver['id'] == ui.driver['id'] else WHITE
            text(image, str(driver['rank']), 143, y, .49, color)
            text(image, fit_text(driver['name'], 235, .46), 218, y, .46, color)
            text(image, driver['id'], 470, y, .43, MUTED)
            text(image, format_time(driver['best_seconds']), 582, y, .51, AMBER)
            text(image, (driver['best_difficulty'] or '-').upper(), 714, y, .36, MUTED)
        if not ui.rankings:
            text(image, 'Complete your first drive to enter the rankings.', 145, 354, .50, MUTED)
        pages = max(1, (len(ui.rankings)+7)//8)
        text(image, f'PAGE {ui.ranking_page+1}/{pages}   /   {len(ui.rankings)} DRIVERS', 145, 646, .41, MUTED)
        text(image, 'ARROW KEYS Pages     B / ESC Back', 145, 680, .49, TEAL, 2)

    @staticmethod
    def overlay(image, title, lines, action, color):
        shade = image[236:530, 133:788]
        shade[:] = shade * .14 + np.array(PANEL) * .86
        cv2.rectangle(image, (133, 236), (788, 530), (70, 74, 57), 1)
        cv2.rectangle(image, (133, 236), (137, 530), color, -1)
        text(image, title, 167, 296, .84, WHITE, 2)
        for i, line in enumerate(lines):
            text(image, line, 168, 341+i*30, .47, MUTED)
        text(image, action, 168, 487, .60, color, 2)
