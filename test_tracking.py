"""Camera-independent checks for motion recovery and MediaPipe eye geometry."""
import math
import unittest

import numpy as np

from face_geometry import LEFT_EYE, RIGHT_EYE, mesh_measurements
from game_core import Game, Rect, PLAYER_Y, ROAD_LEFT, ROAD_RIGHT
from steering import HeadSteering


def car(center):
    return Rect(center-80, PLAYER_Y-75, 160, 150)


class SteeringTests(unittest.TestCase):
    def moving(self, direction=1):
        steering = HeadSteering()
        steering.update(0, 0, car(400), 0)
        steering.update(.1, .1, car(400+20*direction), .1)
        return steering

    def test_no_prediction_without_a_face_history(self):
        self.assertFalse(HeadSteering().update(1, .1).active)

    def test_coasts_in_last_direction_and_decelerates(self):
        for direction in (-1, 1):
            with self.subTest(direction=direction):
                steering = self.moving(direction)
                x0 = steering.player.x
                first = steering.update(.15, .05)
                second = steering.update(.20, .05)
                self.assertTrue(first.predicted and first.active)
                self.assertGreater((first.player.x-x0)*direction, 0)
                self.assertGreater((second.player.x-first.player.x)*direction, 0)
                self.assertLess(abs(second.player.x-first.player.x), abs(first.player.x-x0))
                self.assertEqual(second.player.y+second.player.h/2, PLAYER_Y)

    def test_latest_direction_reversal_wins(self):
        steering = self.moving()
        steering.update(.15, .05, car(390), .15)
        previous = steering.player.x
        self.assertLess(steering.update(.20, .05).player.x, previous)

    def test_reacquisition_corrects_gradually_without_teleporting(self):
        steering = self.moving()
        before = steering.update(.15, .05).player.x
        target = car(200)
        recovered = steering.update(.2, .05, target, .2)
        self.assertTrue(recovered.recovering)
        self.assertLess(recovered.player.x, before)
        self.assertGreater(recovered.player.x, target.x+100)
        previous_error = abs(recovered.player.x-target.x)
        for i in range(1, 40):
            stamp = .2+i*.05
            current = steering.update(stamp, .05, target, stamp)
            error = abs(current.player.x-target.x)
            self.assertLessEqual(error, previous_error)
            previous_error = error
        self.assertLess(previous_error, 1)
        self.assertFalse(current.recovering)

    def test_long_loss_stops_and_cannot_move_outside_road(self):
        steering = HeadSteering()
        steering.update(0, 0, car(700), 0)
        steering.update(.1, .1, car(770), .1)
        for i in range(1, 20):
            state = steering.update(.1+i*.05, .05)
            self.assertGreaterEqual(state.player.x, ROAD_LEFT)
            self.assertLessEqual(state.player.x+state.player.w, ROAD_RIGHT)
        self.assertFalse(state.active)
        stopped = state.player.x
        self.assertEqual(steering.update(2, 1).player.x, stopped)

    def test_cached_detection_cannot_extend_coasting_forever(self):
        steering = self.moving()
        old = car(420)
        self.assertTrue(steering.update(.4, .1, old, .1).predicted)
        self.assertFalse(steering.update(1, .6, old, .1).active)

    def test_prediction_is_consistent_across_render_frame_rates(self):
        results = []
        for step in (.01, .05):
            steering = self.moving()
            for i in range(1, round(.5/step)+1):
                steering.update(.1+i*step, step)
            results.append(steering.player.x)
        self.assertAlmostEqual(*results)

    def test_smoothed_steering_and_coasting_can_hit_roadside(self):
        for predicted in (False, True):
            for direction in (-1, 1):
                with self.subTest(predicted=predicted, direction=direction):
                    game = Game()
                    game.start()
                    steering = HeadSteering()
                    edge_center = ROAD_LEFT+80 if direction == -1 else ROAD_RIGHT-80
                    steering.update(0, 0, car(edge_center-direction*70), 0)
                    motion = steering.update(.1, .1, car(edge_center), .1)
                    for i in range(1, 12):
                        stamp = .1+i*.05
                        motion = steering.update(stamp, .05, None if predicted else car(edge_center),
                                                 None if predicted else stamp)
                        game.update(.05, motion.player, False, tracking=motion.active, eyes_valid=not predicted)
                        if game.state == 'over':
                            break
                    self.assertEqual(game.state, 'over')
                    self.assertEqual(game.crash_reason, 'left road edge' if direction == -1 else 'right road edge')

    def test_prediction_keeps_game_running_but_never_counts_sleep(self):
        game = Game()
        game.start()
        game.update(0, game.player, True)
        game.update(2.9, game.player, True)
        moved = car(300)
        game.update(.1, moved, True, tracking=True, eyes_valid=False)
        self.assertEqual(game.player, moved)
        self.assertGreater(game.elapsed, 2.9)
        self.assertEqual(game.closed_seconds, 0)
        self.assertIsNone(game.pending)
        game.update(.1, moved, True, tracking=True, eyes_valid=True)
        self.assertFalse(game.asleep)

    def test_armed_countdown_continues_during_short_prediction(self):
        game = Game()
        game.start()
        game.update(0, game.player, True)
        game.update(3, game.player, True)
        delay = game.pending
        game.update(.1, car(300), False, tracking=True, eyes_valid=False)
        self.assertAlmostEqual(game.pending, delay-.1)
        self.assertFalse(game.asleep)


class MeshGeometryTests(unittest.TestCase):
    def points(self, ear=.3, count=478):
        points = np.full((count, 2), [200., 200.])
        points[10], points[152] = [200, 80], [200, 350]
        points[234], points[454] = [80, 200], [330, 200]
        eye = np.array([[0, 0], [10, -20*ear], [30, -20*ear],
                        [40, 0], [30, 20*ear], [10, 20*ear]])
        points[list(RIGHT_EYE)] = eye+[110, 180]
        points[list(LEFT_EYE)] = eye+[240, 180]
        return points

    def test_468_and_478_point_eyes_have_correct_ear_and_box(self):
        for count in (468, 478):
            for expected in (0., .15, .3):
                with self.subTest(count=count, ear=expected):
                    box, ear = mesh_measurements(self.points(expected, count), (400, 400))
                    np.testing.assert_allclose(box, [80, 80, 330, 350])
                    self.assertAlmostEqual(ear, expected)

    def test_invalid_eyes_do_not_remove_usable_face_box(self):
        points = self.points()
        points[list(LEFT_EYE)] = [200, 180]
        points[list(RIGHT_EYE)] = [200, 180]
        box, ear = mesh_measurements(points, (400, 400))
        self.assertIsNotNone(box)
        self.assertTrue(math.isnan(ear))

    def test_one_eye_fallback_and_manual_side(self):
        points = self.points(.15)
        points[list(LEFT_EYE)] = [200, 180]
        self.assertAlmostEqual(mesh_measurements(points, (400, 400))[1], .15)
        self.assertTrue(math.isnan(mesh_measurements(points, (400, 400), 'left')[1]))

    def test_nonfinite_or_old_32_point_inputs_are_rejected(self):
        points = self.points()
        points[10, 0] = float('nan')
        for invalid in (points, np.zeros((32, 2))):
            box, ear = mesh_measurements(invalid, (400, 400))
            self.assertIsNone(box)
            self.assertTrue(math.isnan(ear))


if __name__ == '__main__':
    unittest.main()
