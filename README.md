# Night Shift — Systems Fair

A Windows laptop desktop game: use the built-in webcam and move your head
sideways to dodge motorcycles. Run the Python game directly on the laptop.
Uses the supplied car/motorcycle PNGs and three MP3 horns in `assets/`.

## Play

Double-click **start_game.bat**, type a driver name, and press **Enter** to
confirm it. Face your camera and press **Enter** again to start driving.
The launcher uses the existing `../Model Training/venv` environment. The first
camera startup may take a few seconds while face tracking loads.

From PowerShell in this folder:

```powershell
.\start_game.bat
.\start_game.bat --source 1
.\start_game.bat --fullscreen
.\start_game.bat --difficulty hard
```

| Control | Action |
| --- | --- |
| Move head left / right | Steer the car |
| Enter | Start |
| P | Pause / resume |
| G | Open difficulty and car settings (pauses the round) |
| 1 / 2 / 3 / 4 in settings | Select Easy / Medium / Hard / Impossible |
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

The sidebar shows the **five longest drives**. Press **B** to see all drivers,
their IDs, best times, and the difficulty of that best run. The ranking uses
each driver's longest active driving time across all difficulties. Pauses,
menus, name entry, and long tracking-loss pauses do not add time. Equal best
times use driver ID as the stable tie-breaker. A slower or equal run never
replaces a personal best; it still increments that driver's attempt count.

Records save on a crash, restart, difficulty change, or normal quit. Each run
is recorded once. Registered drivers enter the rankings after their first run.
Car changes alone do not restart a run. Driver records persist between launches
in **`data/drivers.json`**. Demo mode uses **`data/demo_drivers.json`** so practice
doesn't change the main rankings. `--database PATH` chooses another file.

The JSON file holds IDs, normalized names, personal-best seconds and difficulty,
attempt counts, and timestamps. Writes replace the file atomically; an unreadable
file is preserved rather than reset. Save failures appear on screen and can be
retried with Enter. Keep this folder writable and run one game instance per
database. Copy the JSON file to back up or transfer driver records.

## Rules

- EAR must stay **below 0.22 for at least 3 continuous seconds** before the
  game flags the player **ASLEEP**. Short blinks do not qualify. The driver
  monitor shows the closure duration; reopening resets it immediately.
- Once flagged asleep, a uniformly random **3–5 second spawn timer** begins.
  The first motorcycle therefore appears 6–8 seconds after continuous closure
  begins. **Reopening does not cancel an already armed spawn timer.** Further
  closures during it do not reset or stack it.
- When it expires, a randomly selected motorcycle appears near your current
  horizontal position, and one of the asset horn sounds plays at random. The
  motorcycle's horizontal position then stays fixed, giving you time to evade.
- If the player is still flagged asleep at the spawn, another random timer
  begins. Otherwise, another three-second continuous closure is needed.
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
  adds one point. Each successive motorcycle spawns faster than the last,
  independently of score. Difficulty controls starting speed and the increase.
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

Press **G**, select **1–4** for difficulty and **Left/Right arrows** for the car,
then **Enter** to apply. Car selection is available only here. Medium is the default.
**Esc** cancels and resumes the previous screen. Applying a different level
saves the current run and asks for a driver name for a fresh round. Restart
keeps the selected level and car and resets motorcycle speeds.

| Level | First motorcycle speed | Increase per new motorcycle |
| --- | --- | --- |
| Easy | 180 pixels/second | +12 pixels/second |
| Medium | 240 pixels/second | +22 pixels/second |
| Hard | 330 pixels/second | +35 pixels/second |
| Impossible | 480 pixels/second | +55 pixels/second |

Speeds are in game coordinates and increase on every spawn without the old
speed cap. Each bike retains its own speed while on screen. The three-second
sleep requirement and random 3–5 second countdown apply at every difficulty.

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

The pinned MediaPipe version is intentional: this game uses its bundled
`solutions.face_mesh` API. Audio uses Windows `winmm`
to play MP3s asynchronously. An audio error is shown in the interface and its
details print in the console.

Camera 0 is the default built-in webcam. If it cannot open, close other camera
apps and check Windows Settings > Privacy & security > Camera > Let desktop
apps access your camera, then press R to reconnect. If the laptop exposes its
webcam under a different index, launch with `--source 1`.

## Verify / demonstrate without a camera

```powershell
.\start_game.bat --demo
.\start_game.bat --smoke-test
& '..\Model Training\venv\Scripts\python.exe' -m unittest -v test_game test_tracking test_drivers
```

Demo mode is explicitly labeled: move the mouse (or A/D / arrow keys) to steer,
press Space to toggle simulated eye closure, and press **L** to simulate losing
and regaining the face. Move sideways before pressing L to see the car coast;
move the mouse elsewhere before pressing L again to see gradual correction.
Smoke testing opens no window or camera and writes `preview.png`. Tests cover
sustained closure, missing/invalid eyes, motion prediction, gradual recovery,
road bounds, cached frames, mesh EAR, all four speed progressions, settings,
pauses, mirrored fixed-height motion, collisions and scoring.
