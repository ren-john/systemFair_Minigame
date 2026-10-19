"""Render every UI state using synthetic data, without a camera or driver DB."""
import argparse
from copy import deepcopy
from pathlib import Path
from tempfile import gettempdir

import cv2
import numpy as np

from drivers import DriverUI, format_best
from game_core import Game, Motorcycle, Rect
from renderer import Renderer
from tracking import Observation
from ui import BG, WHITE, text


def samples():
    rows = [('Saiken Studio', 10, 45.123), ('Bea Cruz', 10, 45.124),
            ('Alexandra Long Driver', 10, 51.789), ('Cam Reyes', 9, 40.12),
            ('Dee Santos', 9, 42.56), ('Eli Garcia', 8, 37.7),
            ('Fran Lim', 7, 34.2), ('Grace Tan', 6, 28.6),
            ('Henry Lee', 4, 21.9), ('Ira Diaz', 0, 5.123)]
    return [dict(id=f'D{i+1:04}', name=name, best_score=score, best_seconds=seconds,
                 best_difficulty='impossible', rank=i+1)
            for i, (name, score, seconds) in enumerate(rows)]


def synthetic_camera():
    frame = np.full((480, 640, 3), (43, 37, 29), np.uint8)
    cv2.circle(frame, (320, 205), 86, (99, 91, 73), -1, cv2.LINE_AA)
    cv2.ellipse(frame, (320, 438), (154, 128), 0, 180, 360, (99, 91, 73), -1, cv2.LINE_AA)
    return frame


def scenes():
    """Yield representative game data for every screen and important edge state."""
    rankings = samples()
    scenarios = (
        ('01_name', 'name'), ('02_returning_driver', 'name'), ('03_name_error', 'name'),
        ('04_tutorial', 'tutorial'), ('05_demo_tutorial', 'tutorial'), ('06_ready', 'ready'),
        ('07_driving', 'running'), ('08_eyes_closed', 'running'), ('09_alarm', 'running'),
        ('10_get_ready', 'running'), ('11_paused', 'paused'), ('12_crash', 'over'),
        ('13_victory', 'won'), ('14_garage', 'settings'), ('15_leaderboard', 'rankings'),
        ('16_leaderboard_page2', 'rankings'), ('17_empty_leaderboard', 'rankings'),
        ('18_tracking_lost', 'running'), ('19_camera_error', 'running'),
        ('20_save_error', 'won'), ('21_eyes_unavailable', 'running'),
    )
    for label, state in scenarios:
        game = Game()
        game.start()
        game.state, game.score, game.elapsed = state, 7, 44.883
        game.bikes = [Motorcycle(Rect(250, 276, 76, 122), 330, 1),
                      Motorcycle(Rect(690, 161, 76, 122), 330, 2)]
        ui = DriverUI(driver=deepcopy(rankings[0]), rankings=deepcopy(rankings),
                      result_message='NEW PERSONAL BEST!  '+format_best(rankings[0]))
        obs = Observation(ear=.28, frame=synthetic_camera(), box=(235, 120, 405, 300))
        tracking, closed, eyes_valid, demo = True, False, True, False
        if state in ('name', 'tutorial', 'ready'):
            game.score = 0
            game.elapsed = 0
        if label == '01_name':
            ui.driver = None
        if label == '02_returning_driver':
            ui.name_input, ui.name_match = 'Saiken Studio', ui.driver
        if label == '03_name_error':
            ui.name_input, ui.name_error = 'Bad@name', 'Use letters, numbers, spaces, dots, apostrophes, or hyphens.'
        if label == '05_demo_tutorial':
            demo = True
        if label == '08_eyes_closed':
            closed, game.closed_seconds = True, 1.8
        if label in ('09_alarm', '10_get_ready'):
            game.pending = 1.1
            closed = label == '09_alarm'
            game.closed_seconds = 3 if closed else 0
        if state == 'over':
            game.crash_reason = 'motorcycle'
        if state == 'won':
            game.score, game.elapsed, game.bikes = 10, 45.123, []
        if label == '16_leaderboard_page2':
            ui.ranking_page = 1
        if label == '17_empty_leaderboard':
            ui.rankings = []
        if label in ('18_tracking_lost', '19_camera_error'):
            tracking = False
            obs = Observation(error='RuntimeError: Cannot open camera. Check camera permissions.'
                              if label == '19_camera_error' else '')
        if label == '20_save_error':
            ui.save_error = 'Could not save driver records. Check that the game folder is writable, then retry.'
        if label == '21_eyes_unavailable':
            eyes_valid = False
        yield label, game, obs, tracking, closed, eyes_valid, demo, ui


def render_previews(output):
    output.mkdir(parents=True, exist_ok=True)
    renderer = Renderer(Path(__file__).resolve().parent / 'assets')
    files = []
    for label, game, obs, tracking, closed, eyes_valid, demo, ui in scenes():
        frame = renderer.draw(game, obs, tracking, closed, 0, 'AUDIO / RANDOM HORN', .22,
                              demo=demo, eyes_valid=eyes_valid, ui=ui, selected_car=1,
                              celebration_time=1.5)
        path = output / f'{label}.png'
        if not cv2.imwrite(str(path), frame):
            raise RuntimeError(f'Cannot write preview: {path}')
        files.append((label, frame))
    columns, tw, th = 3, 480, 330
    sheet = np.full((((len(files)+columns-1)//columns)*th, columns*tw, 3), BG, np.uint8)
    for i, (label, frame) in enumerate(files):
        x, y = (i % columns)*tw, (i//columns)*th
        text(sheet, label.replace('_', ' '), x+14, y+8, 12, WHITE)
        sheet[y+30:y+330, x:x+480] = cv2.resize(frame, (480, 300), interpolation=cv2.INTER_AREA)
    if not cv2.imwrite(str(output / 'overview.png'), sheet):
        raise RuntimeError('Cannot write the screen overview.')
    return [label for label, _ in files]


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=Path(gettempdir()) / 'nightshift-ui')
    args = parser.parse_args()
    names = render_previews(args.output)
    print(f'Rendered {len(names)} screens and overview.png in {args.output}')
