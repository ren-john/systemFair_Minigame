"""Exercise all native UI states without a camera, window, or driver database."""
from copy import deepcopy
from pathlib import Path
import unittest

import numpy as np

from preview_ui import scenes
from renderer import Renderer


def snapshot(game):
    return deepcopy((game.state, game.score, game.elapsed, game.pending,
                     game.closed_seconds, game.warning_triggered, game.player,
                     game.bikes, game.rng.getstate()))


class RendererTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.renderer = Renderer(Path(__file__).resolve().parent / 'assets')

    def test_all_screens_render_without_changing_game_or_driver_data(self):
        count = 0
        for label, game, obs, tracking, closed, eyes_valid, demo, ui in scenes():
            with self.subTest(screen=label):
                before, driver_before = snapshot(game), deepcopy(ui)
                frame = self.renderer.draw(game, obs, tracking, closed, 0, 'AUDIO / MUTED', .22,
                                           demo=demo, ui=ui, eyes_valid=eyes_valid, selected_car=1,
                                           celebration_time=1.5)
                self.assertEqual(frame.shape, (800, 1280, 3))
                self.assertEqual(frame.dtype, np.uint8)
                self.assertGreater(np.unique(frame[::8, ::8].reshape(-1, 3), axis=0).shape[0], 100)
                self.assertEqual(snapshot(game), before)
                self.assertEqual(ui, driver_before)
                count += 1
        self.assertEqual(count, 21)

    def test_long_names_and_error_details_render_on_all_screens(self):
        for label, game, obs, tracking, closed, eyes_valid, demo, ui in scenes():
            with self.subTest(screen=label):
                if ui.driver:
                    ui.driver['name'] = 'W'*24
                ui.name_input = 'W'*24
                for driver in ui.rankings:
                    driver['name'] = 'W'*24
                ui.save_error = 'A very long save failure detail. '*40
                frame = self.renderer.draw(game, obs, tracking, closed, 2, 'AUDIO UNAVAILABLE', .22,
                                           demo=demo, ui=ui, eyes_valid=eyes_valid)
                self.assertEqual(frame.shape, (800, 1280, 3))

    def test_victory_animation_is_independent_of_the_frozen_game_clock(self):
        case = next(case for case in scenes() if case[0] == '13_victory')
        _, game, obs, tracking, closed, eyes_valid, demo, ui = case
        before = snapshot(game)
        frames = [self.renderer.draw(game, obs, tracking, closed, 0, 'AUDIO / MUTED', .22,
                                     ui=ui, celebration_time=t) for t in (0., 2.)]
        self.assertTrue(np.any(frames[0] != frames[1]))
        self.assertEqual(snapshot(game), before)

    def test_camera_aspect_ratios_are_contained_without_changing_source_frames(self):
        _, game, obs, tracking, closed, _, _, ui = next(case for case in scenes() if case[0] == '07_driving')
        for h, w in ((480, 640), (360, 640), (640, 360)):
            with self.subTest(resolution=(w, h)):
                obs.frame = np.full((h, w, 3), (30, 50, 70), np.uint8)
                obs.frame[:, :w//2] = (50, 80, 110)
                before = obs.frame.copy()
                frame = self.renderer.draw(game, obs, tracking, closed, 0, 'AUDIO / MUTED', .22, ui=ui)
                self.assertEqual(frame.shape, (800, 1280, 3))
                np.testing.assert_array_equal(obs.frame, before)


if __name__ == '__main__':
    unittest.main()
