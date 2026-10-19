"""Polished desktop screens over the unchanged OpenCV game coordinates."""
import math

import cv2
import numpy as np

from game_core import Rect, ROAD_LEFT, ROAD_RIGHT, ROAD_TOP, ROAD_BOTTOM, ASLEEP_SECONDS, DIFFICULTIES, SCORE_CAP
from drivers import DriverUI, format_time, format_best
from ui import (BG, SURFACE, RAISED, BORDER, WHITE, MUTED, FAINT, MINT, AMBER, RED, BLUE,
                color, mix, text, measure, fit, wrap, rounded, card, pill, shortcut,
                button, bar, icon, photo)

WIDTH, HEIGHT = 1280, 800
STAGE_COLORS = {'easy': MINT, 'medium': BLUE, 'hard': AMBER, 'impossible': RED}


def sprite(image, asset, rect):
    x, y, w, h = [int(round(v)) for v in (rect.x, rect.y, rect.w, rect.h)]
    if w <= 0 or h <= 0:
        return
    ah, aw = asset.shape[:2]
    scale = min(w/aw, h/ah)
    sw, sh = max(1, int(aw*scale)), max(1, int(ah*scale))
    resized = cv2.resize(asset, (sw, sh), interpolation=cv2.INTER_AREA if scale < 1 else cv2.INTER_LINEAR)
    x, y = x+(w-sw)//2, y+(h-sh)//2
    x0, y0 = max(x, 0), max(y, 0)
    x1, y1 = min(x+sw, image.shape[1]), min(y+sh, image.shape[0])
    if x1 > x0 and y1 > y0:
        cut = resized[y0-y:y1-y, x0-x:x1-x]
        alpha = cut[:, :, 3:4].astype(np.float32)/255
        image[y0:y1, x0:x1] = cut[:, :, :3]*alpha + image[y0:y1, x0:x1]*(1-alpha)


def centered(image, value, y, size=16, ink=WHITE, bold=False, x=WIDTH/2, width=None):
    text(image, value, x, y, size, ink, bold, align='center', width=width)


