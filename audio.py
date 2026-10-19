"""Nonblocking MP3 horns using Windows' built-in multimedia player."""
import ctypes
import os
import random


class Horns:
    def __init__(self, paths):
        self.aliases = []
        self.muted = False
        self.error = ''
        self.current = None
        self.rng = random.Random()
        self.dll = None
        if os.name != 'nt':
            self.error = 'Horn audio requires Windows.'
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

    def command(self, command):
        code = self.dll.mciSendStringW(command, None, 0, None)
        if code:
            message = ctypes.create_unicode_buffer(256)
            self.dll.mciGetErrorStringW(code, message, 256)
            self.error = message.value
        return code == 0

    def play(self):
        if self.muted or not self.aliases:
            return
        self.stop()
        self.current = self.rng.choice(self.aliases)
        self.command(f'play {self.current} from 0')

    def stop(self):
        if self.current:
            self.command(f'stop {self.current}')
            self.current = None

    def close(self):
        self.stop()
        for alias in self.aliases:
            self.command(f'close {alias}')
        self.aliases = []
