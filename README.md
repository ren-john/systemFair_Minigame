# Night Shift — Systems Fair

A Windows/Linux laptop desktop game: use the built-in webcam and move your head
sideways to dodge motorcycles. Run the Python game directly on the laptop.
Uses the supplied car/motorcycle PNGs, three MP3 horns, the eye-opening alarm,
and the mission-complete track in `assets/`.

## Play

Double-click **start_game.bat**, type a driver name, and press **Enter** to
confirm it. A **HOW TO PLAY** tutorial explains steering, the three-second
eye closure, reopening at the alarm, dodging, and the 10-point mission.
Press **Enter** to continue to the driving setup, then face your camera and
press **Enter** again to start driving. The tutorial appears for every driver,
including returning names, and does not add driving time or an attempt.
The launcher uses the existing `../Model Training/venv` environment. The first
camera startup may take a few seconds while face tracking loads.

Dodge **10 motorcycles** to complete the mission. The score display shows
progress toward 10. Winning freezes the drive and opens a celebration splash
with animated confetti, the driver's name, score, and completion time. The
`metal-slug-mission-complete.mp3` victory track plays once and respects mute.
The splash stays visible until you choose another action; **R** opens the next
driver's name entry and **Esc** quits. Losing camera tracking after winning
does not interrupt the celebration or its audio.

From PowerShell in this folder:

```powershell
.\start_game.bat
.\start_game.bat --source 1
.\start_game.bat --fullscreen
```

| Control | Action |
| --- | --- |
| Move head left / right | Steer the car |
| Enter | Confirm name / continue tutorial / start driving |
| P | Pause / resume |
| G | View automatic difficulty progression and choose a car (pauses the round) |
| Enter / Esc in settings | Apply / cancel |
| Left / Right arrows in settings | Choose car |
| R | Save the run and ask for a new driver name; reconnect after a camera error |
| B | Open full rankings (pauses the round) |
| Arrow keys in rankings | Previous / next page |
| B / Esc in rankings | Return to previous screen |
| M | Mute / unmute horns |
| F | Toggle fullscreen |
| Esc / Q | Quit |

While entering a name, letter keys are text, including R, Q, and G. Backspace
deletes a character; Enter confirms; Esc exits. Names accept 1–24 English
letters/numbers, spaces, periods, apostrophes, and hyphens.

## Drivers and rankings

Each driver gets a permanent ID such as **D0001**. Names are unique after
trimming/collapsing spaces and ignoring capitalization: `RJ Santos`,
`rj santos`, and `  RJ   Santos  ` all select the same driver. The original
display spelling is retained. The name box recognizes returning drivers and
shows their ID and personal best before starting. Every restart opens a blank
name box; enter the same name to continue improving that driver's record.

The sidebar shows the **top five drivers**. Press **B** for the full leaderboard,
including driver IDs, scores, times, and **COMPLETE** or **PARTIAL** results.
Ranking uses **highest score first, then shortest active driving time** for
equal scores. Every 10/10 completion ranks above an unfinished run, and the
fastest completion leads. A quick low-score attempt cannot outrank a higher
score. Times display milliseconds; exact score/time ties use driver ID as a
stable tie-breaker. Pauses, menus, name entry, and long tracking-loss pauses
do not add time.

Each driver keeps one personal best using that same rule. More points replace
the previous best; equal points replace it only with a shorter time. Slower,
lower-scoring, and equal results still increment the attempt count.

Records save on a win, crash, restart, or normal quit. Each run
is recorded once. Registered drivers enter the rankings after their first run.
Car changes alone do not restart a run. Driver records persist between launches
in **`data/drivers.json`**. Demo mode uses **`data/demo_drivers.json`** so practice
doesn't change the main rankings. `--database PATH` chooses another file.

The version-2 JSON file holds IDs, normalized names, personal-best score, seconds,
stage reached, attempt counts, and timestamps. Writes replace the file atomically; an unreadable
file is preserved rather than reset. Save failures appear on screen and can be
retried with Enter. Keep this folder writable and run one game instance per
database. Copy the JSON file to back up or transfer driver records.

Older version-1 files did not store scores, so their times cannot be treated as
completed missions. Driver IDs, names, and attempt counts are preserved, and
old time/difficulty results are retained under `legacy_best`. These drivers
enter the new rankings after their next scored run. Reading an old file does
not rewrite it; the upgrade is saved atomically on the next successful write.

## Rules

- EAR must stay **below 0.22 for at least 3 continuous seconds** before the
  game flags the player **ASLEEP**. Short blinks do not qualify. The driver
  monitor shows the closure duration; reopening resets it immediately.