def dim(image):
    image[:] = (image.astype(np.uint16)*30//100).astype(np.uint8)


class Renderer:
    def __init__(self, assets):
        self.cars = [self.load(assets / f'car{i}.png') for i in range(1, 4)]
        self.motors = [self.load(assets / f'Motor{i}.png') for i in range(1, 4)]
        yy, xx = np.mgrid[:HEIGHT, :WIDTH].astype(np.float32)
        glow = np.exp(-((xx-1000)**2+(yy-80)**2)/240000)
        self.background = np.empty((HEIGHT, WIDTH, 3), dtype=np.uint8)
        for c in range(3):
            self.background[:, :, c] = BG[c]+glow*(RAISED[c]-BG[c])*.7
        self.road_background = np.empty((ROAD_BOTTOM-ROAD_TOP, ROAD_RIGHT-ROAD_LEFT, 3), np.uint8)
        for y in range(self.road_background.shape[0]):
            self.road_background[y] = mix(color('#101A29'), color('#19283A'), y/self.road_background.shape[0])

    @staticmethod
    def load(path):
        raw = cv2.imread(str(path), cv2.IMREAD_UNCHANGED)
        if raw is None or raw.ndim != 3 or raw.shape[2] != 4:
            raise RuntimeError(f'Expected transparent PNG asset: {path}')
        ys, xs = np.where(raw[:, :, 3] > 0)
        if not len(xs):
            raise RuntimeError(f'PNG is empty: {path}')
        return raw[ys.min():ys.max()+1, xs.min():xs.max()+1]

    @staticmethod
    def brand(image, x=44, y=30, compact=False):
        rounded(image, x, y, 34, 34, mix(SURFACE, MINT, .15), 11)
        cv2.line(image, (x+11, y+23), (x+15, y+10), MINT, 2, cv2.LINE_AA)
        cv2.line(image, (x+20, y+23), (x+24, y+10), MINT, 2, cv2.LINE_AA)
        text(image, 'NIGHT SHIFT', x+47, y+1, 24, WHITE, True)
        text(image, 'SYSTEMS FAIR  /  HEAD-CONTROLLED ARCADE', x+48, y+34, 10, MUTED)
        if not compact:
            cv2.line(image, (44, 99), (1236, 99), BORDER, 1, cv2.LINE_AA)

    def screen_header(self, image, tag):
        self.brand(image)
        w = measure(tag, 11, True)+22
        pill(image, tag, 1236-w, 35, MUTED)

    @staticmethod
    def avatar(image, name, x, y, size=36):
        initials = ''.join(part[0] for part in name.split()[:2]).upper() or 'N'
        rounded(image, x, y, size, size, mix(SURFACE, MINT, .15), size//3)
        centered(image, initials, y+(size-14)//2, 14, MINT, True, x+size/2)

    def hero_road(self, image, x, y, w, h, car=0):
        rounded(image, x, y, w, h, color('#101E2B'), 20)
        def point(fraction, t):
            span = w*(.16+.81*t)
            return round(x+w/2+(fraction-.5)*span), round(y+t*h)
        polygon = np.array([point(0, 0), point(1, 0), point(1, 1), point(0, 1)], np.int32)
        cv2.fillConvexPoly(image, polygon, color('#1A3040'), cv2.LINE_AA)
        for side in (0, 1):
            cv2.line(image, point(side, 0), point(side, 1), mix(BORDER, MINT, .45), 2, cv2.LINE_AA)
        for lane in (1/3, 2/3):
            for start in (.08, .3, .52, .74, .96):
                cv2.line(image, point(lane, start), point(lane, min(1., start+.11)), color('#536B76'), 2, cv2.LINE_AA)
        sprite(image, self.motors[1], Rect(x+w*.43, y+h*.12, 32, 53))
        cv2.ellipse(image, (round(x+w*.54), round(y+h*.84)), (42, 12), 0, 0, 360, color('#0D1924'), -1)
        sprite(image, self.cars[car], Rect(x+w*.54-52, y+h*.39, 104, h*.53))

    def draw(self, game, obs, tracking, closed, car, audio_status, threshold, demo=False,
             steering_status='live', eyes_valid=True, ui=None, selected_car=None, celebration_time=0.):
        ui = ui or DriverUI()
        image = self.background.copy()
        if game.state == 'name':
            self.name_screen(image, ui, car)
        elif game.state == 'tutorial':
            self.tutorial_screen(image, ui, demo)
        elif game.state == 'settings':
            self.settings_screen(image, game, car if selected_car is None else selected_car)
        elif game.state == 'rankings':
            self.rankings_screen(image, ui)
        elif game.state == 'won':
            self.victory_screen(image, game, ui, celebration_time)
        else:
            self.dashboard(image, game, obs, tracking, closed, car, audio_status, demo, steering_status, eyes_valid, ui)
            if game.state == 'ready':
                self.ready_overlay(image, game, ui, tracking, bool(obs.error))
            elif game.state == 'over':
                self.result_overlay(image, game, ui)
            elif game.state == 'paused':
                self.pause_overlay(image)
            elif not tracking:
                self.tracking_overlay(image, obs.error)
        if ui.save_error:
            key = 'B / ESC' if game.state == 'rankings' else 'ESC' if game.state == 'settings' else 'ENTER'
            action = 'Back to retry' if game.state in ('rankings', 'settings') else 'Retry save'
            self.error_toast(image, 'Your result has not been saved', ui.save_error, key, action)
        return image

    def dashboard(self, image, game, obs, tracking, closed, car, audio_status, demo, steering_status, eyes_valid, ui):
        self.brand(image, 32, 23, compact=True)
        if ui.driver:
            self.avatar(image, ui.driver['name'], 32, 80, 28)
            text(image, ui.driver['name'], 71, 81, 14, WHITE, True, width=180)
            text(image, ui.driver['id'], 71, 102, 10, MUTED)
            pill(image, game.difficulty.upper(), 258, 84, STAGE_COLORS[game.difficulty], 10)
        else:
            text(image, 'Your head. Your wheel.', 33, 88, 16, MUTED)
        card(image, 382, 20, 230, 98)
        text(image, 'MISSION PROGRESS', 402, 35, 10, MUTED, True)
        text(image, f'{game.score:02}', 402, 53, 30, WHITE, True)
        text(image, f'/ {SCORE_CAP}', 447, 65, 15, MUTED)
        for i in range(SCORE_CAP):
            rounded(image, 402+i*19, 99, 14, 4, MINT if i < game.score else BORDER, 2)
        card(image, 628, 20, 250, 98)
        text(image, 'DRIVE TIME', 648, 35, 10, MUTED, True)
        text(image, format_time(game.elapsed), 648, 57, 29, WHITE, True, width=214)

        # These are the original collision coordinates. Only the artwork changes.
        rounded(image, 44, ROAD_TOP, 834, ROAD_BOTTOM-ROAD_TOP, color('#0D1723'), 15)
        image[ROAD_TOP:ROAD_BOTTOM, ROAD_LEFT:ROAD_RIGHT] = self.road_background
        for side in (ROAD_LEFT, ROAD_RIGHT):
            cv2.line(image, (side, ROAD_TOP), (side, ROAD_BOTTOM-1), color('#385E65'), 2)
        offset = int(game.elapsed*190) % 90
        for y in range(ROAD_TOP-90+offset, ROAD_BOTTOM, 90):
            y0, y1 = max(ROAD_TOP, y), min(ROAD_BOTTOM-1, y+38)
            if y1 > y0:
                for x in (330, 590):
                    rounded(image, x-1, y0, 3, y1-y0, color('#3B5065'), 1)
                for x in (54, 863):
                    rounded(image, x, y0, 4, y1-y0, mix(BG, MINT, .6), 2)
        road = image[ROAD_TOP:ROAD_BOTTOM, ROAD_LEFT:ROAD_RIGHT]
        for bike in game.bikes:
            r = bike.rect
            sprite(road, self.motors[bike.style], Rect(r.x-ROAD_LEFT, r.y-ROAD_TOP, r.w, r.h))
        p = game.player
        accent = RED if game.state == 'over' else AMBER if tracking and steering_status != 'live' else MINT if tracking else FAINT
        x0, y0, x1, y1 = map(round, (p.x, p.y, p.x+p.w, p.y+p.h))
        cv2.rectangle(image, (x0, y0), (x1, y1), mix(BG, accent, .38), 1)
        for x, dx in ((x0, 1), (x1, -1)):
            for y, dy in ((y0, 1), (y1, -1)):
                cv2.line(image, (x, y), (x+dx*13, y), accent, 2, cv2.LINE_AA)
                cv2.line(image, (x, y), (x, y+dy*13), accent, 2, cv2.LINE_AA)
        sprite(image, self.cars[car], p)
        text(image, 'YOU', x0, y0-20, 10, accent, True)
        self.monitor(image, game, obs, tracking, closed, demo, steering_status, eyes_valid)
        self.action_card(image, game, tracking, closed, eyes_valid)
        self.mini_rankings(image, ui)
        x = 44
        for key, label in (('P', 'Pause'), ('G', 'Garage'), ('B', 'Board'), ('R', 'New driver'), ('M', 'Sound'), ('F', 'Fullscreen'), ('ESC', 'Quit')):
            x = shortcut(image, key, label, x, 768, 11)
        sound = 'Sound off' if 'MUTED' in audio_status else 'Audio unavailable' if 'UNAVAILABLE' in audio_status else 'Sound on'
        text(image, sound, 1254, 773, 11, MUTED, align='right')
        if demo:
            pill(image, 'DEMO  ·  MOUSE / A,D   ·   SPACE EYES   ·   L TRACKING', 190, 721, MUTED, 10)
        if game.pending is not None and game.state == 'running' and tracking and eyes_valid and closed:
            card(image, 202, 170, 516, 87, mix(SURFACE, AMBER, .07), 18, mix(BORDER, AMBER, .5))
            icon(image, 'eye', 236, 203, 27, AMBER)
            text(image, 'OPEN YOUR EYES', 266, 188, 25, AMBER, True)
            text(image, f'Motorcycle arrives in {game.pending:.1f} seconds. Get ready to dodge.', 226, 229, 13, WHITE)

    def monitor(self, image, game, obs, tracking, closed, demo, steering_status, eyes_valid):
        card(image, 914, 20, 342, 332)
        text(image, 'DRIVER VIEW', 934, 38, 11, MUTED, True)
        tag = 'DEMO' if demo else 'LIVE' if tracking else 'CONNECTING'
        tag_color = MINT if tracking else AMBER
        tw = measure(tag, 10, True)+22
        pill(image, tag, 1236-tw, 31, tag_color, 10)
        rounded(image, 930, 65, 310, 181, BG, 11)
        if obs.frame is not None:
            frame = cv2.flip(obs.frame, 1).copy()
            fh, fw = frame.shape[:2]
            if obs.box is not None:
                bx0, by0, bx1, by1 = obs.box
                cv2.rectangle(frame, (round(fw-bx1), round(by0)), (round(fw-bx0), round(by1)), MINT if tracking else AMBER, 2)
            scale = min(306/fw, 177/fh)
            preview = cv2.resize(frame, (max(1, round(fw*scale)), max(1, round(fh*scale))))
            ph, pw = preview.shape[:2]
            px, py = 932+(306-pw)//2, 67+(177-ph)//2
            photo(image, preview, px, py)
        else:
            icon(image, 'head', 1085, 128, 58, mix(FAINT, MINT, .35))
            centered(image, 'Move left. Move right.', 182, 14, MUTED, x=1085)
            centered(image, 'Demo controls are active' if demo else 'Center your face in the camera', 208, 11, FAINT, x=1085)
        label = ('Tracking paused' if not tracking else 'Eyes unavailable' if not eyes_valid else
                 'Eyes closed' if closed else 'Eyes open')
        ink = FAINT if not tracking or not eyes_valid else AMBER if closed else MINT
        icon(image, 'closed' if closed else 'eye', 946, 271, 20, ink)
        text(image, label, 968, 261, 16, WHITE, True)
        text(image, steering_status.capitalize() if tracking and steering_status != 'live' else 'Ready to steer' if tracking else 'Waiting for your face',
             968, 284, 11, MUTED)
        bar(image, 934, 310, 302, game.closed_seconds/ASLEEP_SECONDS, ink, 4)
        text(image, f'{min(game.closed_seconds, ASLEEP_SECONDS):.1f}s / 3s eye closure', 934, 323, 10, MUTED)

    @staticmethod
    def action_card(image, game, tracking, closed, eyes_valid):
        pending = game.pending is not None
        warning = pending and closed and eyes_valid and tracking
        ink = AMBER if pending else MINT
        card(image, 914, 370, 342, 157, mix(SURFACE, ink, .035), stroke=mix(BORDER, ink, .22))
        text(image, 'NEXT ACTION', 934, 389, 10, MUTED, True)
        title = 'OPEN YOUR EYES' if warning else 'GET READY' if pending else 'CLOSE EYES'
        if not pending and tracking and not eyes_valid:
            title = 'FACE CAMERA'
        text(image, title, 934, 414, 23 if pending else 28, ink, True)
        if pending:
            text(image, f'{max(0, game.pending):.1f}s', 1234, 415, 23, WHITE, True, align='right')
        text(image, 'Move sideways when the motorcycle arrives.' if pending else
             'Keep your eyes visible to continue.' if not eyes_valid else 'Hold for 3 seconds. Open at the alarm.',
             934, 455, 12, MUTED)
        pill(image, 'SPAWN ARMED' if pending else f'REACTION WINDOW  {game.spawn_delay:.1f}s', 934, 485, ink, 10)

    @staticmethod
    def mini_rankings(image, ui):
        card(image, 914, 545, 342, 203)
        text(image, 'TOP DRIVERS', 934, 563, 11, MUTED, True)
        shortcut(image, 'B', 'All', 1160, 555, 11)
        text(image, 'Score first, then fastest time', 934, 585, 10, FAINT)
        for i, driver in enumerate(ui.rankings[:5]):
            y = 610+i*25
            active = ui.driver and driver['id'] == ui.driver['id']
            ink = MINT if active else WHITE
            text(image, f'{i+1:02}', 934, y, 11, MINT if i == 0 else FAINT, True)
            text(image, driver['name'], 962, y, 12, ink, width=112)
            text(image, f"{driver['best_score']}/{SCORE_CAP}", 1088, y, 11, MINT, True)
            text(image, format_time(driver['best_seconds']), 1236, y, 11, MUTED, align='right')
        if not ui.rankings:
            icon(image, 'flag', 1085, 641, 29, FAINT)
            centered(image, 'Your next run could lead the board.', 682, 12, MUTED, x=1085)

    def name_screen(self, image, ui, car):
        self.screen_header(image, '01 / 03  ·  DRIVER PROFILE')
        card(image, 44, 128, 604, 606, mix(SURFACE, MINT, .025), 24)
        pill(image, 'TEN DODGES. ONE MISSION.', 76, 159, MINT)
        text(image, 'Your head.', 76, 216, 58, WHITE, True)
        text(image, 'Your wheel.', 76, 280, 58, MINT, True)
        wrap(image, 'Stay alert. Find your gap. Finish the mission faster than anyone else.', 78, 360, 490, 17)
        self.hero_road(image, 76, 429, 540, 235, car)
        icon(image, 'head', 90, 697, 20, MINT)
        text(image, 'Steer with your head', 111, 690, 13, MUTED)
        icon(image, 'flag', 364, 697, 20, MINT)
        text(image, 'Race to 10 / 10', 385, 690, 13, MUTED)

        card(image, 674, 128, 562, 606, radius=24)
        text(image, 'LET’S MEET THE DRIVER', 712, 167, 11, MINT, True)
        text(image, 'Who’s driving?', 712, 204, 36, WHITE, True)
        wrap(image, 'Use your name to save your score and keep improving your best time.', 714, 257, 468, 16)
        text(image, 'DRIVER NAME', 714, 323, 11, MUTED, True)
        text(image, f'{len(ui.name_input)} / 24', 1194, 323, 11, FAINT, align='right')
        rounded(image, 712, 348, 486, 70, BG, 13, MINT if not ui.name_error else RED)
        value = ui.name_input or 'Enter your name'
        text(image, value, 734, 369, 25, WHITE if ui.name_input else FAINT, width=436)
        if ui.name_input:
            cx = 735+measure(fit(ui.name_input, 436, 25), 25)
            cv2.line(image, (cx+3, 367), (cx+3, 396), MINT, 2, cv2.LINE_AA)
        text(image, 'Up to 24 characters. Use the same name when you return.', 714, 434, 12, FAINT)
        rounded(image, 712, 475, 486, 98, BG, 14)
        if ui.name_error:
            icon(image, 'alert', 740, 503, 20, RED)
            wrap(image, ui.name_error, 766, 493, 408, 14, RED, max_lines=3)
        elif ui.name_match:
            self.avatar(image, ui.name_match['name'], 730, 495)
            text(image, f"Welcome back · {ui.name_match['id']}", 783, 495, 14, WHITE, True)
            text(image, format_best(ui.name_match), 783, 523, 13, MINT, width=388)
        else:
            icon(image, 'head', 744, 512, 26, MINT)
            text(image, 'A fresh start', 782, 496, 15, WHITE, True)
            text(image, 'Your driver profile will be created when you continue.', 782, 526, 12, MUTED, width=390)
        button(image, 'Continue to the tutorial', 'ENTER', 712, 604, 486)
        shortcut(image, 'ESC', 'Quit', 712, 681)
        text(image, 'No timer starts until you’re ready.', 1198, 688, 12, MUTED, align='right')

    def tutorial_screen(self, image, ui, demo):
        self.screen_header(image, '02 / 03  ·  HOW TO PLAY')
        text(image, 'How to play.', 64, 126, 38, WHITE, True)
        name = ui.driver['name'] if ui.driver else 'Driver'
        text(image, f'Welcome, {name}. Learn the loop, then make every second count.', 66, 177, 16, MUTED, width=1150)
        steps = [
            ('wheel', '01', 'Steer your car' if demo else 'Your head is the steering wheel',
             'Move the mouse or use A/D or arrow keys. Stay inside the road; touching a side ends the run.' if demo else
             'Face the camera. Move your head left or right to steer. Stay inside the road; touching a side ends the run.'),
            ('closed', '02', 'Close your eyes for 3 seconds',
             'Press Space to close your simulated eyes. Keep them closed for 3 continuous seconds to trigger the alarm.' if demo else
             'Follow CLOSE EYES. Keep them closed for 3 continuous seconds to trigger the alarm. Short blinks do not count.'),
            ('eye', '03', 'Hear the alarm? Open your eyes.',
             'Press Space again when the beep begins. Move sideways to dodge. The horn means the motorcycle has spawned.' if demo else
             'Open your eyes as soon as the beep begins. A motorcycle is coming. Move your head sideways to dodge it.'),
            ('flag', '04', 'Ten dodges. Mission complete.',
             'Each dodge earns a point. Bikes get faster and reaction time gets shorter. Higher scores rank first; faster times break ties.'),
        ]
        for i, (mark, number, title, body) in enumerate(steps):
            x, y = 64+(i % 2)*588, 222+(i//2)*190
            card(image, x, y, 564, 172, radius=18)
            pill(image, f'STEP {number}', x+24, y+20, MINT, 10)
            icon(image, mark, x+518, y+34, 27, mix(FAINT, MINT, .5))
            text(image, title, x+24, y+64, 21, WHITE, True, width=516)
            wrap(image, body, x+24, y+100, 508, 15, line_height=22, max_lines=3)
        rounded(image, 64, 612, 714, 104, mix(SURFACE, MINT, .045), 16, BORDER)
        text(image, 'THE LOOP', 88, 632, 10, MINT, True)
        text(image, 'Close eyes  →  Alarm  →  Open eyes  →  Dodge', 88, 658, 19, WHITE, True)
        text(image, 'Demo: Space toggles eyes. L toggles tracking.' if demo else 'Repeat until 10 / 10. The fastest completion leads.',
             88, 690, 12, MUTED)
        button(image, 'I’m ready', 'ENTER', 842, 634, 374)
        shortcut(image, 'ESC', 'Quit', 842, 700)
        x = 66
        for key, label in (('P', 'Pause'), ('G', 'Garage'), ('B', 'Board'), ('M', 'Sound'), ('F', 'Fullscreen')):
            x = shortcut(image, key, label, x, 753, 11)

    def settings_screen(self, image, game, car):
        self.screen_header(image, 'GARAGE  /  MISSION SETTINGS')
        text(image, 'Make it your drive.', 48, 123, 36, WHITE, True)
        text(image, 'Choose your car. The challenge grows with your score.', 50, 176, 16, MUTED)
        card(image, 48, 218, 566, 474, radius=22)
        text(image, 'THE ROAD GETS HARDER', 74, 243, 11, MINT, True)
        text(image, 'Automatic difficulty', 74, 270, 24, WHITE, True)
        stages = list(DIFFICULTIES.items())
        for i, (name, settings) in enumerate(stages):
            y = 318+i*81
            end = stages[i+1][1].start_score-1 if i+1 < len(stages) else SCORE_CAP-1
            steps = end-settings.start_score
            end_speed = settings.start_speed+steps*settings.speed_step
            end_delay = settings.spawn_delay-steps*settings.delay_step
            active, accent = name == game.difficulty, STAGE_COLORS[name]
            rounded(image, 74, y, 514, 69, mix(SURFACE, accent, .09) if active else BG, 12, mix(BORDER, accent, .6) if active else None)
            cv2.circle(image, (94, y+21), 4, accent, -1, cv2.LINE_AA)
            text(image, name.capitalize(), 110, y+12, 18, accent if active else WHITE, True)
            text(image, f'SCORE {settings.start_score}–{end}', 568, y+17, 10, MUTED, True, align='right')
            text(image, f'{settings.start_speed:g}–{end_speed:g} px/s', 110, y+43, 12, MUTED)
            text(image, f'{settings.spawn_delay:.1f}–{end_delay:.1f}s to react', 308, y+43, 12, MUTED)
        text(image, 'Every point makes the next motorcycle tougher.', 76, 660, 12, MUTED)
        card(image, 638, 218, 594, 474, radius=22)
        text(image, 'YOUR CAR', 664, 243, 11, MINT, True)
        text(image, 'Pick your ride.', 664, 270, 24, WHITE, True)
        for i, asset in enumerate(self.cars):
            x = 664+i*184
            active = i == car
            rounded(image, x, 320, 174, 216, mix(SURFACE, MINT, .08) if active else BG, 16, MINT if active else BORDER)
            sprite(image, asset, Rect(x+34, 348, 106, 139))
            centered(image, ('Graphite', 'Crimson', 'Azure')[i], 507, 16, MINT if active else WHITE, True, x+87)
            if active:
                cv2.circle(image, (x+151, 342), 8, MINT, -1, cv2.LINE_AA)
                cv2.line(image, (x+147, 342), (x+150, 345), BG, 2, cv2.LINE_AA)
                cv2.line(image, (x+150, 345), (x+156, 338), BG, 2, cv2.LINE_AA)
        shortcut(image, '← / →', 'Change car', 664, 566)
        rounded(image, 664, 614, 540, 48, BG, 12)
        text(image, 'Your score and current round stay with you.', 684, 631, 13, MUTED)
        shortcut(image, 'ESC', 'Cancel', 48, 727)
        button(image, 'Apply selection', 'ENTER', 916, 716, 316)

    def rankings_screen(self, image, ui):
        self.screen_header(image, 'SCORE HIGHER. FINISH FASTER.')
        text(image, 'The leaderboard.', 48, 123, 36, WHITE, True)
        text(image, 'Highest score first. Fastest time wins the tie.', 50, 176, 16, MUTED)
        pill(image, '10 / 10 COMPLETIONS LEAD', 1026, 150, MINT, 10)
        card(image, 48, 218, 1184, 470, radius=22)
        for value, x in (('RANK', 76), ('DRIVER', 154), ('DRIVER ID', 478), ('SCORE', 644), ('FINISH / RUN TIME', 808), ('RESULT', 1060)):
            text(image, value, x, 243, 10, MUTED, True)
        cv2.line(image, (72, 271), (1208, 271), BORDER, 1)
        for i, driver in enumerate(ui.rankings[ui.ranking_page*8:ui.ranking_page*8+8]):
            y = 281+i*48
            active = ui.driver and driver['id'] == ui.driver['id']
            if active:
                rounded(image, 64, y-2, 1152, 44, mix(SURFACE, MINT, .07), 10)
            elif i % 2 == 0:
                rounded(image, 64, y-2, 1152, 44, mix(SURFACE, BG, .33), 10)
            text(image, f"{driver['rank']:02}", 78, y+10, 17, MINT if driver['rank'] == 1 else MUTED, True)
            text(image, driver['name'], 154, y+10, 17, MINT if active else WHITE, active, width=294)
            text(image, driver['id'], 478, y+13, 13, MUTED)
            text(image, f"{driver['best_score']:02} / {SCORE_CAP}", 644, y+9, 19, MINT, True)
            text(image, format_time(driver['best_seconds']), 808, y+10, 18, WHITE, True, width=214)
            complete = driver['best_score'] == SCORE_CAP
            pill(image, 'COMPLETE' if complete else 'PARTIAL', 1060, y+5, MINT if complete else MUTED, 10)
        if not ui.rankings:
            icon(image, 'flag', 640, 405, 48, FAINT)
            centered(image, 'Your first run starts the story.', 458, 24, WHITE, True)
            centered(image, 'Play a round to set your score and time.', 499, 16, MUTED)
        pages = max(1, (len(ui.rankings)+7)//8)
        pill(image, f'PAGE {ui.ranking_page+1} / {pages}', 48, 719, MUTED)
        text(image, f'{len(ui.rankings)} drivers', 192, 726, 13, MUTED)
        shortcut(image, '← / →', 'Pages', 806, 720)
        shortcut(image, 'B / ESC', 'Back', 1060, 720)

    def victory_screen(self, image, game, ui, seconds):
        self.brand(image)
        for i in range(72):
            x = round((i*137+18*math.sin(seconds+i)) % WIDTH)
            y = round((i*83+seconds*(36+i % 7*10)) % HEIGHT)
            ink = (MINT, AMBER, BLUE, MUTED)[i % 4]
            angle = i+seconds*2
            dx, dy = round(4*math.cos(angle)), round(4*math.sin(angle))
            cv2.line(image, (x-dx, y-dy), (x+dx, y+dy), ink, 2, cv2.LINE_AA)
        card(image, 198, 112, 884, 616, mix(SURFACE, MINT, .025), 28, mix(BORDER, MINT, .3))
        cv2.circle(image, (640, 192), 49, mix(SURFACE, MINT, .08), -1, cv2.LINE_AA)
        icon(image, 'trophy', 640, 185, 49, MINT)
        centered(image, 'MISSION COMPLETE', 260, 11, MINT, True)
        centered(image, 'That’s a perfect run.', 289, 45, WHITE, True)
        centered(image, ui.driver['name'] if ui.driver else 'Well driven.', 349, 22, MUTED, width=740)
        rounded(image, 294, 398, 692, 115, BG, 18)
        cv2.line(image, (640, 421), (640, 491), BORDER, 1)
        centered(image, 'MOTORCYCLES DODGED', 418, 10, MUTED, True, 467)
        centered(image, f'{game.score} / {SCORE_CAP}', 445, 36, MINT, True, 467)
        centered(image, 'COMPLETION TIME', 418, 10, MUTED, True, 813)
        centered(image, format_time(game.elapsed), 448, 32, WHITE, True, 813, 308)
        for i in range(SCORE_CAP):
            rounded(image, 390+i*51, 540, 40, 5, MINT, 2)
        centered(image, ui.result_message or 'Every dodge counted. Mission accomplished.', 569, 14, MUTED, width=760)
        button(image, 'Next driver', 'R', 338, 616, 278)
        button(image, 'Leaderboard', 'B', 636, 616, 306, primary=False)
        centered(image, 'ESC  Quit     ·     M  Sound', 691, 12, MUTED)

    @staticmethod
    def modal(image, title, subtitle, mark, ink=MINT, tag=None):
        dim(image)
        card(image, 180, 257, 560, 310, SURFACE, 24, mix(BORDER, ink, .25))
        rounded(image, 208, 285, 48, 48, mix(SURFACE, ink, .13), 14)
        icon(image, mark, 232, 309, 26, ink)
        if tag:
            pill(image, tag, 277, 296, ink, 10)
        text(image, title, 208, 355, 31, WHITE, True, width=504)
        wrap(image, subtitle, 210, 407, 496, 16, max_lines=3)

    def ready_overlay(self, image, game, ui, tracking, camera_error):
        name = ui.driver['name'] if ui.driver else 'Driver'
        self.modal(image, 'Ready when you are.', f'{name}, center your face and stay inside the road. Close your eyes for 3 seconds to begin each cycle.',
                   'wheel', tag='03 / 03  ·  READY TO DRIVE')
        if tracking:
            button(image, 'Start driving', 'ENTER', 208, 491, 504)
        elif camera_error:
            button(image, 'Reconnect camera', 'R', 208, 491, 504, ink=AMBER)
        else:
            rounded(image, 208, 491, 504, 50, RAISED, 12)
            centered(image, 'Waiting for your camera…', 508, 16, MUTED, x=460)
        if camera_error:
            self.error_toast(image, 'Camera unavailable', 'Check the camera connection and close other camera apps.', 'R', 'Try again', AMBER)

    def result_overlay(self, image, game, ui):
        reason = {'left road edge': 'You touched the left edge of the road.',
                  'right road edge': 'You touched the right edge of the road.',
                  'motorcycle': 'A motorcycle caught you. Find your gap on the next run.'}.get(game.crash_reason, 'Keep inside the road and dodge incoming traffic.')
        self.modal(image, 'End of the road.', reason, 'alert', RED, 'ROUND ENDED')
        text(image, f'{game.score} / {SCORE_CAP} DODGED', 210, 463, 14, RED, True)
        text(image, format_time(game.elapsed), 710, 461, 19, WHITE, True, align='right')
        button(image, 'Next driver', 'R', 208, 505, 250, ink=RED)
        button(image, 'Leaderboard', 'B', 472, 505, 240, primary=False)
        if ui.result_message:
            text(image, ui.result_message, 460, 590, 12, MUTED, align='center', width=700)

    def pause_overlay(self, image):
        self.modal(image, 'Take a breather.', 'Your drive and reaction countdown are paused. Come back when you’re ready.', 'pause', tag='DRIVE PAUSED')
        button(image, 'Resume driving', 'P', 208, 491, 504)

    def tracking_overlay(self, image, error):
        self.modal(image, 'Your camera needs a moment.' if error else 'Let’s find your face.',
                   'Check the camera connection and close other camera apps, then reconnect to continue.' if error else
                   'Center your face in the camera. Your drive will resume automatically when tracking returns.',
                   'head', AMBER, 'CAMERA UNAVAILABLE' if error else 'TRACKING PAUSED')
        if error:
            button(image, 'Reconnect camera', 'R', 208, 491, 504, ink=AMBER)
            self.error_toast(image, 'Connection details', error, 'R', 'Reconnect', AMBER)
        else:
            rounded(image, 208, 491, 504, 50, RAISED, 12)
            centered(image, 'Waiting for your face…', 508, 16, MUTED, x=460)

    @staticmethod
    def error_toast(image, title, detail, key, action, ink=RED):
        card(image, 224, 608, 832, 132, mix(SURFACE, ink, .055), 18, mix(BORDER, ink, .5))
        icon(image, 'alert', 252, 637, 22, ink)
        text(image, title, 278, 627, 18, WHITE, True)
        wrap(image, detail, 250, 663, 760, 13, MUTED, line_height=20, max_lines=2)
        shortcut(image, key, action, 840, 703, 11)
