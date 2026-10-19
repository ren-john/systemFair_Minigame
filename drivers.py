"""Local driver records ranked by highest score, then fastest active time."""
from copy import deepcopy
from dataclasses import dataclass, field
from datetime import datetime, timezone
import json
import math
import os
from pathlib import Path
import re
import tempfile

from game_core import DIFFICULTIES, SCORE_CAP

MAX_NAME = 24


def clean_name(value):
    if not isinstance(value, str):
        raise ValueError('Enter a driver name.')
    name = ' '.join(value.split())
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9 .'-]{0,23}", name):
        raise ValueError('Use 1-24 letters/numbers; spaces, dots, apostrophes and hyphens are allowed.')
    return name


def format_time(seconds):
    milliseconds = round(max(0, seconds)*1000)
    minutes, remainder = divmod(milliseconds, 60000)
    return f'{minutes:02}:{remainder//1000:02}.{remainder%1000:03}'


def format_best(driver):
    if driver['best_score'] is None:
        return 'NO SCORED RUN YET'
    return f"{driver['best_score']}/{SCORE_CAP}  /  {format_time(driver['best_seconds'])}"


class StoreError(RuntimeError):
    pass


def require(condition):
    if not condition:
        raise ValueError('Invalid or duplicate driver record.')


class DriverStore:
    def __init__(self, path):
        self.path = Path(path)
        self.data = {'version': 2, 'next_id': 1, 'drivers': []}
        if self.path.exists():
            try:
                data = json.loads(self.path.read_text(encoding='utf-8'))
                require(data['version'] in (1, 2) and isinstance(data['drivers'], list))
                require(type(data['next_id']) is int and data['next_id'] > 0)
                ids, names = set(), set()
                for driver in data['drivers']:
                    name = clean_name(driver['name'])
                    key = name.casefold()
                    require(re.fullmatch(r'D\d{4,}', driver['id']))
                    require(driver['id'] not in ids and key not in names)
                    require(driver['name_key'] == key)
                    require(0 < int(driver['id'][1:]) < data['next_id'])
                    require(type(driver['attempts']) is int and driver['attempts'] >= 0)
                    require(type(driver['best_seconds']) in (int, float))
                    require(math.isfinite(driver['best_seconds']) and driver['best_seconds'] >= 0)
                    require(driver['best_difficulty'] in DIFFICULTIES or driver['best_difficulty'] is None)
                    if data['version'] == 2:
                        score = driver['best_score']
                        require(score is None or (type(score) is int and 0 <= score <= SCORE_CAP))
                        if score is None:
                            require(driver['best_seconds'] == 0 and driver['best_difficulty'] is None)
                        else:
                            require(driver['attempts'] > 0 and driver['best_difficulty'] in DIFFICULTIES)
                    ids.add(driver['id'])
                    names.add(key)
                if data['version'] == 1:
                    # Scores were never stored by v1. Preserve its time record
                    # as history instead of guessing a score or a completion.
                    for driver in data['drivers']:
                        if driver['attempts']:
                            driver['legacy_best'] = {
                                'seconds': driver['best_seconds'],
                                'difficulty': driver['best_difficulty'],
                            }
                        driver.update(best_score=None, best_seconds=0., best_difficulty=None)
                    data['version'] = 2
                self.data = data
            except (OSError, ValueError, KeyError, TypeError, OverflowError) as exc:
                raise StoreError(f'Cannot read driver database {self.path}. Existing data was not changed: {exc}') from exc
        else:
            self._commit(self.data)

    def _commit(self, data):
        temporary = None
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=self.path.parent,
                                             prefix=self.path.name+'.', suffix='.tmp', delete=False) as handle:
                temporary = Path(handle.name)
                json.dump(data, handle, indent=2, ensure_ascii=False, allow_nan=False)
                handle.write('\n')
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, self.path)
        except OSError as exc:
            raise StoreError(f'Could not save driver records: {exc}') from exc
        finally:
            if temporary is not None and temporary.exists():
                try:
                    temporary.unlink()
                except OSError:
                    pass
        self.data = data

    def find(self, name):
        try:
            key = clean_name(name).casefold()
        except ValueError:
            return None
        return next((deepcopy(d) for d in self.data['drivers'] if d['name_key'] == key), None)

    def get_or_create(self, name):
        name = clean_name(name)
        existing = self.find(name)
        if existing:
            return existing
        data = deepcopy(self.data)
        driver = {'id': f"D{data['next_id']:04}", 'name': name, 'name_key': name.casefold(),
                  'best_score': None, 'best_seconds': 0., 'best_difficulty': None, 'attempts': 0,
                  'created_at': datetime.now(timezone.utc).isoformat(), 'last_played_at': None}
        data['next_id'] += 1
        data['drivers'].append(driver)
        self._commit(data)
        return deepcopy(driver)

    def record(self, driver_id, score, seconds, difficulty):
        if (type(score) is not int or not 0 <= score <= SCORE_CAP
                or type(seconds) not in (int, float) or not math.isfinite(seconds)
                or seconds < 0 or difficulty not in DIFFICULTIES):
            raise ValueError('Invalid drive result.')
        data = deepcopy(self.data)
        driver = next((d for d in data['drivers'] if d['id'] == driver_id), None)
        if driver is None:
            raise ValueError(f'Unknown driver: {driver_id}')
        seconds = round(seconds, 3)
        improved = (driver['best_score'] is None or score > driver['best_score']
                    or (score == driver['best_score'] and seconds < driver['best_seconds']))
        if improved:
            driver['best_score'] = score
            driver['best_seconds'] = seconds
            driver['best_difficulty'] = difficulty
        driver['attempts'] += 1
        driver['last_played_at'] = datetime.now(timezone.utc).isoformat()
        self._commit(data)
        return deepcopy(driver), improved

    def ranking(self):
        drivers = sorted((d for d in self.data['drivers'] if d['best_score'] is not None),
                         key=lambda d: (-d['best_score'], d['best_seconds'], int(d['id'][1:])))
        return [dict(deepcopy(d), rank=i+1) for i, d in enumerate(drivers)]


