# PRD: Evening Light Fader ("The Fader")

## 1. Summary
The Fader is a Home Assistant automation system that gradually dims a set of
household lights from a configured maximum down to a configured minimum across a
scheduled evening window (e.g., 21:30 -> 23:40), eases them to a floor until a
"lights off" time, and turns them off overnight until morning. Its defining
requirement is robust coexistence with manual human control: people may turn lights
on/off or change brightness at any time -- including during the day when the Fader
is dormant -- and the Fader must never fight them. A per-room "Reset to Schedule"
control lets users hand a light (or room) back to the Fader on demand.

## 2. Where this lives (current implementation = source of truth)
- Engine: `homeassistant-config/python_scripts/hello_world.py`. It is a Home
  Assistant `python_script`, invoked via the `python_script.hello_world` service
  with `data: { function_name: "adjust_brightness", entity_id, current_time,
  sunset_time }`. A `function_name` dispatcher is at the bottom of the file.
- Per-light drivers: automations named `fade_<light>` (in `automations.yaml`) fire
  on `platform: time_pattern, minutes: /1`, gated by a condition that the light's
  `is_active` boolean is `on`. Each passes `current_time` (now, `%H:%M:%S`) and
  `sunset_time` (sun.sun next_setting) to the engine.
- Engagement: automation `Turn On Lights Boolean` fires at
  `input_datetime.global_fader_start_time`. Conditions: at least one resident is
  home AND `input_boolean.guest_mode` is off. Action: turns ON `_is_active` for all
  managed lights and ensures `_needs_reset` is OFF. It must NOT set `_needs_reset`.
  [CHANGE vs current code: today it also turns ON `_needs_reset` for every light,
   which forces a snap to the ceiling at start_time and overrides any daytime
   user dimming -- this is a bug and contradicts never-brighten / scenario F.
   See section 11.]
- Reset controls: scripts `reactivate_kitchen_dimmer`, `reactivate_dining_room_dimmer`,
  `reactivate_art_room_dimmer`, and `reactivate_all_dimmers` (in `scripts.yaml`),
  surfaced as buttons on the `the-circle` dashboard (`dashboards/the-circle.yaml`).
- Sandbox constraints: HA `python_script` runs in a restricted interpreter. NO
  `import` statements are allowed. Only `hass`, `data`, and `logger` globals are
  available. All time math must be done with string parsing / arithmetic (no
  `datetime` import). Keep all logic within these constraints.
- Brightness scale: Home Assistant `light` brightness and all `*_max_brightness` /
  `*_min_brightness` helpers are on the 0-255 integer scale. Do NOT rescale by 2.55.

### Stale code to ignore / remove
- `homeassistant-config/custom_components/lightprofilerestorer/` is an older,
  unused OOP reimplementation (services `start_dimming`, `deactivate_fader`, etc.).
  It is NOT wired into the live system. Treat `hello_world.py` as canonical; the
  component may be deleted.
- The `adaptive_lighting` custom component has been deleted; do not reintroduce a
  dependency on it. (If a config entry remains on the live instance, it should be
  removed via Settings -> Devices & Services.)

## 3. Goals
- Smoothly dim each managed light from its configured max to its configured min
  across its fade window, using cubic easing.
- Treat human on/off and brightness actions as authoritative; never fight them.
- Detect manual brightness changes and yield (flag the light "needs reset"),
  with an asymmetric auto-resume rule (see 6.7).
- Provide per-light / per-room "Reset to Schedule" that re-engages the Fader.
- Be self-healing: correct behavior after HA restarts, missed ticks, or mid-window
  changes, deriving all decisions from persisted helpers + current time + the
  light's live state (no in-memory state).

## 4. Non-Goals
- Turning lights ON autonomously (the Fader only adjusts already-on lights), and
  never brightening a light up toward its ceiling autonomously.
- Raising/brightening lights up from a lower level or from off. The Fader only ever
  holds or dims. Bringing lights UP automatically (e.g., a sunrise "fade-to-on") is
  a separate FUTURE project and must not be implemented here. The only sanctioned
  brightening is an explicit user Reset that snaps a light onto the curve.
