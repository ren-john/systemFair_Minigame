"""Check real MP3 decoding and horn controls without an audio device."""
import os
from pathlib import Path
import unittest
from unittest.mock import MagicMock, patch

from audio import Horns, horn_paths, VICTORY_FILE, WARNING_FILE


ASSETS = Path(__file__).resolve().parent / 'assets'


@unittest.skipIf(os.name == 'nt', 'Linux mixer backend')
class MixerHornTests(unittest.TestCase):
    def setUp(self):
        self.environment = patch.dict(os.environ, {
            'SDL_AUDIODRIVER': 'dummy', 'PYGAME_HIDE_SUPPORT_PROMPT': '1',
        })
        self.environment.start()
        self.addCleanup(self.environment.stop)
        import pygame
        self.pygame = pygame
        pygame.mixer.quit()
        self.addCleanup(pygame.mixer.quit)
        self.horns = Horns(horn_paths(ASSETS), ASSETS / VICTORY_FILE, ASSETS / WARNING_FILE)
        self.addCleanup(self.horns.close)

    def test_supplied_mp3s_decode_and_play(self):
        self.assertEqual(self.horns.error, '')
        self.assertEqual(len(self.horns.sounds), 3)
        for sound in self.horns.sounds:
            with self.subTest(duration=sound.get_length()):
                self.assertGreater(sound.get_length(), 0)
                self.horns.rng = MagicMock()
                self.horns.rng.choice.return_value = sound
                self.horns.play()
                self.assertEqual(self.horns.error, '')
                self.assertIs(self.horns.current.get_sound(), sound)
                self.assertTrue(self.horns.current.get_busy())
                self.horns.stop()
                self.assertEqual(sound.get_num_channels(), 0)
                self.assertIsNone(self.horns.current)

    def test_retrigger_replaces_previous_horn_and_mute_prevents_playback(self):
        self.horns.rng = MagicMock()
        first, second = self.horns.sounds[:2]
        self.horns.rng.choice.side_effect = [first, second]
        self.horns.play()
        self.horns.play()
        self.assertEqual(first.get_num_channels(), 0)
        self.assertEqual(second.get_num_channels(), 1)
        self.horns.muted = True
        self.horns.stop()  # The game's M key stops a horn when muting.
        self.horns.play()
        self.assertIsNone(self.horns.current)
        self.assertFalse(self.pygame.mixer.get_busy())

    def test_close_releases_audio_device_and_is_repeatable(self):
        self.horns.play()
        self.horns.play_warning()
        self.horns.close()
        self.assertIsNone(self.pygame.mixer.get_init())
        self.horns.close()
        self.horns.play()
        self.assertIsNone(self.horns.current)
        self.assertIsNone(self.horns.warning_current)

    def test_existing_mixer_is_left_open(self):
        other = Horns(horn_paths(ASSETS))
        other.play()
        other.close()
        self.assertIsNotNone(self.pygame.mixer.get_init())
        self.assertIsNone(other.current)

    def test_missing_asset_reports_error_without_crashing(self):
        missing = Horns([ASSETS / 'missing-horn.mp3'])
        self.addCleanup(missing.close)
        self.assertIn('Cannot load horn audio:', missing.error)
        missing.play()
        self.assertIsNone(missing.current)

    def test_unavailable_device_reports_error_without_crashing(self):
        self.horns.close()
        with patch.object(self.pygame.mixer, 'init', side_effect=self.pygame.error('No audio device')):
            unavailable = Horns(horn_paths(ASSETS), ASSETS / VICTORY_FILE)
        self.addCleanup(unavailable.close)
        self.assertIn('No audio device', unavailable.error)
        unavailable.play()
        self.assertIsNone(unavailable.current)

    def test_victory_replaces_horn_and_respects_mute(self):
        self.assertGreater(self.horns.victory.get_length(), 6)
        self.horns.play()
        self.horns.play_warning()
        self.horns.play_victory()
        self.assertIs(self.horns.current.get_sound(), self.horns.victory)
        self.assertIsNone(self.horns.warning_current)
        self.assertTrue(all(sound.get_num_channels() == 0 for sound in self.horns.sounds))
        self.horns.muted = True
        self.horns.play_victory()
        self.assertIsNone(self.horns.current)
        self.assertFalse(self.pygame.mixer.get_busy())

    def test_alarm_plays_without_cutting_off_simultaneous_motorcycle_horn(self):
        self.assertGreater(self.horns.warning.get_length(), 0)
        self.horns.play()
        horn = self.horns.current
        self.horns.play_warning()
        self.assertIs(self.horns.current, horn)
        self.assertTrue(horn.get_busy())
        self.assertIs(self.horns.warning_current.get_sound(), self.horns.warning)
        self.horns.play_warning()
        self.assertEqual(self.horns.warning.get_num_channels(), 1)
        self.assertTrue(horn.get_busy())
        self.horns.stop()
        self.assertFalse(self.pygame.mixer.get_busy())

    def test_muted_alarm_is_silent_and_unmuting_allows_next_alarm(self):
        self.horns.muted = True
        self.horns.play_warning()
        self.assertIsNone(self.horns.warning_current)
        self.assertFalse(self.pygame.mixer.get_busy())
        self.horns.muted = False
        self.horns.play_warning()
        self.assertTrue(self.horns.warning_current.get_busy())


