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
- Detect manual brightness changes and yield (hold), with an asymmetric auto-resume
  rule (see 6.5/6.7), derived live per tick -- no new per-light state.
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
- Deadband: detection threshold (10% of full 0-255 scale, ~26 levels). A light whose
  live brightness is within D of the curve is "on track" and the Fader commands the
  next (small) step; a deviation beyond D means a human changed it and the Fader
  HOLDS. It is a manual-change detection threshold, NOT a command-suppression
  threshold (normal per-minute steps are far smaller than D and are still commanded).
- needs_reset: per-light flag meaning "snap this light back onto the schedule on
  the next evaluation."
- is_active: per-light two-tier flag. ON = the Fader is MANAGING this light this
  evening (each tick it either commands the curve step or holds); OFF = explicitly
  DISENGAGED (away, deactivate button, make-*-bright-again, end of night). A detected
  manual change must NOT turn it off (see 6.7).

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
- Per-tick decision (NO new state -- derived live from current brightness C vs target
  T, with deadband D = 10% of full scale, ~26/255). Because the per-minute fade step
  is tiny (a few levels out of 255, far smaller than D), a light the Fader is driving
  normally sits within D of the curve; only a human jump exceeds D. Each tick, for a
  managed (`_is_active == on`) light that is on:
    1. `|T - C| <= D` (on the curve):      command T -- the normal dimming step.
    2. `C < T - D` (dimmer than the curve): HOLD, command nothing. Covers a manual
       dim AND a daytime-dimmed / fade-in-handoff light at engagement. As the
       descending curve reaches C (re-entering case 1), dimming resumes automatically.
    3. `C > T + D` (brighter than the curve): HOLD, command nothing. A manual
       brighten; the Fader does not pull it back down. It stays in case 3 as the
       curve keeps dropping, until a Reset or the next evening (when T resets to the
       ceiling and C falls back within D, re-entering case 1).
  This single rule IS the entire "never-brighten + asymmetric resume" behavior. The
  asymmetry (a manual dim auto-resumes; a manual brighten holds until reset) falls out
  of cases 2 vs 3 -- case 2 self-heals into case 1 while case 3 stays put -- so NO
  yield flag or other new per-light state is required. "Yielded" simply means
  "managed and currently holding (case 2 or 3)", recomputed each tick, never stored.
  (Commands are issued every tick while on track; an implementation may skip
  re-sending a value the light is already at, e.g. while holding at the floor, to
  avoid redundant calls -- a tiny epsilon, unrelated to the 10% detection deadband.)

### 6.6 Floor-zero maps to OFF
When the resolved target is 0 (including floor == 0 at/after end time, and the
overnight branch), the Fader must turn the light OFF via `light.turn_off`, never
issue `brightness: 0`.

### 6.7 Manual override semantics (no new state) and the two-tier `is_active`
- Detection uses the same deadband as 6.5: a light within D of the curve is "on
  track"; a deviation beyond D (or the light turned off) is a human change.
  [CHANGE vs current code: today the threshold is +/-20% (0.8x/1.2x, relative);
   target is 10% of full scale.]
- No new state is added. The "yield" is NOT a stored flag -- it is the per-tick HOLD
  of cases 2/3 in 6.5, recomputed each minute from C vs T. The two booleans the
  system already has (`_is_active`, `_needs_reset`) are sufficient.
- Asymmetry (from 6.5): a manual DIM (case 2) auto-resumes when the curve catches
  down; a manual BRIGHTEN (case 3) holds until a Reset or the next evening (when T
  resets to the ceiling and the light re-enters case 1).
- No cooldown: a held light stays at the user's setting until a Reset (6.9) or the
  next window's engagement.
- A mid-window manual power-ON stays manual (the user is presumably using the light);
  it lands in case 3 (brighter than the low evening curve) and holds until a Reset.
- Two-tier `is_active` -- this is the one behavioral change vs current code:
  - `_is_active == on` => MANAGED. Each tick the engine either commands (case 1) or
    holds (cases 2/3). A detected manual change MUST NOT turn `_is_active` off: the
    per-minute driver (`fade_<light>`) only runs while `_is_active == on`, so the
    light must stay engaged for case 2 to "catch down" and auto-resume.
  - `_is_active == off` => DISENGAGED. Reserved for explicit user/away events only
    (make-*-bright-again, the deactivate button, away-mode, end of night). The
    per-minute driver correctly does nothing.
  [CHANGE vs current code: today the engine turns `_is_active` OFF on any deviation
   beyond the deadband, which permanently stops evaluation and breaks dim auto-resume
   (a held light is never re-examined). The fix is purely logical: on a deviation,
   HOLD for this tick and leave `_is_active` on -- do NOT add any new entity.]

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
   the three-way per-tick decision (6.5): command when on the curve (case 1), hold
   when dimmer (case 2) or brighter (case 3) than the curve, never brighten, and
   leave off lights off.
