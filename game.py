"""Night Shift: head-controlled motorcycle evasion for Systems Fair."""
import argparse
import math
import os
from pathlib import Path
import random
import sys
import time

os.environ.setdefault('TF_CPP_MIN_LOG_LEVEL', '2')
import cv2
import numpy as np

from audio import Horns
from game_core import (Game, Rect, Motorcycle, PLAYER_Y, ROAD_LEFT, ROAD_RIGHT,
                       DIFFICULTIES, ASLEEP_SECONDS, player_from_face)
from renderer import Renderer
from tracking import Observation, Tracker
from face_geometry import EAR_THRESHOLD
from steering import HeadSteering, FRESH_SECONDS
from drivers import DriverStore, DriverSession

ROOT = Path(__file__).resolve().parent
WINDOW = 'Night Shift | Systems Fair'


def arguments():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=int, default=0, help='Laptop webcam index (default: 0)')
    parser.add_argument('--assets', type=Path, default=ROOT / 'assets')
    parser.add_argument('--ear-threshold', type=float, default=EAR_THRESHOLD)
    parser.add_argument('--confidence', type=float, default=.5)
    parser.add_argument('--eye-mode', choices=['auto', 'left', 'right'], default='auto')
    parser.add_argument('--eye-width-ratio', type=float, default=.60)
    parser.add_argument('--demo', action='store_true', help='Mouse/A,D steering, space toggles eyes, L toggles tracking loss')
    parser.add_argument('--mute', action='store_true')
    parser.add_argument('--fullscreen', action='store_true')
    parser.add_argument('--difficulty', choices=list(DIFFICULTIES), default='medium')
    parser.add_argument('--database', type=Path, help='Override the local driver-records JSON path')
    parser.add_argument('--smoke-test', action='store_true', help='Render a deterministic preview and check assets without opening a camera/window')
    for_args = parser.parse_args()
    if not math.isfinite(for_args.ear_threshold) or for_args.ear_threshold <= 0:
        parser.error('--ear-threshold must be a positive finite number')
    if not 0 < for_args.confidence <= 1 or not 0 < for_args.eye_width_ratio <= 1:
        parser.error('--confidence and --eye-width-ratio must be in (0, 1]')
    if for_args.source < 0:
        parser.error('--source must be a nonnegative camera index')
    return for_args


def smoke_test(renderer):
    game = Game(random.Random(12))
    game.start()
    game.update(0, game.player, True)
    assert game.pending is None
    game.update(ASLEEP_SECONDS, game.player, True)
    assert game.asleep
    assert 3 <= game.pending <= 5
    delay = game.pending
    assert game.update(delay, game.player, False) == 1
    assert game.pending is None
    game.elapsed = 27
    game.score = 4
    game.bikes = [Motorcycle(Rect(390, 320, 76, 122), 220, 1),
                  Motorcycle(Rect(650, 190, 76, 122), 220, 2)]
    game.pending = 3.7
    preview = renderer.draw(game, Observation(ear=.28), True, False, 1,
                            'AUDIO  /  RANDOM HORN', EAR_THRESHOLD, demo=True)
    output = ROOT / 'preview.png'
    if not cv2.imwrite(str(output), preview):
        raise RuntimeError(f'Could not save preview: {output}')
    print(f'Smoke test passed. All six PNGs loaded; timer/spawn checked. Preview: {output}')