- Color or color-temperature control (brightness only).
- Replacing circadian/adaptive lighting.
- Owning the schedule UI beyond the existing dashboard helpers.

## 5. Glossary
- Ceiling / max: configured per-light maximum brightness (top of the curve). The
  Fader never drives a light UP to reach it.
- Floor / min: configured per-light minimum brightness (bottom of the curve).
  A floor of 0 means "off" at the bottom (see 6.6).
- Window: the per-light fade interval [start_time, end_time]; may cross midnight.
- Curve: cubic-eased interpolation from ceiling to floor across the window.
- Deadband: tolerance (10% of full 0-255 scale, ~26 levels) used to (a) detect
  manual changes and (b) suppress no-op commands.
- needs_reset: per-light flag meaning "snap this light back onto the schedule on
  the next evaluation."
- is_active: per-light flag meaning "the Fader is currently driving this light."

## 6. Functional Requirements

### 6.1 Managed lights
The Fader manages exactly these 10 lights (HA `entity_id` -> helper stem, where the
stem is `entity_id` with "." replaced by "_"):
- light.kitchen_desk_lamp      -> light_kitchen_desk_lamp
- light.under_cabinet_lights   -> light_under_cabinet_lights
- light.bookshelf_lights       -> light_bookshelf_lights
- light.dimmable_light_1       -> light_dimmable_light_1
- light.urban_outfiters        -> light_urban_outfiters   (note: existing spelling)
- light.giraffe_lamp           -> light_giraffe_lamp
- light.hue_white_lamp_1       -> light_hue_white_lamp_1
- light.hue_white_lamp_2       -> light_hue_white_lamp_2
- light.hue_white_lamp_3       -> light_hue_white_lamp_3
- light.living_room_pendants   -> light_living_room_pendants

### 6.2 Per-light helper entities (naming convention)
For stem `<f>`:
- input_boolean.<f>_is_active     - Fader is driving this light.
- input_boolean.<f>_needs_reset   - snap onto schedule next evaluation.
- input_number.<f>_max_brightness - ceiling (0-255).
- input_number.<f>_min_brightness - floor (0-255).
- input_datetime.<f>_start_time   - window start; sentinel "12:34:56" => use global.
- input_datetime.<f>_end_time     - window end;   sentinel "12:34:56" => use global.

### 6.3 Global helper entities
- input_datetime.global_fader_start_time  (default 21:30:00) - window start fallback.
- input_datetime.global_fader_end_time    (default 23:40:00) - window end fallback.
- input_datetime.global_lights_off_time   (default 01:05:00) - hard "go dark" time.
- input_datetime.global_morning_time      (default 05:00:00) - end of overnight-off.
- input_boolean.fader_booster_is_active   - boost mode (see 6.8).
- input_boolean.fader_retarder_is_active  - reserved; currently unused. Preserve.
- input_boolean.guest_mode                - when on, engagement automation is skipped.

### 6.4 Window resolution and time model
- Resolve start/end from the per-light `_start_time`/`_end_time`. If the value is
  the sentinel "12:34:56", fall back to the corresponding `global_fader_*` time.
- Convert all times to minutes-since-midnight for comparison.
- Wrap-around handling (windows/anchors crossing midnight): if a later anchor's
  minutes are less than `global_morning_time`'s minutes, add 24*60 to it before
  comparing (end_time, current_time, global_lights_off_time as needed), and treat
  global_morning_time as next-day. The math must remain correct for windows that
  start before midnight and end after it (e.g., 23:40 -> 01:05). DST: rely on HA's
  localized `now()` passed in as `current_time`; do not attempt UTC conversion in
  the sandbox.

### 6.5 Brightness curve and evaluation
For each managed light, every minute (and immediately on reset), compute a target:
- If `start <= now <= end` (in window):
    progress = (now - start) / (end - start)
    eased    = cubic_ease_in_out(progress)        # 4t^3 for t<0.5; 1-((-2t+2)^3)/2 else
    target   = round(max - (max - min) * eased)    # 0-255
