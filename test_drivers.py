import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from drivers import DriverStore, DriverSession, StoreError, format_time
from game_core import Game, Motorcycle, Rect, SCORE_CAP


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

    def test_ranking_prefers_score_then_fastest_time(self):
        a, b, c, d, e = (self.store.get_or_create(name) for name in ('Alex', 'Bea', 'Cam', 'Dee', 'Eli'))
        self.store.record(a['id'], 10, 60, 'impossible')
        self.store.record(b['id'], 10, 45, 'impossible')
        self.store.record(c['id'], 9, 10, 'impossible')
        self.store.record(d['id'], 8, 5, 'impossible')
        self.store.record(e['id'], 9, 8, 'impossible')
        self.assertEqual([d['name'] for d in self.store.ranking()], ['Bea', 'Alex', 'Eli', 'Cam', 'Dee'])
        self.store.record(a['id'], 10, 44.123, 'impossible')
        reloaded = DriverStore(self.path)
        self.assertEqual(reloaded.ranking()[0]['id'], a['id'])
        self.assertEqual(reloaded.ranking()[0]['best_seconds'], 44.123)
        self.assertEqual(reloaded.ranking()[0]['best_score'], 10)
        self.assertEqual(reloaded.ranking()[0]['attempts'], 2)

    def test_personal_best_prefers_higher_score_then_shorter_time(self):
        driver = self.store.get_or_create('Alex')
        self.store.record(driver['id'], 3, 30, 'medium')
        result, improved = self.store.record(driver['id'], 4, 45, 'medium')
        self.assertTrue(improved)
        self.assertEqual((result['best_score'], result['best_seconds']), (4, 45))
        for score, seconds in ((3, 1), (4, 50), (4, 45)):
            result, improved = self.store.record(driver['id'], score, seconds, 'medium')
            self.assertFalse(improved)
            self.assertEqual((result['best_score'], result['best_seconds']), (4, 45))
        result, improved = self.store.record(driver['id'], 4, 44.999, 'medium')
        self.assertTrue(improved)
        self.assertEqual(result['best_seconds'], 44.999)
        self.assertEqual(result['attempts'], 6)

    def test_equal_score_and_time_keep_existing_record_and_ties_are_stable(self):
        a, b = (self.store.get_or_create(name) for name in ('Alex', 'Bea'))
        self.store.record(b['id'], 6, 10, 'hard')
        self.store.record(a['id'], 6, 10, 'hard')
        result, improved = self.store.record(a['id'], 6, 10, 'easy')
        self.assertFalse(improved)
        self.assertEqual(result['best_difficulty'], 'hard')
        self.assertEqual([d['id'] for d in self.store.ranking()], [a['id'], b['id']])

    def test_millisecond_differences_are_ranked_and_displayed(self):
        a, b = (self.store.get_or_create(name) for name in ('Alex', 'Bea'))
        self.store.record(a['id'], 10, 45.124, 'impossible')
        self.store.record(b['id'], 10, 45.123, 'impossible')
        self.assertEqual([d['id'] for d in self.store.ranking()], [b['id'], a['id']])
        self.assertEqual(format_time(45.123), '00:45.123')
        self.assertEqual(format_time(59.9996), '01:00.000')

    def test_zero_score_result_is_distinct_from_no_run(self):
        driver = self.store.get_or_create('Alex')
        self.assertIsNone(driver['best_score'])
        self.assertEqual(self.store.ranking(), [])
        result, improved = self.store.record(driver['id'], 0, 0, 'easy')
        self.assertTrue(improved)
        self.assertEqual(result['best_score'], 0)
        self.assertEqual(len(self.store.ranking()), 1)

    def test_old_time_records_are_preserved_without_inventing_scores(self):
        driver = self.store.get_or_create('Alex')
        legacy = json.loads(self.path.read_text())
        legacy['version'] = 1
        legacy_driver = legacy['drivers'][0]
        del legacy_driver['best_score']
        legacy_driver.update(best_seconds=80.123, best_difficulty='impossible', attempts=3)
        self.path.write_text(json.dumps(legacy), encoding='utf-8')
        original = self.path.read_bytes()
        migrated = DriverStore(self.path)
        self.assertEqual(self.path.read_bytes(), original)
        returning = migrated.find('Alex')
        self.assertEqual(returning['id'], driver['id'])
        self.assertEqual(returning['attempts'], 3)
        self.assertEqual(returning['legacy_best'], {'seconds': 80.123, 'difficulty': 'impossible'})
        self.assertIsNone(returning['best_score'])
        self.assertEqual(migrated.ranking(), [])
        migrated.record(driver['id'], 8, 35, 'impossible')
        reloaded = DriverStore(self.path)
        self.assertEqual(reloaded.data['version'], 2)
        self.assertEqual(reloaded.find('Alex')['legacy_best'], returning['legacy_best'])
        self.assertEqual(reloaded.find('Alex')['attempts'], 4)
        self.assertEqual(reloaded.ranking()[0]['best_score'], 8)
        self.assertEqual(reloaded.ranking()[0]['best_seconds'], 35)

    def test_invalid_scores_and_times_do_not_change_saved_records(self):
        driver = self.store.get_or_create('Alex')
        original = self.path.read_bytes()
        for score, seconds in ((-1, 1), (11, 1), (True, 1), (2.5, 1),
                               (5, -1), (5, float('nan')), (5, float('inf')), (5, True)):
            with self.subTest(score=score, seconds=seconds), self.assertRaises(ValueError):
                self.store.record(driver['id'], score, seconds, 'medium')
            self.assertEqual(self.path.read_bytes(), original)

    def test_invalid_stored_scores_are_preserved_and_reported(self):
        driver = self.store.get_or_create('Alex')
        self.store.record(driver['id'], 7, 20, 'hard')
        for score in (-1, 11, True, 2.5, None):
            data = json.loads(json.dumps(self.store.data))
            data['drivers'][0]['best_score'] = score
            self.path.write_text(json.dumps(data), encoding='utf-8')
            original = self.path.read_bytes()
            with self.subTest(score=score), self.assertRaises(StoreError):
                DriverStore(self.path)
            self.assertEqual(self.path.read_bytes(), original)

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
                self.store.record(driver['id'], 7, 99, 'hard')
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
        game.score = 3
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
        game.score = 4
        session.ask_name()  # A restart also records an unfinished drive.
        self.assertEqual(self.store.find('QRG')['best_seconds'], 40)
        self.assertEqual(self.store.find('QRG')['best_score'], 4)
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

    def test_completed_run_saves_once_and_save_failure_can_be_retried(self):
        game = Game()
        session = DriverSession(game, self.store)
        session.ui.name_input = 'Winner'
        session.submit_name()
        session.start()
        game.elapsed = 50
        game.score = SCORE_CAP-1
        game.bikes = [Motorcycle(Rect(80, 757, 76, 122), 0, 0)]
        game.update(0, game.player, False)
        self.assertEqual(game.state, 'won')
        with patch.object(self.store, 'record', side_effect=StoreError('locked')):
            self.assertFalse(session.finish_run())
        self.assertEqual(game.state, 'won')
        self.assertTrue(session.run_open)
        self.assertTrue(session.finish_run())
        self.assertTrue(session.finish_run())
        self.assertTrue(session.ask_name())
        self.assertEqual(self.store.find('Winner')['attempts'], 1)
        self.assertEqual(self.store.find('Winner')['best_seconds'], 50)
        self.assertEqual(self.store.find('Winner')['best_score'], SCORE_CAP)
        self.assertEqual(self.store.find('Winner')['best_difficulty'], 'impossible')
        self.assertEqual(game.difficulty, 'easy')


if __name__ == '__main__':
    unittest.main()
