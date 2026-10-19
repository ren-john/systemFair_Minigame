"""Run with: python -m unittest -v test_game"""
import random
import unittest

from game_core import Game, Motorcycle, Rect, PLAYER_Y, ROAD_LEFT, ROAD_RIGHT, ROAD_BOTTOM, SCORE_CAP, player_from_face

PROGRESSION = (
    ('easy', 180), ('easy', 192), ('easy', 204),
    ('medium', 240), ('medium', 262), ('medium', 284),
    ('hard', 330), ('hard', 365), ('impossible', 480), ('impossible', 535),
)
REACTION_DELAYS = (2.5, 2.4, 2.3, 2., 1.8, 1.6, 1.3, 1.1, .9, .7)


class GameTests(unittest.TestCase):
    def setUp(self):
        self.game = Game(random.Random(17))
        self.game.start()

    def fall_asleep(self):
        self.game.update(0, self.game.player, True)
        self.game.update(3, self.game.player, True)

    def test_three_continuous_seconds_required_before_arming(self):
        self.game.update(.1, self.game.player, True)
        self.assertEqual(self.game.closed_seconds, 0)
        self.game.update(2.999, self.game.player, True)
        self.assertFalse(self.game.asleep)
        self.assertIsNone(self.game.pending)
        self.game.update(.001, self.game.player, True)
        self.assertTrue(self.game.asleep)
        self.assertEqual(self.game.pending, 2.5)

    def test_warning_triggers_once_when_armed_and_reopening_does_not_repeat_it(self):
        self.game.update(0, self.game.player, True)
        self.game.update(2.999, self.game.player, True)
        self.assertFalse(self.game.warning_triggered)
        self.game.update(.001, self.game.player, True)
        self.assertTrue(self.game.warning_triggered)
        delay = self.game.pending
        for closed in (True, False, True, False):
            self.game.update(.01, self.game.player, closed)
            self.assertFalse(self.game.warning_triggered)
        self.assertAlmostEqual(self.game.pending, delay-.04)

    def test_continuously_closed_eyes_warn_once_for_each_new_countdown(self):
        self.fall_asleep()
        self.assertTrue(self.game.warning_triggered)
        self.assertEqual(self.game.update(self.game.pending, self.game.player, True), 1)
        self.assertTrue(self.game.warning_triggered)
        self.game.update(0, self.game.player, True)
        self.assertFalse(self.game.warning_triggered)

    def test_warning_does_not_repeat_after_tracking_loss_pause_or_restart(self):
        self.fall_asleep()
        for state, tracking in (('running', False), ('paused', True), ('settings', True)):
            self.game.state = state
            delay = self.game.pending
            self.game.update(10, self.game.player, True, tracking=tracking)
            self.assertFalse(self.game.warning_triggered)
            self.assertEqual(self.game.pending, delay)
            self.game.state = 'running'
            self.game.update(0, self.game.player, True)
            self.assertFalse(self.game.warning_triggered)
        self.game.start()
        self.assertFalse(self.game.warning_triggered)
        self.assertIsNone(self.game.pending)

    def test_reopening_after_asleep_does_not_cancel_spawn(self):
        self.fall_asleep()
        delay = self.game.pending
        self.assertEqual(delay, 2.5)
        self.assertEqual(self.game.update(delay-.001, self.game.player, False), 0)
        self.assertEqual(self.game.update(.002, self.game.player, False), 1)
        self.assertEqual(self.game.spawn_count, 1)
        self.assertIsNone(self.game.pending)
        self.assertFalse(self.game.asleep)
        self.assertEqual(self.game.closed_seconds, 0)

    def test_reaction_window_shortens_at_every_score_and_spawn_waits_for_expiry(self):
        previous_delay = float('inf')
        for score, delay in enumerate(REACTION_DELAYS):
            with self.subTest(score=score):
                game = Game(random.Random(17))
                game.start()
                game.score = score
                self.assertEqual(game.spawn_delay, delay)
                self.assertLess(delay, previous_delay)
                previous_delay = delay
                game.update(0, game.player, True)
                game.update(2.999, game.player, True)
                self.assertFalse(game.warning_triggered)
                self.assertIsNone(game.pending)
                game.update(.001, game.player, True)
                self.assertTrue(game.warning_triggered)
                self.assertEqual(game.pending, delay)
                self.assertEqual(game.update(delay-.001, game.player, False), 0)
                self.assertFalse(game.warning_triggered)
                self.assertEqual(game.update(.002, game.player, False), 1)
                self.assertEqual(game.spawn_count, 1)
                self.assertIsNone(game.pending)
                self.assertAlmostEqual(game.elapsed, 3+delay+.001)

    def test_armed_countdown_keeps_its_duration_when_score_crosses_stage_boundary(self):
        for score in (2, 5, 7):
            with self.subTest(score=score):
                self.game.start()
                self.game.score = score
                self.fall_asleep()
                remaining = self.game.pending
                self.game.bikes = [Motorcycle(Rect(80, ROAD_BOTTOM+1, 76, 122), 0, 0)]
                self.game.update(0, self.game.player, False)
                self.assertEqual(self.game.score, score+1)
                self.assertEqual(self.game.spawn_delay, REACTION_DELAYS[score+1])
                self.assertEqual(self.game.pending, remaining)
                self.assertFalse(self.game.warning_triggered)
                self.assertEqual(self.game.update(remaining-.001, self.game.player, False), 0)
                self.assertEqual(self.game.update(.002, self.game.player, False), 1)

    def test_short_countdown_freezes_during_interruptions_at_every_stage(self):
        for score in (0, 3, 6, 8, 9):
            with self.subTest(score=score):
                self.game.start()
                self.game.score = score
                self.fall_asleep()
                remaining = self.game.pending
                for state, tracking in (('running', False), ('paused', True), ('settings', True)):
                    self.game.state = state
                    self.game.update(60, self.game.player, False, tracking=tracking)
                    self.assertEqual(self.game.pending, remaining)
                    self.assertFalse(self.game.warning_triggered)
                self.game.state = 'running'
                self.assertEqual(self.game.update(remaining-.001, self.game.player, False), 0)
                self.assertEqual(self.game.update(.002, self.game.player, False), 1)

    def test_separate_short_closures_do_not_accumulate(self):
        for _ in range(5):
            self.game.update(0, self.game.player, True)
            self.game.update(2.9, self.game.player, True)
            self.game.update(.01, self.game.player, False)
        self.assertFalse(self.game.asleep)
        self.assertIsNone(self.game.pending)

    def test_cached_camera_frames_cannot_qualify_sleep(self):
        self.game.update(0, self.game.player, True, eye_dt=0)
        for _ in range(100):
            self.game.update(.1, self.game.player, True, eye_dt=0)
        self.assertEqual(self.game.closed_seconds, 0)
        self.assertIsNone(self.game.pending)
        self.game.update(.1, self.game.player, True, eye_dt=3)
        self.assertTrue(self.game.asleep)

    def test_many_blinks_cannot_stack_or_reset_pending_timer(self):
        self.fall_asleep()
        delay = self.game.pending
        for _ in range(10):
            self.game.update(.05, self.game.player, False)
            self.game.update(.05, self.game.player, True)
        self.assertAlmostEqual(self.game.pending, delay-1)
        self.assertEqual(self.game.spawn_count, 0)

    def test_continuous_closure_repeats_with_current_score_delay(self):
        self.fall_asleep()
        self.assertEqual(self.game.update(self.game.pending, self.game.player, True), 1)
        self.assertEqual(self.game.pending, 2.5)

    def test_open_eyes_do_not_spawn(self):
        self.game.update(60, self.game.player, False)
        self.assertEqual(self.game.spawn_count, 0)
        self.assertIsNone(self.game.pending)

    def test_tracking_loss_and_pause_freeze_game(self):
        self.fall_asleep()
        delay = self.game.pending
        elapsed = self.game.elapsed
        self.game.update(60, self.game.player, False, tracking=False)
        self.assertEqual(self.game.pending, delay)
        self.assertEqual(self.game.elapsed, elapsed)
        self.assertFalse(self.game.asleep)
        self.game.state = 'paused'
        self.game.update(60, self.game.player, False)
        self.assertEqual(self.game.pending, delay)

    def test_lost_tracking_or_pause_requires_new_continuous_closure(self):
        for interruption in ('lost', 'paused', 'settings'):
            with self.subTest(interruption=interruption):
                self.game.start()
                self.game.update(0, self.game.player, True)
                self.game.update(2.9, self.game.player, True)
                if interruption != 'lost':
                    self.game.state = interruption
                self.game.update(10, self.game.player, True, tracking=interruption != 'lost')
                self.game.state = 'running'
                self.game.update(0, self.game.player, True)
                self.game.update(.2, self.game.player, True)
                self.assertFalse(self.game.asleep)
                self.assertIsNone(self.game.pending)

    def test_swept_collision_does_not_tunnel_through_face(self):
        self.game.bikes = [Motorcycle(Rect(self.game.player.x+10, 200, 76, 122), 900, 0)]
        self.game.update(1, self.game.player, False)
        self.assertEqual(self.game.state, 'over')
        self.assertEqual(self.game.score, 0)
        self.assertEqual(self.game.crash_reason, 'motorcycle')

    def test_either_road_edge_crashes_even_when_clamped_or_past_boundary(self):
        for x, side in ((ROAD_LEFT, 'left'), (ROAD_LEFT-50, 'left'),
                        (ROAD_RIGHT-160, 'right'), (ROAD_RIGHT-110, 'right')):
            with self.subTest(x=x):
                self.game.start()
                self.game.pending = .01
                player = Rect(x, PLAYER_Y-75, 160, 150)
                self.assertEqual(self.game.update(.05, player, False), 0)
                self.assertEqual(self.game.state, 'over')
                self.assertEqual(self.game.crash_reason, f'{side} road edge')
                self.assertEqual(self.game.player, player)
                self.assertIsNone(self.game.pending)
                self.assertEqual(self.game.spawn_count, 0)
                elapsed = self.game.elapsed
                self.game.update(2, self.game.player, False)
                self.assertEqual(self.game.elapsed, elapsed)

    def test_near_edge_inside_road_does_not_crash(self):
        for x in (ROAD_LEFT+1, ROAD_RIGHT-161):
            self.game.update(.05, Rect(x, PLAYER_Y-75, 160, 150), False)
            self.assertEqual(self.game.state, 'running')
            self.assertEqual(self.game.crash_reason, '')

    def test_restart_clears_crash_and_paused_motion_does_not_crash(self):
        edge = Rect(ROAD_LEFT, PLAYER_Y-75, 160, 150)
        self.game.state = 'paused'
        self.game.update(.1, edge, False)
        self.assertEqual(self.game.state, 'paused')
        self.game.state = 'running'
        self.game.update(.1, edge, False)
        self.assertEqual(self.game.state, 'over')
        self.game.start()
        self.assertEqual(self.game.crash_reason, '')
        self.game.update(.1, self.game.player, False)
        self.assertEqual(self.game.state, 'running')

    def test_dodge_scores_only_once(self):
        self.game.bikes = [Motorcycle(Rect(80, 700, 76, 122), 220, 0)]
        self.game.update(1, self.game.player, False)
        self.game.update(1, self.game.player, False)
        self.assertEqual(self.game.score, 1)
        self.assertEqual(self.game.state, 'running')

    def test_tenth_dodge_wins_cancels_spawns_and_freezes_round(self):
        self.game.score = SCORE_CAP-1
        self.fall_asleep()
        self.game.pending = .01
        self.game.bikes = [Motorcycle(Rect(80, 750, 76, 122), 220, 0)]
        self.assertEqual(self.game.update(.1, self.game.player, True), 0)
        self.assertEqual(self.game.state, 'won')
        self.assertEqual(self.game.score, SCORE_CAP)
        self.assertIsNone(self.game.pending)
        self.assertEqual(self.game.bikes, [])
        self.assertFalse(self.game.asleep)
        self.assertFalse(self.game.warning_triggered)
        elapsed = self.game.elapsed
        player = self.game.player
        for tracking in (True, False):
            self.game.update(60, Rect(ROAD_LEFT, 100, 160, 150), True, tracking=tracking)
            self.assertEqual(self.game.state, 'won')
            self.assertEqual(self.game.elapsed, elapsed)
            self.assertEqual(self.game.player, player)
            self.assertEqual(self.game.score, SCORE_CAP)
        self.game.start()
        self.assertEqual(self.game.state, 'running')
        self.assertEqual(self.game.score, 0)
        self.assertEqual(self.game.elapsed, 0)

    def test_multiple_dodges_in_one_update_cannot_exceed_cap(self):
        self.game.score = SCORE_CAP-1
        self.game.bikes = [Motorcycle(Rect(80, 750, 76, 122), 220, style) for style in range(3)]
        self.game.update(.1, self.game.player, False)
        self.assertEqual(self.game.score, SCORE_CAP)
        self.assertEqual(self.game.state, 'won')

    def test_collision_takes_priority_over_tenth_dodge_regardless_of_bike_order(self):
        for reverse in (False, True):
            self.game.start()
            self.game.score = SCORE_CAP-1
            bikes = [Motorcycle(Rect(80, 750, 76, 122), 220, 0),
                     Motorcycle(Rect(self.game.player.x, self.game.player.y, 76, 122), 220, 1)]
            self.game.bikes = bikes[::-1] if reverse else bikes
            self.game.update(.1, self.game.player, False)
            self.assertEqual(self.game.state, 'over')
            self.assertEqual(self.game.score, SCORE_CAP-1)

    def test_face_moves_only_horizontally_and_mirrors(self):
        a = player_from_face((100, 100, 220, 220), (640, 480))
        b = player_from_face((100, 250, 220, 370), (640, 480))
        c = player_from_face((300, 100, 420, 220), (640, 480))
        self.assertEqual(a, b)
        self.assertEqual(a.y+a.h/2, PLAYER_Y)
        self.assertLess(c.x, a.x)
        self.assertAlmostEqual(a.w, 120/640*780)
        self.assertAlmostEqual(a.h, 120/480*618)

    def test_restart_clears_pending_and_hazards(self):
        self.fall_asleep()
        self.game.update(self.game.pending, self.game.player, True)
        self.game.start()
        self.assertIsNone(self.game.pending)
        self.assertEqual(self.game.bikes, [])
        self.assertFalse(self.game.previous_closed)
        self.assertEqual(self.game.closed_seconds, 0)

    def test_spawns_at_the_same_score_keep_the_same_speed(self):
        for score, (stage, speed) in enumerate(PROGRESSION):
            with self.subTest(score=score):
                game = Game(random.Random(17))
                game.start()
                game.score = score
                for _ in range(5):
                    game.pending = 0
                    self.assertEqual(game.update(0, game.player, False), 1)
                    self.assertEqual(game.score, score)
                self.assertEqual(game.spawn_count, 5)
                self.assertEqual(game.difficulty, stage)
                self.assertTrue(all(bike.speed == speed for bike in game.bikes))

    def test_full_round_automatically_progresses_from_easy_to_impossible(self):
        game = self.game
        previous_speed = 0
        for score, (stage, speed) in enumerate(PROGRESSION):
            with self.subTest(score=score):
                self.assertEqual(game.difficulty, stage)
                game.pending = 0
                self.assertEqual(game.update(0, game.player, False), 1)
                bike = game.bikes[-1]
                self.assertEqual(bike.speed, speed)
                self.assertGreater(bike.speed, previous_speed)
                previous_speed = bike.speed
                bike.rect.x, bike.rect.y = 80, ROAD_BOTTOM+1
                game.update(0, game.player, False)
                self.assertEqual(game.score, score+1)
                self.assertEqual(game.state, 'won' if score == SCORE_CAP-1 else 'running')
        self.assertEqual(game.difficulty, 'impossible')

    def test_motorcycles_in_flight_keep_their_speed_when_a_point_is_earned(self):
        for score, (_stage, speed) in enumerate(PROGRESSION[:-1]):
            with self.subTest(score=score):
                game = Game(random.Random(17))
                game.start()
                game.score = score
                game.pending = 0
                game.update(0, game.player, False)
                existing = game.bikes[0]
                game.bikes.append(Motorcycle(Rect(80, ROAD_BOTTOM+1, 76, 122), speed, 0))
                game.update(0, game.player, False)
                self.assertEqual(game.score, score+1)
                self.assertEqual(existing.speed, speed)
                game.pending = 0
                game.update(0, game.player, False)
                self.assertEqual(existing.speed, speed)
                self.assertEqual(game.bikes[-1].speed, PROGRESSION[score+1][1])

    def test_restart_resets_automatic_difficulty_and_speed(self):
        self.fall_asleep()
        self.game.score = 9
        self.assertEqual(self.game.difficulty, 'impossible')
        self.assertEqual(self.game.spawn_delay, .7)
        self.game.start()
        self.assertEqual(self.game.state, 'running')
        self.assertEqual(self.game.score, 0)
        self.assertIsNone(self.game.pending)
        self.assertEqual(self.game.spawn_count, 0)
        self.assertEqual(self.game.difficulty, 'easy')
        self.assertEqual(self.game.next_speed, 180)
        self.assertEqual(self.game.spawn_delay, 2.5)


