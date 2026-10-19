"""Nonblocking MP3 horns using Windows winmm or Pygame's audio mixer."""
import ctypes
import os
import random


HORN_FILES = (
    'dragon-studio-car-honk-386166.mp3',
    'floraphonic-car-horn-2-189856.mp3',
    'floraphonic-car-horn-3-191449.mp3',
)
VICTORY_FILE = 'metal-slug-mission-complete.mp3'
WARNING_FILE = 'smoke-alarm-beep.mp3'


def horn_paths(assets):
    """Keep victory and warning tracks out of random motorcycle playback."""
    return [assets / name for name in HORN_FILES]


class Horns:
    def __init__(self, paths, victory_path=None, warning_path=None):
        self.aliases = []
        self.muted = False
        self.error = ''
        self.current = None
        self.rng = random.Random()
        self.dll = None
        self.pygame = None
        self.sounds = []
        self.owns_mixer = False
        self.victory = None
        self.warning = None
        self.warning_current = None
        paths = list(paths)
        if not paths:
            self.error = 'No horn MP3 files found.'
            return
        if os.name != 'nt':
            self.load_mixer(paths, victory_path, warning_path)
            return
        self.dll = ctypes.WinDLL('winmm')
        self.dll.mciSendStringW.argtypes = [ctypes.c_wchar_p, ctypes.c_wchar_p, ctypes.c_uint, ctypes.c_void_p]
        self.dll.mciGetErrorStringW.argtypes = [ctypes.c_uint, ctypes.c_wchar_p, ctypes.c_uint]
        for i, path in enumerate(paths):
            alias = f'systems_horn_{i}'
            if self.command(f'open "{path.resolve()}" type mpegvideo alias {alias}'):
                self.aliases.append(alias)
        if not self.aliases and not self.error:
            self.error = 'No horn MP3 files found.'
        if victory_path is not None:
            alias = 'systems_victory'
            if self.command(f'open "{victory_path.resolve()}" type mpegvideo alias {alias}'):
                self.victory = alias
        if warning_path is not None:
            alias = 'systems_warning'
            if self.command(f'open "{warning_path.resolve()}" type mpegvideo alias {alias}'):
                self.warning = alias

    def load_mixer(self, paths, victory_path, warning_path):
        os.environ.setdefault('PYGAME_HIDE_SUPPORT_PROMPT', '1')
        try:
            import pygame
        except ImportError:
            self.error = 'Horn audio requires Pygame. Install requirements.txt in the game environment.'
            return
        self.pygame = pygame
        try:
            if pygame.mixer.get_init() is None:
                pygame.mixer.init()
                self.owns_mixer = True
            self.sounds = [pygame.mixer.Sound(str(path.resolve())) for path in paths]
            if victory_path is not None:
                self.victory = pygame.mixer.Sound(str(victory_path.resolve()))
            if warning_path is not None:
                self.warning = pygame.mixer.Sound(str(warning_path.resolve()))
        except (pygame.error, OSError) as exc:
            self.error = f'Cannot load horn audio: {exc}'

    def command(self, command):
        code = self.dll.mciSendStringW(command, None, 0, None)
        if code:
            message = ctypes.create_unicode_buffer(256)
            self.dll.mciGetErrorStringW(code, message, 256)
            self.error = message.value
        return code == 0

    def play(self):
        if self.muted or not (self.aliases or self.sounds):
            return
        self.stop()
        self.current = self.play_sound(self.rng.choice(self.sounds if self.pygame is not None else self.aliases))

    def play_victory(self):
        self.stop()
        if not self.muted and self.victory is not None:
            self.current = self.play_sound(self.victory)

    def play_warning(self):
        if not self.muted and self.warning is not None:
            self.stop_warning()
            # A new countdown can arm on the same frame as a spawn when the
            # player keeps their eyes closed. Preserve that motorcycle's horn.
            self.warning_current = self.play_sound(self.warning)

    def play_sound(self, sound):
        if self.pygame is not None:
            try:
                channel = sound.play()
                if channel is None:
                    self.error = 'Cannot play horn audio: no free audio channel.'
                return channel
            except self.pygame.error as exc:
                self.error = f'Cannot play horn audio: {exc}'
            return
        if self.command(f'play {sound} from 0'):
            return sound

    def stop_warning(self):
        if self.warning_current is not None:
            if self.pygame is not None:
                self.warning_current.stop()
            else:
                self.command(f'stop {self.warning_current}')
            self.warning_current = None

    def stop(self):
        self.stop_warning()
        if self.current:
            if self.pygame is not None:
                self.current.stop()
            else:
                self.command(f'stop {self.current}')
            self.current = None

    def close(self):
        self.stop()
        for alias in self.aliases:
            self.command(f'close {alias}')
        if self.dll is not None and self.victory is not None:
            self.command(f'close {self.victory}')
        if self.dll is not None and self.warning is not None:
            self.command(f'close {self.warning}')
        self.aliases = []
        self.sounds = []
        self.victory = None
        self.warning = None
        if self.owns_mixer:
            self.pygame.mixer.quit()
            self.owns_mixer = False