- Once flagged asleep, a **score-based reaction countdown** begins, shrinking
  from **2.5 seconds at score 0** to **0.7 seconds at score 9**.
  **`smoke-alarm-beep.mp3` plays once when that timer starts: open your eyes
  and prepare to dodge.** An **OPEN YOUR EYES** prompt stays visible while the
  countdown is active and your eyes remain closed. The cue respects mute;
  the visual prompt is still shown when muted.
  At score 0, the first motorcycle therefore appears **5.5 seconds** after
  continuous closure begins: 3 seconds to qualify plus 2.5 seconds after the
  alarm. **Reopening does not cancel an already armed spawn timer.** Further
  closures during it do not reset or stack it. Once armed, the countdown keeps
  its duration even if another dodge increases the score or advances the stage.
- When it expires, a randomly selected motorcycle appears near your current
  horizontal position, and one of the asset horn sounds plays at random. The
  motorcycle's horizontal position then stays fixed, giving you time to evade.
- If the player is still flagged asleep at the spawn, another score-based timer
  begins with a fresh alarm cue. Otherwise, another three-second continuous
  closure is needed. The alarm and motorcycle horn can play together when
  a spawn and a new countdown happen at the same time. Pausing or losing
  tracking stops audio and freezes the countdown; resuming does not replay
  an alarm for a countdown that was already armed.
- The camera is mirrored for intuitive steering. The face rectangle's horizontal
  center and dimensions are mapped into road coordinates. Its center stays at a
  **fixed vertical position**; the car PNG fits inside this visible collision box.
  Face dimensions scale with camera distance; height is capped at 220 game pixels
  to keep the box on the road. No keyboard steering is used in camera mode.
- During a brief face dropout, the car keeps moving in the last measured
  direction and gradually slows. Prediction lasts up to **0.75 seconds** after
  the last valid observation and stays inside the road. Longer losses pause
  gameplay. When the face returns, the car gradually corrects toward its actual
  position (roughly a second to settle) instead of jumping there. The displayed
  car box and the collision box always use the same corrected position.
- Touching either side of the road or a motorcycle ends the round with a
  **YOU CRASHED** popup. Roadside collision boundaries are invisible and align
  with the road edges. They also apply while the car is coasting or recentering.
  Press **R** to enter the next driver's name; move your head toward the center
  before starting their drive.
  Each successfully avoided motorcycle
  adds one point, up to **10**. The tenth dodge completes the mission and clears
  all remaining motorcycles and spawn timers. A collision on the same update
  takes priority over a dodge. Each point increases the speed of subsequent
  motorcycles. Difficulty advances automatically from Easy to Impossible as
  the score approaches 10.
- Steering and eye validity are independent. A valid face can still steer when
  eye measurements are unavailable. During brief coasting, the road and any
  armed spawn timer continue; no face history means no prediction. Once the
  0.75-second limit expires, both freeze until the face returns.
- Unavailable eyes, tracking loss, pausing, and opening settings reset sleep
  qualification. Predicted movement and cached camera frames never add to the
  three-second closure duration. The UI shows `COASTING`, `RECENTERING`, or
  unavailable eyes when appropriate.
- Camera frames are processed locally in memory and are not recorded.

## Difficulty

Every round starts on **Easy**. The game advances through the stages below
automatically as you earn points; there is no manual difficulty selector or
`--difficulty` option. The current stage appears above the road.

| Score | Stage | Motorcycle speed at each score | Alarm-to-spawn delay at each score |
| --- | --- | --- | --- |
| 0–2 | Easy | 180, 192, 204 pixels/second | 2.5, 2.4, 2.3 seconds |
| 3–5 | Medium | 240, 262, 284 pixels/second | 2.0, 1.8, 1.6 seconds |
| 6–7 | Hard | 330, 365 pixels/second | 1.3, 1.1 seconds |
| 8–9 | Impossible | 480, 535 pixels/second | 0.9, 0.7 seconds |
| 10 | Mission complete | Gameplay stops | No further spawns |

Speeds are in game coordinates and increase at every point, including when
crossing a stage boundary. Spawning additional motorcycles at the same score
keeps their speed the same. Each bike retains its assigned speed while on
screen. Restarting resets the score, stage, and speed to Easy at 0 points.
The three-second eye-closure requirement applies at every stage. Each point
shortens the delay between the alarm's **start** and the next motorcycle spawn;
the timer does not wait for the alarm clip to finish or for the player to open
their eyes. The spawn horn replaces any remaining alarm audio. Pauses and
tracking loss freeze the countdown. Settings show the timing ranges, and the
road-watch panel shows the next reaction window before a countdown is armed.