- If `end < now <= global_lights_off` (post-fade, pre-bedtime): target = min (floor).
- If `global_lights_off < now < global_morning` (overnight): target = 0 (off),
  unless booster is on (see 6.8).
- Otherwise (daytime / outside all anchors): the Fader is passive -- it keeps the
  light's current brightness (issues effectively no change), EXCEPT a reset request
  outside the window resolves to OFF (see 6.9, scenario 9.C).
- Invariant: if `max <= min`, hold (no fade, never brighten).
- Never-brighten / unified hold rule: for a managed light with current brightness C
  and curve target T, while `T >= C` the Fader HOLDS (issues no command). This
  single rule implements both "never-brighten" and "auto-resume after a manual dim":
  the Fader simply waits until the descending curve reaches C (i.e. `T < C`), then
  dims. A light that was manually dimmed during the day therefore fades naturally
  instead of jumping up at window open, and a mid-window manual dim needs no special
  flag.

### 6.6 Floor-zero maps to OFF
When the resolved target is 0 (including floor == 0 at/after end time, and the
overnight branch), the Fader must turn the light OFF via `light.turn_off`, never
issue `brightness: 0`.

### 6.7 Manual override (needs_reset) and the deadband
- Detection (the deadband): on each evaluation, compare the light's actual current
  brightness to the Fader's expected value (the curve target / last commanded).
  If they differ by more than the deadband (10% of full scale, ~26 of 255) -- or
  the light has been turned off -- a human changed it.
  [CHANGE vs current code: today the threshold is +/-20% (0.8x/1.2x, relative).
   Target is 10% of full scale.]
