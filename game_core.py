"""Deterministic game rules, independent of camera, inference and rendering."""
from dataclasses import dataclass
import math
import random

ROAD_LEFT, ROAD_RIGHT = 70, 850
ROAD_TOP, ROAD_BOTTOM = 138, 756
PLAYER_Y = 640
ASLEEP_SECONDS = 3.0
SCORE_CAP = 10


@dataclass(frozen=True)
class Difficulty:
    start_score: int
    start_speed: float
    speed_step: float
    spawn_delay: float
    delay_step: float


DIFFICULTIES = {
    'easy': Difficulty(0, 180, 12, 2.5, .1),
    'medium': Difficulty(3, 240, 22, 2., .2),
    'hard': Difficulty(6, 330, 35, 1.3, .2),
    'impossible': Difficulty(8, 480, 55, .9, .2),
}


@dataclass
class Rect:
    x: float
    y: float
    w: float
    h: float

    def overlaps(self, other):
        return (self.x < other.x + other.w and self.x + self.w > other.x
                and self.y < other.y + other.h and self.y + self.h > other.y)


def player_from_face(box, frame_size):
    """Mirror camera x, scale the face rectangle to the road, lock center y."""
    fw, fh = frame_size
    x0, y0, x1, y1 = box
    width = min(ROAD_RIGHT - ROAD_LEFT, max(1, (x1 - x0) / fw * (ROAD_RIGHT - ROAD_LEFT)))
    height = min(220, max(1, (y1 - y0) / fh * (ROAD_BOTTOM - ROAD_TOP)))
    center = ROAD_LEFT + (1 - (x0 + x1) / (2 * fw)) * (ROAD_RIGHT - ROAD_LEFT)
    center = max(ROAD_LEFT + width / 2, min(ROAD_RIGHT - width / 2, center))
    return Rect(center - width / 2, PLAYER_Y - height / 2, width, height)


@dataclass
class Motorcycle:
    rect: Rect
    speed: float
    style: int


class Game:
    def __init__(self, rng=None):
        self.rng = rng or random.Random()
        self.reset()

    def reset(self):
        self.state = 'ready'
        self.elapsed = 0.0
        self.score = 0
        self.bikes = []
        self.pending = None
        self.clear_sleep()
        self.player = Rect(380, PLAYER_Y - 75, 160, 150)
        self.spawn_count = 0
        self.crash_reason = ''
        self.warning_triggered = False

    def crash(self, reason):
        self.state = 'over'
        self.crash_reason = reason
        self.pending = None
        self.clear_sleep()
        self.warning_triggered = False

    def win(self):
        self.state = 'won'
        self.score = SCORE_CAP
        self.bikes.clear()
        self.pending = None
        self.clear_sleep()
        self.warning_triggered = False

    def clear_sleep(self):
        self.previous_closed = False
        self.closed_seconds = 0.0

    @property
    def asleep(self):
        return self.closed_seconds >= ASLEEP_SECONDS

    @property
    def difficulty(self):
        return next(name for name, settings in reversed(DIFFICULTIES.items())
                    if self.score >= settings.start_score)

    @property
    def next_speed(self):
        settings = DIFFICULTIES[self.difficulty]
        return settings.start_speed + (self.score-settings.start_score) * settings.speed_step

    @property
    def spawn_delay(self):
        """Alarm-to-spawn time captured when the next countdown is armed."""
        settings = DIFFICULTIES[self.difficulty]
        score = min(self.score, SCORE_CAP-1)
        return round(settings.spawn_delay - (score-settings.start_score)*settings.delay_step, 2)

    def start(self):
        self.reset()
        self.state = 'running'

    def update(self, dt, player, eyes_closed, tracking=True, eye_dt=None, eyes_valid=True):
        """Return spawn count; warning_triggered marks a newly armed countdown.

        All timers freeze while paused/untracked.

        Three continuous seconds below the EAR threshold flags asleep and arms
        one score-dependent reaction timer. Reopening resets sleep qualification but never
        cancels an armed spawn. eye_dt uses camera sample time when supplied;
        redisplaying a cached camera frame must not accumulate closure time.
        """
        self.warning_triggered = False
        if self.state != 'running' or not tracking:
            self.clear_sleep()
            return 0
        if not math.isfinite(dt) or dt < 0:
            raise ValueError('dt must be finite and nonnegative')
        eye_dt = dt if eye_dt is None else eye_dt
        if not math.isfinite(eye_dt) or eye_dt < 0:
            raise ValueError('eye_dt must be finite and nonnegative')
        if eyes_closed and eyes_valid:
            if self.previous_closed:
                self.closed_seconds += eye_dt
            self.previous_closed = True
        else:
            self.clear_sleep()
        self.player = player
        self.elapsed += dt
        # Invisible side boundaries: contact uses the same half-pixel precision
        # as rendering, so smoothing toward an edge cannot avoid a collision.
        if player.x <= ROAD_LEFT + .5:
            self.crash('left road edge')
            return 0
        if player.x + player.w >= ROAD_RIGHT - .5:
            self.crash('right road edge')
            return 0
        spawned = 0
        # Update existing countdowns before arming a new one.
        if self.pending is not None:
            self.pending -= dt
            if self.pending <= 0:
                self.pending = None
                width, height = 76, 122
                center = self.player.x + self.player.w / 2 + self.rng.uniform(-90, 90)
                center = max(ROAD_LEFT + width / 2, min(ROAD_RIGHT - width / 2, center))
                self.bikes.append(Motorcycle(Rect(center - width / 2, ROAD_TOP - height, width, height),
                                             self.next_speed, self.rng.randrange(3)))
                self.spawn_count += 1
                spawned = 1
        if self.asleep and self.pending is None:
            self.pending = self.spawn_delay
            self.warning_triggered = True
        survivors = []
        dodged = 0
        for bike in self.bikes:
            old_y = bike.rect.y
            # A new motorcycle starts at the horizon on this update.
            if not (spawned and bike is self.bikes[-1]):
                bike.rect.y += bike.speed * dt
            swept = Rect(bike.rect.x, old_y, bike.rect.w, bike.rect.h + bike.rect.y - old_y)
            collided = swept.overlaps(self.player)
            if collided:
                self.crash('motorcycle')
            if bike.rect.y > ROAD_BOTTOM:
                if not collided and self.state != 'over':
                    dodged += 1
            else:
                survivors.append(bike)
        self.bikes = survivors
        # Resolve every collision before awarding points, so list order cannot
        # turn a simultaneous crash into a victory.
        if self.state == 'running':
            self.score = min(SCORE_CAP, self.score + dodged)
            if self.score == SCORE_CAP:
                self.win()
                return 0
        return spawned