Press **G** to view the progression and choose a car with **Left/Right arrows**,
then **Enter** to apply. **Esc** cancels and resumes the previous screen. Car
changes preserve your score and current round. Driver records save the stage
reached alongside the score and time of a personal best in `best_difficulty`.

## Face tracking

The game uses MediaPipe Face Mesh in video mode with refined eyes and lips:
**478 landmarks** (468 face landmarks plus 10 iris landmarks). The same tracked
mesh supplies face bounds and eye measurements. The camera preview displays
only the face box; the landmark dots remain hidden. There are no model names
or point-count labels in the game UI.

`tracking.py` runs the camera and mesh on a worker. `face_geometry.py` computes
EAR from six eyelid points per eye in pixel coordinates, rejects invalid eye
geometry, and supports one-eye fallback. `steering.py` estimates horizontal
velocity from fresh measurements and performs bounded coasting and smooth
correction. Normal steering uses lighter smoothing to remain responsive.

The previous custom 32-point model, its loader, and the `--model` option have
been removed from this game. No custom TFLite/ONNX file or direct TensorFlow
dependency is required; MediaPipe includes its own runtime assets. The original
files in the Model Training project are untouched.

To move the game to another laptop, copy the `SystemsFairGame` folder and install
the requirements below. No separate landmark file needs to be copied.

Options: `--ear-threshold 0.22`, `--confidence 0.5`,
`--eye-mode auto|left|right`, `--eye-width-ratio 0.60`, `--mute`.
The EAR threshold remains configurable; lighting, camera angle, and eye
geometry affect closure detection.

For a separate installation, use Python 3.11:

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe game.py
```

On Linux, use a Python 3.11 virtual environment:

```bash
python3.11 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python game.py
```

If this project already has the local Python environment installed, launch it
with `.venv/bin/python game.py`. Add `--demo` to play without a webcam.

The pinned MediaPipe version is intentional: this game uses its bundled
`solutions.face_mesh` API. Audio uses Windows `winmm` on Windows and Pygame's
audio mixer on Linux to play MP3s asynchronously. Pygame is installed by
`requirements.txt` on Linux; no external MP3 player is needed. An audio error is
shown in the interface and its details print in the console. On Linux, check
your desktop sound output and volume if horns are silent. **M** toggles mute.
Only the three designated horn files are selected for motorcycle sounds;
the victory track and `smoke-alarm-beep.mp3` are excluded from random horns.

To verify Linux MP3 loading and playback controls without speakers:

```bash
SDL_AUDIODRIVER=dummy .venv/bin/python -m unittest -v test_audio
```

Camera 0 is the default built-in webcam. If it cannot open, close other camera
apps and check Windows Settings > Privacy & security > Camera > Let desktop
apps access your camera, then press R to reconnect. If the laptop exposes its
webcam under a different index, launch with `--source 1`.

## Verify / demonstrate without a camera

```powershell
.\start_game.bat --demo
.\start_game.bat --smoke-test
& '..\Model Training\venv\Scripts\python.exe' -m unittest -v test_game test_tracking test_drivers test_audio
```

Demo mode is explicitly labeled: move the mouse (or A/D / arrow keys) to steer,
press Space to toggle simulated eye closure, and press **L** to simulate losing
and regaining the face. Move sideways before pressing L to see the car coast;
move the mouse elsewhere before pressing L again to see gradual correction.
Smoke testing opens no window or camera and writes `preview.png`. Tests cover
sustained closure, missing/invalid eyes, motion prediction, gradual recovery,
road bounds, cached frames, mesh EAR, automatic difficulty stages, car settings,
pauses, mirrored fixed-height motion, collisions and scoring.
Tests also cover the 10-point cap, victory saving, frozen completion time,
single-play victory audio, tracking loss after winning, and restart.
Alarm tests cover the three-second threshold, one cue per countdown, reopening,
mute, pause/tracking recovery, and separate alarm/horn playback.
Reaction-timing tests cover every score, stage transitions during an armed
countdown, frozen timers, restart, and the alarm-to-horn interval at score 9.
Leaderboard tests cover score-first/fastest-time ordering, personal bests,
millisecond ties, persistence, invalid results, and version-1 history upgrades.
Tutorial tests cover name-to-tutorial-to-ready navigation and preventing
timers, eye qualification, or attempts from starting before driving begins.