- Asymmetry (which falls out of 6.5):
  - Manual DIM below the curve: needs no explicit yield flag. The unified hold rule
    (6.5) holds the light and auto-resumes dimming once the descending curve reaches
    the user's level.
  - Manual BRIGHTEN above the curve: this is the ONLY case requiring an explicit
    yield-until-reset state. When a change beyond the deadband leaves `C > T`, flag
    the light yielded so the Fader does not dim it back down. It stays yielded until
    an explicit Reset (or the next window's engagement, which clears the flag).
- No cooldown: once yielded, the light stays at the user's setting until a Reset
  (6.9) or the next window's engagement.
- A mid-window manual power-ON stays manual (the user is presumably using the
  light); the Fader does not seize it until the next window or a Reset.

### 6.8 Booster (existing behavior to preserve)
- When `fader_booster_is_active` is on: multiply the computed brightness by 1.2
  (clamped to 255) and raise an effective floor to at least 20 when min > 0. In the
  overnight branch, booster yields `min/2` instead of 0. (`fader_retarder_is_active`
  exists but is currently unused; leave the hook in place.)

### 6.9 Reset to Schedule
- Scope: a single light or a predefined room group only. There is NO house-wide
  per-light "all" beyond the explicit "Reset All Rooms" button (which simply runs
  the three room scripts).
- Mechanism (per the existing scripts): turn ON the group's `_needs_reset` and
  `_is_active` booleans, then `automation.trigger` the corresponding `fade_<light>`
  automations so evaluation happens immediately rather than on the next minute tick.
- On evaluation with `needs_reset == on`: clear `needs_reset`, ensure `is_active`,
  and apply `desired_state(now)`:
    - in window      -> ON at the curve target (snaps onto curve; this MAY raise the
      light because it is an explicit user request).
    - out of window  -> OFF.
- Room groups (from existing scripts; preserve membership):
  - Kitchen:     under_cabinet_lights, dimmable_light_1, hue_white_lamp_1/2/3
  - Art Room:    bookshelf_lights, urban_outfiters
  - Dining Room: giraffe_lamp, kitchen_desk_lamp, living_room_pendants
  - Reset All:   the union of the three.

### 6.10 State / restart safety
All decisions derive from helper states + `current_time` + the light's live
brightness. There is no in-memory source of truth, so a mid-fade HA restart
recovers automatically (the next minute tick recomputes the absolute target).

## 7. Engagement / disengagement lifecycle
1. At `global_fader_start_time`, if a resident is home and guest_mode is off, the
   engagement automation turns ON `_is_active` for all managed lights and clears
   `_needs_reset` (sets it OFF). It does NOT force a snap to the curve.
2. Each minute, `fade_<light>` evaluates lights whose `_is_active` is on, applying
   the unified hold rule (6.5): dim when `T < C`, hold when `T >= C`, never brighten,
   and leave off lights off.
3. A manual BRIGHTEN above the curve yields the light (6.7) until Reset or the next
   window. A manual DIM needs no special handling -- the hold rule covers it.
4. Reset (per-light/room) sets `_needs_reset`; the next evaluation clears it and
   snaps the light to `desired_state(now)` (in-window -> curve target, which MAY
   raise the light because it is an explicit user request; out-of-window -> OFF).
5. After `global_lights_off_time`, lights go OFF (overnight). After
   `global_morning_time`, the Fader is passive again until the next start.

## 8. Logging & error handling
- Log per-evaluation detail at debug/info: resolved start/end, max/min, target,
  deadband decision, and override/needs_reset status.
- Wrap the final `light.turn_on`/`light.turn_off` in defensive handling; on a
  non-numeric brightness, log an error including entity_id and inputs, and return
  without commanding the light. Never raise out of the script.
- Remove any leftover debug overrides (e.g., a hardcoded `brightness = 1`).

## 9. Acceptance scenarios (must all pass)
A. In-window manual BRIGHTEN: at 22:00 (curve ~76%) user sets light to 100%.
   Fader yields and does not pull it down. User taps the room Reset; light snaps to
   the curve value for "now" (not back to 100%).
B. In-window manual DIM below curve: user sets a level below the curve. Fader holds;
   when the descending curve reaches that level, Fader resumes dimming automatically.
C. Out-of-window Reset (daytime): user taps Reset while outside the window; the
   light turns OFF (Fader is not active at that time).
D. Restart mid-window: HA restarts at 22:30; within one minute the light is at the
   correct curve value with no manual intervention.
E. Light OFF at window open: Fader does not turn it on.
F. Light dimmer than curve at window open (dimmed earlier in the day): Fader does
   NOT brighten it; it holds until the curve catches down, then dims. (Requires the
   engagement fix in section 11 -- engagement must not set `_needs_reset`.)
G. Floor == 0: at/after end_time the light turns OFF (not brightness 0).
H. Deadband: with the light on the curve, a sub-10% reported fluctuation does not
   trigger yield, and the Fader only issues a command when |target - current| > 10%.

## 10. Open / configuration notes for the implementer
- Several helpers currently hold placeholder or questionable values to verify
  before relying on them: many `_start_time`/`_end_time` are the "12:34:56"
  sentinel (intended -> fall back to global); some `_max_brightness` are 0
  (e.g., hue_white_lamp_2/3, living_room_pendants), which with the never-brighten +
  floor-0 rules would keep those lights effectively off -- confirm intended.
- Keep all engine logic import-free per the python_script sandbox.
- `light.urban_outfiters` retains its existing (misspelled) entity_id; do not
  rename without migrating all helpers and automations.

## 11. Known bug to fix: engagement forces a snap to ceiling
- Symptom: at `global_fader_start_time` every managed light jumps to its maximum
  brightness, overriding any value the user set during the day and brightening
  lights up (which violates never-brighten / scenario F and pre-empts the future
  fade-to-on project).
- Root cause: the `Turn On Lights Boolean` automation in `automations.yaml` turns
  ON `_needs_reset` for all 10 lights in addition to `_is_active`. With
  `needs_reset == on`, the next evaluation snaps each light to the curve target,
  which equals the ceiling at `start_time`.
- Fix: in that automation's `input_boolean.turn_on` action, remove the ten
  `_needs_reset` entities (and ideally `input_boolean.turn_off` them instead, so any
  stale yield from the previous evening is cleared). Engagement must set only
  `_is_active`; the unified hold rule (6.5) then governs the rest.