3. A manual BRIGHTEN holds the light (case 3) until Reset or the next window; a
   manual DIM holds (case 2) and auto-resumes when the curve catches down. Neither
   turns `_is_active` off and neither stores a flag -- both are derived each tick.
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
H. Deadband: with the light on the curve, a sub-10% reported fluctuation stays in
   case 1 (on track) and the Fader commands the normal step; a jump beyond 10%
   (|current - target| > 10%) flips the light to HOLD (case 2 if dimmer, case 3 if
   brighter) without turning `_is_active` off.

## 10. Open / configuration notes for the implementer
- Several helpers currently hold placeholder or questionable values to verify
  before relying on them: many `_start_time`/`_end_time` are the "12:34:56"
  sentinel (intended -> fall back to global); some `_max_brightness` are 0
  (e.g., hue_white_lamp_2/3, living_room_pendants), which with the never-brighten +
  floor-0 rules would keep those lights effectively off -- confirm intended.
- Keep all engine logic import-free per the python_script sandbox.
- `light.urban_outfiters` retains its existing (misspelled) entity_id; do not
  rename without migrating all helpers and automations.

## 11. Fixed bug: engagement previously forced a snap to ceiling
- Previous symptom: at `global_fader_start_time` every managed light jumped to its
  maximum brightness, overriding any value the user set during the day and
  brightening lights up (which violated never-brighten / scenario F and pre-empted
  the future fade-to-on project).
- Root cause: the `Turn On Lights Boolean` automation in `automations.yaml` turned
  ON `_needs_reset` for all 10 lights in addition to `_is_active`. With
  `needs_reset == on`, the next evaluation snapped each light to the curve target,
  which equals the ceiling at `start_time`.
- Implemented fix: that automation now turns ON only the ten `_is_active` entities
  and explicitly turns OFF the ten `_needs_reset` entities, so stale reset requests
  are cleared without forcing a snap to the curve. The unified hold rule (6.5) then
  governs start-time handoff.

## 12. Integration points & automation hooks (in `automations.yaml` / `scripts.yaml`)
The Fader is wired to the rest of the system through the following hooks. Any
re-implementation must preserve these contracts (entity names, the meaning of
`_is_active` / `_needs_reset`, and the room groupings).

- Engagement: `turn_on_lights_boolean` at `global_fader_start_time` (presence + not
  guest_mode). Must set only `_is_active` (see 7 and 11).
- Per-minute drivers: `fade_<light>` (one per managed light), `time_pattern
  minutes: /1`, gated on `<f>_is_active == on`, calling `python_script.hello_world`
  with `function_name: adjust_brightness`. Because evaluation is gated on
  `_is_active`, that flag must stay on through manual dims (see 6.7, CRITICAL).
- Reset-to-Schedule: scripts `reactivate_kitchen_dimmer`,
  `reactivate_dining_room_dimmer`, `reactivate_art_room_dimmer` (set `_needs_reset`
  + `_is_active` for their room group), `reactivate_all_dimmers` (runs all three),
  and automation `reactivate_kitchen_dimmer_auto` (button
  `input_button.reactivate_kitchen_dimmer`). Together the room groups cover all 10
  managed lights.
- The Circle dashboard (`dashboards/the-circle.yaml`) exposes
  `input_datetime.global_fader_start_time`, `input_datetime.global_fader_end_time`,
  and `input_datetime.global_lights_off_time` in its Fade Schedule card. It does
  not currently expose `input_datetime.global_morning_time`. Its reset buttons call
  `script.reactivate_kitchen_dimmer`, `script.reactivate_dining_room_dimmer`,
  `script.reactivate_art_room_dimmer`, and `script.reactivate_all_dimmers`.
- Brighten-and-disengage: scripts `make_kitchen_bright_again`,
  `make_dining_room_bright_again`, `make_art_room_bright_again` (and automation
  `make_the_kitchen_bright_again_2`). These set lights to full brightness and turn
  `_is_active` OFF -- the explicit "I want it bright now" path. Re-engagement is via
  a Reset. Keep this path consistent with the yield model in 6.7.