def main():
    args = arguments()
    renderer = Renderer(args.assets)
    if args.smoke_test:
        smoke_test(renderer)
        return
    database = args.database or ROOT / 'data' / ('demo_drivers.json' if args.demo else 'drivers.json')
    store = DriverStore(database)
    horns = Horns(sorted(args.assets.glob('*.mp3')))
    horns.muted = args.mute
    reported_audio_error = ''
    tracker = None
    game = Game(difficulty=args.difficulty)
    session = DriverSession(game, store)
    settings_return_state = 'ready'
    rankings_return_state = 'ready'
    selected_difficulty = game.difficulty
    car = 0
    selected_car = car
    fullscreen = args.fullscreen
    demo_closed = False
    demo_lost = False
    steering = HeadSteering()
    mouse_x = [460.0]
    try:
        if not args.demo:
            tracker = Tracker(args.source, args.confidence, args.eye_mode, args.eye_width_ratio)
        cv2.namedWindow(WINDOW, cv2.WINDOW_NORMAL | cv2.WINDOW_KEEPRATIO)
        cv2.resizeWindow(WINDOW, 1280, 800)
        if fullscreen:
            cv2.setWindowProperty(WINDOW, cv2.WND_PROP_FULLSCREEN, cv2.WINDOW_FULLSCREEN)
        cv2.setMouseCallback(WINDOW, lambda event, x, y, flags, param: mouse_x.__setitem__(0, float(x))
                             if event == cv2.EVENT_MOUSEMOVE else None)
        previous = time.monotonic()
        was_tracking = False
        last_observation_time = None
        while True:
            now = time.monotonic()
            dt = min(.1, now - previous)
            previous = now
            obs = tracker.snapshot() if tracker else Observation(ear=.15 if demo_closed else .30, timestamp=now)
            face_visible = ((not demo_lost) if args.demo else
                            (obs.box is not None and obs.frame is not None
                             and 0 <= now-obs.timestamp <= FRESH_SECONDS and not obs.error))
            eyes_valid = face_visible and math.isfinite(obs.ear)
            closed = obs.ear < args.ear_threshold if eyes_valid else False
            measurement = None
            if args.demo and face_visible:
                center = max(ROAD_LEFT+80, min(ROAD_RIGHT-80, mouse_x[0]))
                measurement = Rect(center-80, PLAYER_Y-75, 160, 150)
            elif face_visible:
                h, w = obs.frame.shape[:2]
                measurement = player_from_face(obs.box, (w, h))
            motion = steering.update(now, dt, measurement, obs.timestamp if face_visible else None)
            tracking = motion.active and not obs.error
            player = motion.player
            if tracking and game.state == 'ready':
                game.player = player
            eye_dt = (max(0, obs.timestamp - last_observation_time)
                      if eyes_valid and last_observation_time is not None else 0)
            if eye_dt > FRESH_SECONDS:
                game.clear_sleep()
                eye_dt = 0
            last_observation_time = obs.timestamp if eyes_valid else None
            if game.update(dt if was_tracking else 0, player, closed, tracking,
                           eye_dt=eye_dt, eyes_valid=eyes_valid):
                horns.play()
            if game.state == 'over' and session.run_open and not session.ui.save_error:
                session.finish_run()
            was_tracking = tracking
            if game.state == 'over' or not tracking:
                horns.stop()
            audio_status = 'AUDIO  /  MUTED' if horns.muted else 'AUDIO  /  RANDOM HORN'
            if horns.error:
                audio_status = 'AUDIO UNAVAILABLE / SEE CONSOLE'
                if horns.error != reported_audio_error:
                    print(f'Audio diagnostic: {horns.error}', file=sys.stderr)
                    reported_audio_error = horns.error
            image = renderer.draw(game, obs, tracking, closed, car, audio_status,
                                  args.ear_threshold, args.demo, selected_difficulty,
                                  steering_status='coasting' if motion.predicted else 'recentering' if motion.recovering else 'live',
                                  eyes_valid=eyes_valid, ui=session.ui, selected_car=selected_car)
            cv2.imshow(WINDOW, image)
            key = cv2.waitKeyEx(16)
            if cv2.getWindowProperty(WINDOW, cv2.WND_PROP_VISIBLE) < 1:
                break
            # Text entry owns the keyboard: R, Q, G, etc. are name characters.
            if game.state == 'name':
                if key == 27:
                    break
                if key in (10, 13):
                    session.submit_name()
                elif key >= 0:
                    session.type_name(key)
                continue
            if key == ord('q'):
                if session.finish_run():
                    break
                if game.state == 'running':
                    game.state = 'paused'
                continue
            if game.state == 'settings':
                if key in (ord('1'), ord('2'), ord('3'), ord('4')):
                    selected_difficulty = list(DIFFICULTIES)[key-ord('1')]
                elif key in (2424832, 2555904):
                    selected_car = (selected_car + (-1 if key == 2424832 else 1)) % 3
                elif key in (10, 13):
                    changing_difficulty = selected_difficulty != game.difficulty
                    if changing_difficulty and not session.finish_run():
                        continue
                    game.state = settings_return_state
                    car = selected_car
                    game.set_difficulty(selected_difficulty)
                    if changing_difficulty:
                        session.ask_name()
                elif key in (27, ord('g')):
                    game.state = settings_return_state
                continue
            if game.state == 'rankings':
                if key in (27, ord('b')):
                    game.state = rankings_return_state
                elif key in (2424832, 2490368):
                    session.ui.ranking_page = max(0, session.ui.ranking_page-1)
                elif key in (2555904, 2621440):
                    session.ui.ranking_page = min(max(0, (len(session.ui.rankings)-1)//8), session.ui.ranking_page+1)
                continue
            if key in (10, 13) and session.ui.save_error:
                session.finish_run()
                continue
            if key == 27:
                if session.finish_run():
                    break
                if game.state == 'running':
                    game.state = 'paused'
                continue
            if key == ord('g'):
                settings_return_state = game.state
                selected_difficulty = game.difficulty
                selected_car = car
                game.state = 'settings'
                game.clear_sleep()
                horns.stop()
                continue
            if key == ord('b'):
                rankings_return_state = game.state
                game.state = 'rankings'
                game.clear_sleep()
                session.ui.ranking_page = 0
                horns.stop()
                continue
            if key in (10, 13) and game.state == 'ready' and face_visible:
                session.start()
            elif key == ord('r'):
                horns.stop()
                if not session.ask_name():
                    continue
                if tracker and obs.error:
                    tracker.close()
                    tracker = Tracker(args.source, args.confidence, args.eye_mode, args.eye_width_ratio)
                    steering = HeadSteering()
            elif key == ord('p'):
                if game.state == 'running':
                    game.state = 'paused'
                    game.clear_sleep()
                    horns.stop()
                elif game.state == 'paused':
                    game.state = 'running'
            elif key == ord('m'):
                horns.muted = not horns.muted
                if horns.muted:
                    horns.stop()
            elif key == ord('f'):
                fullscreen = not fullscreen
                cv2.setWindowProperty(WINDOW, cv2.WND_PROP_FULLSCREEN,
                                      cv2.WINDOW_FULLSCREEN if fullscreen else cv2.WINDOW_NORMAL)
            elif args.demo and key == 32:
                demo_closed = not demo_closed
            elif args.demo and key == ord('l'):
                demo_lost = not demo_lost
            elif args.demo and key in (ord('a'), ord('d'), 2424832, 2555904):
                mouse_x[0] = max(ROAD_LEFT+80, min(ROAD_RIGHT-80, mouse_x[0] + (-35 if key in (ord('a'), 2424832) else 35)))
    finally:
        if not session.finish_run():
            print(session.ui.save_error, file=sys.stderr)
        if tracker:
            tracker.close()
        horns.close()
        cv2.destroyAllWindows()
        if horns.error:
            print(f'Audio diagnostic: {horns.error}', file=sys.stderr)


if __name__ == '__main__':
    try:
        main()
    except (RuntimeError, FileNotFoundError, cv2.error) as exc:
        print(f'Cannot start Night Shift: {exc}', file=sys.stderr)
        sys.exit(1)
