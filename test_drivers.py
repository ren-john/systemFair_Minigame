import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from drivers import DriverStore, DriverSession, StoreError
from game_core import Game


class DriverTests(unittest.TestCase):
    def setUp(self):
        self.directory = TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name)/'drivers.json'
        self.store = DriverStore(self.path)

    def test_names_are_unique_ignoring_case_and_spacing_with_stable_id(self):
        first = self.store.get_or_create('  RJ   Santos  ')
        second = self.store.get_or_create('rj santos')
        self.assertEqual(first['id'], second['id'])
        self.assertEqual(first['name'], 'RJ Santos')
        reloaded = DriverStore(self.path)
        self.assertEqual(reloaded.get_or_create('RJ SANTOS')['id'], first['id'])
        self.assertNotEqual(reloaded.get_or_create('Alex')['id'], first['id'])
        self.assertEqual(len(reloaded.data['drivers']), 2)

    def test_high_score_only_increases_and_ranking_sorts_longest_first(self):
        a, b = (self.store.get_or_create(name) for name in ('Alex', 'Bea'))
        self.store.record(a['id'], 50, 'medium')
        self.store.record(b['id'], 70, 'hard')
        shorter, improved = self.store.record(a['id'], 20, 'easy')
        self.assertFalse(improved)
        self.assertEqual(shorter['best_seconds'], 50)
        self.assertEqual(shorter['best_difficulty'], 'medium')
        self.assertEqual([d['name'] for d in self.store.ranking()], ['Bea', 'Alex'])
        self.store.record(a['id'], 80.123, 'impossible')
        reloaded = DriverStore(self.path)
        self.assertEqual(reloaded.ranking()[0]['id'], a['id'])
        self.assertEqual(reloaded.ranking()[0]['best_seconds'], 80.123)
        self.assertEqual(reloaded.ranking()[0]['attempts'], 3)

    def test_equal_score_keeps_existing_record_and_ties_are_stable(self):
        a, b = (self.store.get_or_create(name) for name in ('Alex', 'Bea'))
        self.store.record(b['id'], 10, 'medium')
        self.store.record(a['id'], 10, 'hard')
        result, improved = self.store.record(a['id'], 10, 'easy')
        self.assertFalse(improved)
        self.assertEqual(result['best_difficulty'], 'hard')
        self.assertEqual([d['id'] for d in self.store.ranking()], [a['id'], b['id']])

    def test_blank_and_invalid_names_do_not_create_drivers(self):
        for name in ('', '   ', 'A'*25, '<script>', 'Name\x00'):
            with self.subTest(name=name), self.assertRaises(ValueError):
                self.store.get_or_create(name)
        self.assertEqual(self.store.data['drivers'], [])

    def test_failed_atomic_save_keeps_existing_file_and_memory(self):
        driver = self.store.get_or_create('Alex')
        original = self.path.read_bytes()
        with patch('drivers.os.replace', side_effect=PermissionError('locked')):
            with self.assertRaises(StoreError):
                self.store.record(driver['id'], 99, 'hard')
        self.assertEqual(self.path.read_bytes(), original)
        self.assertEqual(self.store.find('Alex')['attempts'], 0)
        self.assertEqual(list(self.path.parent.glob('*.tmp')), [])

    def test_corrupt_file_is_preserved_instead_of_overwritten(self):
        self.path.write_text('{broken', encoding='utf-8')
        with self.assertRaises(StoreError):
            DriverStore(self.path)
        self.assertEqual(self.path.read_text(encoding='utf-8'), '{broken')

    def test_duplicate_identity_in_database_is_rejected(self):
        self.store.get_or_create('Alex')
        data = self.store.data
        data['drivers'].append(dict(data['drivers'][0], id='D0002', name='alex'))
        data['next_id'] = 3
        self.path.write_text(json.dumps(data), encoding='utf-8')
        with self.assertRaises(StoreError):
            DriverStore(self.path)

    def test_restart_prompts_for_name_and_returning_player_updates_same_record(self):
        game = Game()
        session = DriverSession(game, self.store)
        self.assertEqual(game.state, 'name')
        session.ui.name_input = 'QRG'
        self.assertTrue(session.submit_name())
        original_id = session.ui.driver['id']
        session.start()
        game.elapsed = 30
        game.crash('motorcycle')
        session.finish_run()
        session.finish_run()
        self.assertEqual(self.store.find('qrg')['attempts'], 1)
        self.assertTrue(session.ask_name())
        self.assertEqual(game.state, 'name')
        self.assertEqual(session.ui.name_input, '')
        self.assertIsNone(session.ui.driver)
        session.ui.name_input = 'qrg'
        session.submit_name()
        self.assertEqual(session.ui.driver['id'], original_id)
        session.start()
        game.elapsed = 40
        session.ask_name()  # A restart also records an unfinished drive.
        self.assertEqual(self.store.find('QRG')['best_seconds'], 40)
        self.assertEqual(len(self.store.data['drivers']), 1)

    def test_record_failure_keeps_run_for_retry_and_prevents_discard(self):
        game = Game()
        session = DriverSession(game, self.store)
        session.ui.name_input = 'Alex'
        session.submit_name()
        session.start()
        game.elapsed = 20
        with patch.object(self.store, 'record', side_effect=StoreError('locked')):
            self.assertFalse(session.ask_name())
        self.assertTrue(session.run_open)
        self.assertEqual(session.ui.driver['name'], 'Alex')
        self.assertTrue(session.finish_run())
        self.assertEqual(self.store.find('Alex')['best_seconds'], 20)
        self.assertEqual(session.ui.save_error, '')


if __name__ == '__main__':
    unittest.main()
