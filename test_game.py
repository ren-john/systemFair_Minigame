"""Run with: python -m unittest -v test_game"""
import random
import unittest

from game_core import Game, Motorcycle, Rect, PLAYER_Y, ROAD_LEFT, ROAD_RIGHT, DIFFICULTIES, player_from_face


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
        self.assertGreaterEqual(self.game.pending, 3)
        self.assertLessEqual(self.game.pending, 5)

    def test_reopening_after_asleep_does_not_cancel_spawn(self):
        self.fall_asleep()
        delay = self.game.pending
        self.assertGreaterEqual(delay, 3)
        self.assertLessEqual(delay, 5)
        self.assertEqual(self.game.update(delay-.001, self.game.player, False), 0)
        self.assertEqual(self.game.update(.002, self.game.player, False), 1)
        self.assertEqual(self.game.spawn_count, 1)
        self.assertIsNone(self.game.pending)
        self.assertFalse(self.game.asleep)
        self.assertEqual(self.game.closed_seconds, 0)

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

    def test_continuous_closure_repeats_with_new_random_delay(self):
        self.fall_asleep()
        self.assertEqual(self.game.update(self.game.pending, self.game.player, True), 1)
        self.assertGreaterEqual(self.game.pending, 3)
        self.assertLessEqual(self.game.pending, 5)

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

    def test_each_difficulty_increases_speed_per_spawn_even_without_score(self):
        first_speeds = []
        for name, settings in DIFFICULTIES.items():
            with self.subTest(difficulty=name):
                game = Game(random.Random(17), difficulty=name)
                game.start()
                game.update(0, game.player, True)
                game.update(3, game.player, True)
                for number in range(5):
                    game.bikes.clear()
                    self.assertEqual(game.update(game.pending, game.player, True), 1)
                    self.assertEqual(game.bikes[-1].speed, settings.start_speed + number*settings.speed_step)
                    self.assertEqual(game.score, 0)
                first_speeds.append(settings.start_speed)
                game.start()
                self.assertEqual(game.difficulty, name)
                self.assertEqual(game.next_speed, settings.start_speed)
        self.assertEqual(first_speeds, sorted(set(first_speeds)))

    def test_difficulty_changes_start_fresh_round_and_same_selection_preserves(self):
        self.fall_asleep()
        delay = self.game.pending
        self.game.set_difficulty('medium')
        self.assertEqual(self.game.pending, delay)
        self.assertEqual(self.game.state, 'running')
        self.game.set_difficulty('impossible')
        self.assertEqual(self.game.state, 'ready')
        self.assertIsNone(self.game.pending)
        self.assertEqual(self.game.spawn_count, 0)
        self.assertEqual(self.game.next_speed, DIFFICULTIES['impossible'].start_speed)
        with self.assertRaises(ValueError):
            self.game.set_difficulty('unknown')


class DesktopIntegrationTests(unittest.TestCase):
    def test_demo_event_loop_controls_and_cleanup_without_window(self):
        from unittest.mock import patch, MagicMock
        from tempfile import TemporaryDirectory
        from pathlib import Path
        import json
        import game as desktop

        keys = (list(map(ord, 'QRG'))+[13, ord('g'), ord('4'), 27, ord('g'), ord('4'), 2555904, 13]
                + list(map(ord, 'qrg'))+[13, 13, ord('d'), ord('l')]
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
        self.assertEqual(session.difficulty, 'impossible')
        self.assertEqual([driver['name'] for driver in records], ['QRG', 'Next'])
        self.assertEqual(records[0]['attempts'], 1)
        self.assertEqual(records[1]['attempts'], 0)


if __name__ == '__main__':
    unittest.main()