class HornFallbackTests(unittest.TestCase):
    def test_random_horns_exclude_victory_and_eye_warning_assets(self):
        paths = horn_paths(ASSETS)
        self.assertEqual(len(paths), 3)
        self.assertTrue(all(path.is_file() for path in paths))
        self.assertNotIn(ASSETS / VICTORY_FILE, paths)
        self.assertNotIn(ASSETS / WARNING_FILE, paths)

    def test_no_assets_is_reported_without_initializing_audio(self):
        horns = Horns([])
        self.assertEqual(horns.error, 'No horn MP3 files found.')
        horns.play()
        horns.stop()
        horns.close()

    def test_windows_still_uses_winmm(self):
        path = ASSETS / 'dragon-studio-car-honk-386166.mp3'
        dll = MagicMock()
        dll.mciSendStringW.return_value = 0
        with patch('audio.os.name', 'nt'), patch('audio.ctypes.WinDLL', return_value=dll, create=True):
            horns = Horns([path])
        self.assertEqual(horns.error, '')
        self.assertIsNone(horns.pygame)
        horns.play()
        self.assertIsNotNone(horns.current)
        horns.stop()
        self.assertIsNone(horns.current)
        horns.close()
        commands = [call.args[0] for call in dll.mciSendStringW.call_args_list]
        self.assertTrue(commands[0].startswith('open '))
        self.assertEqual(commands[1:], [
            'play systems_horn_0 from 0', 'stop systems_horn_0', 'close systems_horn_0',
        ])

    def test_windows_victory_has_its_own_alias_and_is_closed(self):
        paths = horn_paths(ASSETS)
        victory = ASSETS / VICTORY_FILE
        dll = MagicMock()
        dll.mciSendStringW.return_value = 0
        with patch('audio.os.name', 'nt'), patch('audio.ctypes.WinDLL', return_value=dll, create=True):
            horns = Horns(paths, victory)
        horns.play()
        horns.play_victory()
        self.assertEqual(horns.current, 'systems_victory')
        horns.close()
        commands = [call.args[0] for call in dll.mciSendStringW.call_args_list]
        self.assertIn('play systems_victory from 0', commands)
        self.assertIn('close systems_victory', commands)
        self.assertNotIn('systems_victory', horns.aliases)

    def test_windows_alarm_has_its_own_alias_and_stops_with_other_audio(self):
        paths = horn_paths(ASSETS)
        victory, warning = ASSETS / VICTORY_FILE, ASSETS / WARNING_FILE
        dll = MagicMock()
        dll.mciSendStringW.return_value = 0
        with patch('audio.os.name', 'nt'), patch('audio.ctypes.WinDLL', return_value=dll, create=True):
            horns = Horns(paths, victory, warning)
        horns.play()
        current = horns.current
        horns.play_warning()
        self.assertEqual(horns.current, current)
        self.assertEqual(horns.warning_current, 'systems_warning')
        horns.stop()
        self.assertIsNone(horns.current)
        self.assertIsNone(horns.warning_current)
        horns.close()
        commands = [call.args[0] for call in dll.mciSendStringW.call_args_list]
        self.assertIn('play systems_warning from 0', commands)
        self.assertIn('stop systems_warning', commands)
        self.assertIn('close systems_warning', commands)


if __name__ == '__main__':
    unittest.main()