@dataclass
class DriverUI:
    driver: object = None
    name_input: str = ''
    name_match: object = None
    name_error: str = ''
    save_error: str = ''
    result_message: str = ''
    rankings: list = field(default_factory=list)
    ranking_page: int = 0


class DriverSession:
    def __init__(self, game, store):
        self.game = game
        self.store = store
        self.ui = DriverUI(rankings=store.ranking())
        self.run_open = False
        self.ask_name()

    def ask_name(self):
        if not self.finish_run():
            return False
        self.game.reset()
        self.game.state = 'name'
        self.ui.driver = None
        self.ui.name_input = ''
        self.ui.name_match = None
        self.ui.name_error = ''
        self.ui.result_message = ''
        return True

    def type_name(self, key):
        if key in (8, 127):
            self.ui.name_input = self.ui.name_input[:-1]
        elif 32 <= key <= 126 and len(self.ui.name_input) < MAX_NAME:
            self.ui.name_input += chr(key)
        self.ui.name_match = self.store.find(self.ui.name_input)
        self.ui.name_error = ''

    def submit_name(self):
        try:
            self.ui.driver = self.store.get_or_create(self.ui.name_input)
        except (ValueError, StoreError) as exc:
            self.ui.name_error = str(exc)
            return False
        self.game.state = 'ready'
        return True

    def start(self):
        if self.ui.driver is None:
            return False
        self.game.start()
        self.run_open = True
        self.ui.result_message = ''
        return True

    def finish_run(self):
        if not self.run_open:
            return True
        try:
            driver, improved = self.store.record(self.ui.driver['id'], self.game.score,
                                                 self.game.elapsed, self.game.difficulty)
        except StoreError as exc:
            self.ui.save_error = str(exc)
            return False
        self.ui.driver = driver
        self.ui.rankings = self.store.ranking()
        self.ui.save_error = ''
        self.ui.result_message = ('NEW PERSONAL BEST!  ' if improved else 'PERSONAL BEST  ') + format_best(driver)
        self.run_open = False
        return True