- Bulk deactivate/reactivate buttons: `turn_off_multiple_fader_booleans_3`
  (`input_button.deactivate_dimmer`) and `turn_on_multiple_fader_booleans_3`
  (`input_button.reactivate_dimmer`). NOTE: these currently cover only 7 of 10
  lights (see 13).
- Presence/away:
  - `turn_off_lights_when_no_one_is_home` turns lights off and `_is_active` off for
    all 10 lights -- the canonical full disengage.
  - `restore_lights_when_returning_home A/B` and the zone-arrival automations
    (`Turn on Lights When ... Comes Home`) re-engage via `_is_active` or the
    reactivate (reset) scripts.
- Schedule-boundary re-assertion: `run_scripts_after_global_lights_off_time` fires
  the reactivate (reset) scripts ~60s after lights-off, forcing overnight
  conformance. This depends on out-of-window Reset -> OFF (6.6, 6.9). NOTE:
  `run_scripts_after_global_fader_end_time` was referenced in earlier design notes
  but is not currently defined in `automations.yaml`.
- Daytime presence reset: `Light Off Art Room if Unoccupied` calls
  `reactivate_art_room_dimmer` during the day. This RELIES on out-of-window Reset
  resolving to OFF (6.9 / scenario 9.C); if that behavior changes, this breaks.

### Relationship to the sunset "Fade In" automations (handoff, not Fader)
- Automations `Fade In - L-Bar Lights`, `Fade In - L-Desk`, `Fade In - Art Room`,
  `Fade In - L-Giraffe lamp`, `Fade In - Kitchen` use a third-party easing script
  (`script.1720765151144`) to brighten lights UP around sunset. They do NOT set
  `_is_active` and are independent of the Fader engine.
- This means a script-based "fade to on" already exists (cf. the section 4 Non-Goal,
  which concerns NOT adding raising logic to the Fader engine itself).
- Handoff contract: at `global_fader_start_time` the Fader engages and, via the
  never-brighten / unified hold rule (6.5), holds each light at wherever the Fade-In
  left it until the descending curve catches down -- so the Fader never yanks these
  lights up or abruptly down at handoff.

## 13. Additional issues found in the automations (fix or confirm)
- Coverage gap: `turn_off_multiple_fader_booleans_3` and
  `turn_on_multiple_fader_booleans_3` operate on only 7 lights (missing
  `light_hue_white_lamp_2`, `light_hue_white_lamp_3`, `light_living_room_pendants`).
  Decide whether these buttons should cover all 10 managed lights.
- Likely-broken entity references:
  - `restore_lights_when_returning_home B` ("Reactivate Dimmers on Arrival") triggers
    and conditions reference `person.name1` / `person.name2`, which appear to be
    placeholders rather than the real `person.alex_vardakostas` /
    `person.anna_tong`. This automation likely never fires as intended.
  - `restore_lights_when_returning_home A`'s brightness template reads
    `state_attr('input_number.light_<person>_max_brightness', 'state')`, which is
    incorrect (input_number value is the state, not a `state` attribute; and the
    entity is keyed by person, not light). It always falls back to 255.
- These are independent of the core engine logic but touch the same `_is_active` /
  brightness contracts, so confirm intended behavior before relying on them.

## 14. Implementation and live validation notes
- Implemented on 2026-06-06 in `python_scripts/hello_world.py` and
  `automations.yaml`: the engine now returns explicit command/hold/off decisions,
  manual deviations HOLD without turning `_is_active` off, and target `0` maps to
  `light.turn_off`.
- Live validation covered the critical acceptance paths:
  - Manual brighten on `light.under_cabinet_lights` held brightness and left
    `_is_active` on.
  - In-window Reset on `light.under_cabinet_lights` snapped to the curve and cleared
    `_needs_reset`.
  - Manual dim on `light.under_cabinet_lights` held below the curve, then resumed
    when the synthetic curve caught down.
  - Out-of-window Reset on `light.giraffe_lamp` turned the light off.
  - Temporary floor-zero on `light.giraffe_lamp` turned the light off cleanly, then
    the floor was restored to `1`.
  - Synthetic start-time handoff on a dimmed `light.giraffe_lamp` did not brighten
    the light and left `_is_active` on / `_needs_reset` off.