class DesktopIntegrationTests(unittest.TestCase):
    def test_impossible_spawn_follows_alarm_after_short_reaction_window(self):
        from unittest.mock import patch, MagicMock
        from tempfile import TemporaryDirectory
        from pathlib import Path
        import game as desktop

        engine = Game(random.Random(17))
        audio = MagicMock(error='', muted=False)
        events = []
        audio.play_warning.side_effect = lambda: events.append(('alarm', engine.elapsed))
        audio.play.side_effect = lambda: events.append(('horn', engine.elapsed))
        ticks = iter(i*.1 for i in range(1000))
        keys = list(map(ord, 'Fast')) + [13, 13]
        seeded = opened = False

        def next_key(_delay):
            nonlocal seeded, opened
            if keys:
                return keys.pop(0)
            if engine.state == 'running' and not seeded:
                engine.score = 9
                seeded = True
                return 32
            if events and not opened:
                opened = True
                return 32
            return 27 if engine.spawn_count else -1

        with TemporaryDirectory() as directory, \
             patch.object(desktop.sys, 'argv', ['game.py', '--demo', '--database', str(Path(directory)/'drivers.json')]), \
             patch.object(desktop, 'Game', return_value=engine), \
             patch.object(desktop, 'Horns', return_value=audio), \
             patch.object(desktop.time, 'monotonic', side_effect=lambda: next(ticks)), \
             patch.object(desktop.cv2, 'namedWindow'), \
             patch.object(desktop.cv2, 'resizeWindow'), \
             patch.object(desktop.cv2, 'setMouseCallback'), \
             patch.object(desktop.cv2, 'imshow'), \
             patch.object(desktop.cv2, 'waitKeyEx', side_effect=next_key), \
             patch.object(desktop.cv2, 'getWindowProperty', return_value=1), \
             patch.object(desktop.cv2, 'destroyAllWindows'):
            desktop.main()
        self.assertEqual([event for event, _ in events], ['alarm', 'horn'])
        reaction_time = events[1][1]-events[0][1]
        self.assertGreaterEqual(reaction_time+1e-9, .7)
        self.assertLessEqual(reaction_time, .8+1e-9)
        audio.play_victory.assert_not_called()

    def test_car_settings_keep_score_and_cannot_change_automatic_difficulty(self):
        from unittest.mock import patch, MagicMock
        from tempfile import TemporaryDirectory
        from pathlib import Path
        import json
        import game as desktop

        engine = Game(random.Random(17))
        renderer = desktop.Renderer(desktop.ROOT / 'assets')
        audio = MagicMock(error='', muted=False)
        ticks = iter(i*.1 for i in range(1000))
        keys = iter(list(map(ord, 'Auto')) + [13, 13, ord('g'), 2555904, 27, ord('g'),
                    ord('1'), ord('4'), 2555904, 13, ord('p'), ord('r')]
                    + list(map(ord, 'Next')) + [13, 27])
        seeded = False
        settings_frames = 0

        def next_key(_delay):
            nonlocal seeded, settings_frames
            if engine.state == 'running' and not seeded:
                engine.score = 7
                seeded = True
            if engine.state in ('running', 'settings', 'paused'):
                self.assertEqual(engine.score, 7)
                self.assertEqual(engine.difficulty, 'hard')
                driver = json.loads(database.read_text())['drivers'][0]
                self.assertEqual(driver['attempts'], 0)
            if engine.state == 'settings':
                settings_frames += 1
            return next(keys)

        with TemporaryDirectory() as directory, \
             patch.object(desktop.sys, 'argv', ['game.py', '--demo', '--database', str(Path(directory)/'drivers.json')]), \
             patch.object(desktop, 'Game', return_value=engine), \
             patch.object(desktop, 'Horns', return_value=audio), \
             patch.object(desktop, 'Renderer', return_value=renderer), \
             patch.object(renderer, 'draw', wraps=renderer.draw) as draw, \
             patch.object(desktop.time, 'monotonic', side_effect=lambda: next(ticks)), \
             patch.object(desktop.cv2, 'namedWindow'), \
             patch.object(desktop.cv2, 'resizeWindow'), \
             patch.object(desktop.cv2, 'setMouseCallback'), \
             patch.object(desktop.cv2, 'imshow'), \
             patch.object(desktop.cv2, 'waitKeyEx', side_effect=next_key), \
             patch.object(desktop.cv2, 'getWindowProperty', return_value=1), \
             patch.object(desktop.cv2, 'destroyAllWindows'):
            database = Path(directory) / 'drivers.json'
            desktop.main()
            records = json.loads(database.read_text())['drivers']
        self.assertGreaterEqual(settings_frames, 6)
        self.assertEqual(draw.call_args.args[4], 1)
        self.assertEqual(records[0]['attempts'], 1)
        self.assertEqual(records[0]['best_difficulty'], 'hard')
        self.assertEqual(records[0]['best_score'], 7)
        self.assertEqual(records[1]['attempts'], 0)
        self.assertEqual(engine.score, 0)
        self.assertEqual(engine.difficulty, 'easy')

    def test_command_line_cannot_override_automatic_difficulty(self):
        from contextlib import redirect_stderr
        from io import StringIO
        from unittest.mock import patch
        import game as desktop

        with patch.object(desktop.sys, 'argv', ['game.py', '--difficulty', 'hard']), redirect_stderr(StringIO()):
            with self.assertRaises(SystemExit) as result:
                desktop.arguments()
        self.assertEqual(result.exception.code, 2)

    def test_alarm_plays_once_before_horn_and_does_not_repeat_after_interruptions(self):
        from unittest.mock import patch, MagicMock
        from tempfile import TemporaryDirectory
        from pathlib import Path
        import game as desktop

        engine = Game(random.Random(17))
        audio = MagicMock()
        audio.error = ''
        audio.muted = False
        ticks = iter(i*.1 for i in range(1000))
        keys = (list(map(ord, 'Alarm')) + [13, 13, 32] + [-1]*35
                + [32, ord('l')] + [-1]*12 + [ord('l'), ord('p')]
                + [-1]*10 + [ord('p')] + [-1]*60 + [27])
        with TemporaryDirectory() as directory, \
             patch.object(desktop.sys, 'argv', ['game.py', '--demo', '--database', str(Path(directory)/'drivers.json')]), \
             patch.object(desktop, 'Game', return_value=engine), \
             patch.object(desktop, 'Horns', return_value=audio) as factory, \
             patch.object(desktop.time, 'monotonic', side_effect=lambda: next(ticks)), \
             patch.object(desktop.cv2, 'namedWindow'), \
             patch.object(desktop.cv2, 'resizeWindow'), \
             patch.object(desktop.cv2, 'setMouseCallback'), \
             patch.object(desktop.cv2, 'imshow'), \
             patch.object(desktop.cv2, 'waitKeyEx', side_effect=keys), \
             patch.object(desktop.cv2, 'getWindowProperty', return_value=1), \
             patch.object(desktop.cv2, 'destroyAllWindows'):
            desktop.main()
        audio.play_warning.assert_called_once()
        audio.play.assert_called_once()
        calls = [call[0] for call in audio.method_calls]
        self.assertLess(calls.index('play_warning'), calls.index('play'))
        self.assertEqual(factory.call_args.args[2].name, 'smoke-alarm-beep.mp3')
        audio.close.assert_called_once()

    def test_victory_plays_once_survives_tracking_loss_and_saves_before_restart(self):
        from unittest.mock import patch, MagicMock
        from tempfile import TemporaryDirectory
        from pathlib import Path
        import json
        import game as desktop

        engine = Game(random.Random(17))
        audio = MagicMock()
        audio.error = ''
        audio.muted = False
        ticks = iter(i*.1 for i in range(1000))
        keys = iter(list(map(ord, 'Win')) + [13, 13, -1] + [-1]*5 + [ord('l')]
                    + [-1]*80 + [ord('p'), ord('b'), 27, -1, -1, ord('r')]
                    + list(map(ord, 'Next')) + [13, 27])
        seeded = False
        frozen_elapsed = None
        win_frames = 0
        stops_at_win = None

        def next_key(_delay):
            nonlocal seeded, frozen_elapsed, win_frames, stops_at_win
            if engine.state == 'running' and not seeded:
                seeded = True
                engine.score = SCORE_CAP-1
                engine.pending = .01
                engine.bikes = [Motorcycle(Rect(80, 757, 76, 122), 0, 0)]
            if engine.state == 'won':
                win_frames += 1
                if frozen_elapsed is None:
                    frozen_elapsed = engine.elapsed
                    stops_at_win = audio.stop.call_count
                self.assertEqual(engine.elapsed, frozen_elapsed)
                self.assertEqual(engine.score, SCORE_CAP)
                if win_frames < 70:
                    self.assertEqual(audio.stop.call_count, stops_at_win)
            return next(keys)

        with TemporaryDirectory() as directory, \
             patch.object(desktop.sys, 'argv', ['game.py', '--demo', '--database', str(Path(directory)/'drivers.json')]), \
             patch.object(desktop, 'Game', return_value=engine), \
             patch.object(desktop, 'Horns', return_value=audio) as audio_factory, \
             patch.object(desktop.time, 'monotonic', side_effect=lambda: next(ticks)), \
             patch.object(desktop.cv2, 'namedWindow'), \
             patch.object(desktop.cv2, 'resizeWindow'), \
             patch.object(desktop.cv2, 'setMouseCallback'), \
             patch.object(desktop.cv2, 'imshow'), \
             patch.object(desktop.cv2, 'waitKeyEx', side_effect=next_key), \
             patch.object(desktop.cv2, 'getWindowProperty', return_value=1), \
             patch.object(desktop.cv2, 'destroyAllWindows'):
            desktop.main()
            records = json.loads((Path(directory)/'drivers.json').read_text())['drivers']
        self.assertGreater(win_frames, 80)
        audio.play_victory.assert_called_once()
        audio.play.assert_not_called()
        audio.close.assert_called_once()
        self.assertNotIn(audio_factory.call_args.args[1], audio_factory.call_args.args[0])
        self.assertEqual([driver['name'] for driver in records], ['Win', 'Next'])
        self.assertEqual(records[0]['attempts'], 1)
        self.assertEqual(records[0]['best_seconds'], round(frozen_elapsed, 3))
        self.assertEqual(records[0]['best_score'], SCORE_CAP)
        self.assertEqual(records[1]['attempts'], 0)
        self.assertEqual(engine.state, 'ready')
        self.assertEqual(engine.score, 0)

    def test_demo_event_loop_controls_and_cleanup_without_window(self):
        from unittest.mock import patch, MagicMock
        from tempfile import TemporaryDirectory
        from pathlib import Path
        import json
        import game as desktop

        keys = (list(map(ord, 'QRG'))+[13, ord('g'), ord('4'), 2555904, 27,
                ord('g'), ord('4'), 2555904, 13, 13, ord('d'), ord('l')]
                + [-1]*3 + [ord('l'), 32] + [-1]*100
                + [ord('b'), 27, ord('r')] + list(map(ord, 'Next'))
                + [13, ord('m'), ord('f'), 27])
        session = Game(random.Random(17))
        audio = MagicMock()
        audio.error = ''
        audio.muted = False
        ticks = iter(i * .1 for i in range(1000))
        with TemporaryDirectory() as directory, \
             patch.object(desktop.sys, 'argv', ['game.py', '--demo', '--database', str(Path(directory)/'drivers.json')]), \
             patch.object(desktop, 'Game', return_value=session), \
             patch.object(desktop, 'Horns', return_value=audio), \
             patch.object(desktop.time, 'monotonic', side_effect=lambda: next(ticks)), \
             patch.object(desktop.cv2, 'namedWindow'), \
             patch.object(desktop.cv2, 'resizeWindow'), \
             patch.object(desktop.cv2, 'setMouseCallback'), \
             patch.object(desktop.cv2, 'setWindowProperty') as fullscreen, \
             patch.object(desktop.cv2, 'imshow') as display, \
             patch.object(desktop.cv2, 'waitKeyEx', side_effect=keys), \
             patch.object(desktop.cv2, 'getWindowProperty', return_value=1), \
             patch.object(desktop.cv2, 'destroyAllWindows') as cleanup:
            desktop.main()
            records = json.loads((Path(directory)/'drivers.json').read_text(encoding='utf-8'))['drivers']
        self.assertEqual(display.call_count, len(keys))
        self.assertEqual(display.call_args.args[1].shape, (800, 1280, 3))
        audio.play.assert_called()
        audio.close.assert_called_once()
        cleanup.assert_called_once()
        fullscreen.assert_called_once()
        self.assertTrue(audio.muted)
        self.assertEqual(session.difficulty, 'easy')
        self.assertEqual([driver['name'] for driver in records], ['QRG', 'Next'])
        self.assertEqual(records[0]['attempts'], 1)
        self.assertEqual(records[1]['attempts'], 0)


if __name__ == '__main__':
    unittest.main()
