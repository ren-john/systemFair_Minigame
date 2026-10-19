"""Bounded inertial steering and gradual correction after face reacquisition."""
from dataclasses import dataclass
import math

from game_core import PLAYER_Y, ROAD_LEFT, ROAD_RIGHT, Rect

FRESH_SECONDS = .20
COAST_SECONDS = .75


@dataclass
class SteeringState:
    player: Rect
    active: bool
    predicted: bool = False
    recovering: bool = False


class HeadSteering:
    def __init__(self):
        self.player = Rect(380, PLAYER_Y-75, 160, 150)
        self.target = None
        self.last_seen = None
        self.velocity = 0.
        self.lost = False
        self.recovering = False

    @staticmethod
    def center(rect):
        return rect.x + rect.w/2

    def update(self, now, dt, measurement=None, sample_time=None):
        fresh = (measurement is not None and sample_time is not None
                 and 0 <= now-sample_time <= FRESH_SECONDS)
        if fresh and (self.last_seen is None or sample_time > self.last_seen):
            if self.last_seen is None:
                self.player = Rect(measurement.x, measurement.y, measurement.w, measurement.h)
            else:
                gap = sample_time-self.last_seen
                if gap <= FRESH_SECONDS and not self.lost:
                    raw = (self.center(measurement)-self.center(self.target))/gap
                    raw = max(-900., min(900., raw))
                    blend = 1-math.exp(-gap/.08)
                    # A direction reversal must be reflected immediately.
                    self.velocity = raw if raw*self.velocity < 0 else self.velocity + blend*(raw-self.velocity)
                else:
                    self.velocity = 0.
                if self.lost or gap > FRESH_SECONDS:
                    self.recovering = True
            self.target = measurement
            self.last_seen = sample_time
            self.lost = False
        if self.last_seen is None:
            return SteeringState(self.player, False)

        age = max(0., now-self.last_seen)
        active = age <= COAST_SECONDS
        center = self.center(self.player)
        width, height = self.player.w, self.player.h
        if fresh:
            # ~1 second to settle after a dropout; normal steering is faster.
            tau = .32 if self.recovering else .065
            blend = 1-math.exp(-max(0., dt)/tau)
            center += blend*(self.center(self.target)-center)
            size_blend = 1-math.exp(-max(0., dt)/.18)
            width += size_blend*(self.target.w-width)
            height += size_blend*(self.target.h-height)
            if abs(self.center(self.target)-center) < 2:
                self.recovering = False
        else:
            self.lost = True
            # Integrate a decaying velocity; never extrapolate indefinitely.
            a0 = max(0., min(COAST_SECONDS, age-dt))
            a1 = min(COAST_SECONDS, age)
            center += self.velocity*.45*(math.exp(-a0/.45)-math.exp(-a1/.45))
        center = max(ROAD_LEFT+width/2, min(ROAD_RIGHT-width/2, center))
        self.player = Rect(center-width/2, PLAYER_Y-height/2, width, height)
        return SteeringState(self.player, active, active and not fresh, self.recovering and fresh)
