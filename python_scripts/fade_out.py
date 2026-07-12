BRIGHTNESS_REPORT_TOLERANCE = 1
FADER_UPDATE_INTERVAL_MINUTES = 1
EXPECTED_TARGET_LOOKBACK_TICKS = 2
FADE_IN_START_GRACE_MINUTES = 2
MINUTES_PER_DAY = 24 * 60
SENTINEL_TIME = "12:34:56"
PEAK_REDUCTION_FACTOR = 2.0 / 3.0
FADER_COLOR_TEMPERATURE_ENTITY = "input_number.fader_hue_color_temperature_kelvin"
COLOR_TEMPERATURE_HELPER_SUFFIX = "_requires_fader_color_temperature"


def get_state(entity, default=None):
    state = hass.states.get(entity)
    if state is None:
        return default
    if state.state in ("unknown", "unavailable", None):
        return default
    return state.state


def fader_is_enabled():
    return get_state("input_boolean.fader_enabled", "on") == "on"


def time_to_minutes(time_str):
    h, m, s = time_str.split(":")
    return int(h) * 60 + int(m) + int(s) / 60


def minute_aligned_time(time_str):
    h, m, s = time_str.split(":")
    return "{:02d}:{:02d}:00".format(int(h), int(m))


def shift_time_minutes(time_str, delta_minutes):
    h, m, s = time_str.split(":")
    total_seconds = int(h) * 60 * 60 + int(m) * 60 + int(float(s))
    total_seconds = (total_seconds + delta_minutes * 60) % (MINUTES_PER_DAY * 60)
    shifted_hours = total_seconds // (60 * 60)
    shifted_minutes = (total_seconds % (60 * 60)) // 60
    shifted_seconds = total_seconds % 60
    return "{:02d}:{:02d}:{:02d}".format(shifted_hours, shifted_minutes, shifted_seconds)


def safe_int(value, default=None):
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default


def clamp_brightness(value):
    value = int(value + 0.5)
    if value < 0:
        return 0
    if value > 255:
        return 255
    return value


def get_fader_color_temperature_kelvin():
    kelvin = safe_int(get_state(FADER_COLOR_TEMPERATURE_ENTITY), None)
    if kelvin is None or kelvin <= 0:
        return None
    return kelvin


def helper_stem(entity_id):
    return entity_id.replace(".", "_")


def entity_id_from_helper_stem(stem):
    if "_" not in stem:
        return stem
    domain, object_id = stem.split("_", 1)
    return domain + "." + object_id


def color_temperature_helper_entity(entity_id):
    return "input_boolean." + helper_stem(entity_id) + COLOR_TEMPERATURE_HELPER_SUFFIX


def requires_fader_color_temperature(entity_id):
    return get_state(color_temperature_helper_entity(entity_id), "off") == "on"


def get_current_brightness(light_state):
    if light_state is None or light_state.state != "on":
        return 0

    brightness = light_state.attributes.get("brightness")
    current_brightness = safe_int(brightness, 0)
    if current_brightness is None:
        return 0
    return max(0, min(255, current_brightness))


def cubic_ease_in_out(t):
    if t < 0.5:
        return 4 * t * t * t
    return 1 - (-2 * t + 2) ** 3 / 2


def normalize_anchor(minutes, morning_minutes):
    if minutes < morning_minutes:
        return minutes + MINUTES_PER_DAY
    return minutes


def resolve_timeline(current_time, fade_in_start_time, start_time, end_time):
    global_lights_off_time = get_state("input_datetime.global_lights_off_time")
    global_morning_time = get_state("input_datetime.global_morning_time")

    current_minutes = time_to_minutes(current_time)
    fade_in_start_minutes = time_to_minutes(fade_in_start_time)
    start_minutes = time_to_minutes(start_time)
    end_minutes = time_to_minutes(end_time)
    lights_off_minutes = time_to_minutes(global_lights_off_time)
    morning_minutes = time_to_minutes(global_morning_time)

    current_minutes = normalize_anchor(current_minutes, morning_minutes)
    fade_in_start_minutes = normalize_anchor(fade_in_start_minutes, morning_minutes)
    start_minutes = normalize_anchor(start_minutes, morning_minutes)
    end_minutes = normalize_anchor(end_minutes, morning_minutes)
    lights_off_minutes = normalize_anchor(lights_off_minutes, morning_minutes)
    morning_minutes = morning_minutes + MINUTES_PER_DAY

    if end_minutes < start_minutes:
        end_minutes += MINUTES_PER_DAY
    if lights_off_minutes < end_minutes:
        lights_off_minutes += MINUTES_PER_DAY
    if morning_minutes < lights_off_minutes:
        morning_minutes += MINUTES_PER_DAY

    return current_minutes, fade_in_start_minutes, start_minutes, end_minutes, lights_off_minutes, morning_minutes


def cap_target(target, max_brightness):
    return min(clamp_brightness(target), max_brightness)


def boosted_target(target, min_brightness, booster_is_active, max_brightness):
    if booster_is_active:
        effective_min = min_brightness
        if effective_min > 0:
            effective_min = max(effective_min, 20)
        boosted = target * 1.2
        if effective_min > 0 and boosted < effective_min:
            boosted = effective_min
        return cap_target(boosted, max_brightness)
    return cap_target(target, max_brightness)


def effective_max_brightness(max_brightness):
    if get_state("input_boolean.fader_peak_reducer_is_active", "off") == "on":
        return clamp_brightness(max_brightness * PEAK_REDUCTION_FACTOR)
    return max_brightness


def calculate_target(current_time, fade_in_start_time, start_time, end_time, max_brightness, min_brightness):
    current_minutes, fade_in_start_minutes, start_minutes, end_minutes, lights_off_minutes, morning_minutes = resolve_timeline(current_time, fade_in_start_time, start_time, end_time)

    booster_is_active = get_state("input_boolean.fader_booster_is_active", "off") == "on"
    # Hook retained for the existing helper; the retarder is intentionally unused.
    fader_retarder_is_active = get_state("input_boolean.fader_retarder_is_active", "off") == "on"
    max_brightness = effective_max_brightness(max_brightness)

    effective_min = min_brightness
    if booster_is_active and effective_min > 0:
        effective_min = max(effective_min, 20)

    if fade_in_start_minutes < start_minutes and fade_in_start_minutes <= current_minutes < start_minutes:
        if max_brightness <= 0:
            return {"period": "fade_in", "target": 0, "reason": "max_zero"}

        total_minutes = start_minutes - fade_in_start_minutes
        if total_minutes <= 0:
            return {"period": "fade_in", "target": None, "reason": "invalid_fade_in_window"}

        progress = (current_minutes - fade_in_start_minutes) / total_minutes
        eased = cubic_ease_in_out(progress)
        target = clamp_brightness(max_brightness * eased)
        if target <= 0:
            target = 1
        return {"period": "fade_in", "target": target, "reason": "fade_in_curve"}

    if start_minutes <= current_minutes <= end_minutes:
        if max_brightness <= min_brightness:
            if min_brightness == 0:
                return {"period": "window", "target": 0, "reason": "max_not_above_min_zero"}
            return {"period": "window", "target": None, "reason": "max_not_above_min"}

        total_minutes = end_minutes - start_minutes
        if total_minutes <= 0:
            return {"period": "window", "target": None, "reason": "invalid_window"}

        progress = (current_minutes - start_minutes) / total_minutes
        eased = cubic_ease_in_out(progress)
        target = max_brightness - ((max_brightness - effective_min) * eased)
        return {"period": "window", "target": boosted_target(target, effective_min, booster_is_active, max_brightness), "reason": "curve"}

    if end_minutes < current_minutes <= lights_off_minutes:
        target = effective_min
        return {"period": "post_fade", "target": boosted_target(target, effective_min, booster_is_active, max_brightness), "reason": "floor"}

    if lights_off_minutes < current_minutes < morning_minutes:
        if booster_is_active and effective_min > 0:
            return {"period": "overnight", "target": cap_target(effective_min / 2, max_brightness), "reason": "overnight_boost"}
        return {"period": "overnight", "target": 0, "reason": "overnight_off"}

    return {"period": "daytime", "target": None, "reason": "passive"}


def should_passive_after_bedtime(target_info, needs_reset):
    if needs_reset == "on":
        return False
    return target_info["period"] in ("post_fade", "overnight")


def passive_after_bedtime_target():
    return {"period": "post_bedtime", "target": None, "reason": "post_bedtime_passive"}


def brightness_is_on_track(current_brightness, expected_targets):
    if len(expected_targets) == 0:
        return False

    current_target = expected_targets[0]
    previous_target = current_target
    if len(expected_targets) > 1:
        previous_target = expected_targets[1]

    lower_bound = min(current_target, previous_target) - BRIGHTNESS_REPORT_TOLERANCE
    upper_bound = max(current_target, previous_target) + BRIGHTNESS_REPORT_TOLERANCE
    if lower_bound <= current_brightness <= upper_bound:
        return True

    for expected_target in expected_targets[2:]:
        if expected_target - BRIGHTNESS_REPORT_TOLERANCE <= current_brightness <= expected_target + BRIGHTNESS_REPORT_TOLERANCE:
            return True
    return False


def decide_action(entity_id, light_state, current_brightness, target_info, expected_targets, needs_reset):
    target = target_info["target"]
    period = target_info["period"]

    if needs_reset == "on":
        if period in ("fade_in", "window", "post_fade") and target is not None:
            if target <= 0:
                return {"action": "turn_off", "brightness": 0, "reason": "reset_target_zero"}
            return {"action": "turn_on", "brightness": target, "reason": "reset_to_schedule"}
        return {"action": "turn_off", "brightness": 0, "reason": "reset_outside_window"}

    if target is None:
        return {"action": "hold", "brightness": current_brightness, "reason": target_info["reason"]}

    if light_state is None or light_state.state != "on":
        return {"action": "hold", "brightness": current_brightness, "reason": "light_off"}

    if target <= 0:
        if brightness_is_on_track(current_brightness, expected_targets):
            return {"action": "turn_off", "brightness": 0, "reason": target_info["reason"]}
        return {"action": "hold", "brightness": current_brightness, "reason": "manual_bright_hold"}

    if period == "fade_in":
        if current_brightness > target:
            return {"action": "hold", "brightness": current_brightness, "reason": "manual_bright_hold"}
        if brightness_is_on_track(current_brightness, expected_targets):
            return {"action": "turn_on", "brightness": target, "reason": "on_fade_in_curve"}
        return {"action": "hold", "brightness": current_brightness, "reason": "manual_dim_hold"}

    if brightness_is_on_track(current_brightness, expected_targets):
        return {"action": "turn_on", "brightness": target, "reason": "on_curve"}

    if current_brightness < target:
        return {"action": "hold", "brightness": current_brightness, "reason": "manual_dim_hold"}

    return {"action": "hold", "brightness": current_brightness, "reason": "manual_bright_hold"}


def expected_scheduled_targets(current_time, fader_inputs, current_target_info):
    expected_targets = []
    current_target = current_target_info["target"]
    if current_target is not None:
        expected_targets.append(current_target)

    for ticks_ago in range(1, EXPECTED_TARGET_LOOKBACK_TICKS + 1):
        previous_time = shift_time_minutes(current_time, -FADER_UPDATE_INTERVAL_MINUTES * ticks_ago)
        previous_target_info = calculate_target(previous_time, fader_inputs["fade_in_start_time"], fader_inputs["start_time"], fader_inputs["end_time"], fader_inputs["max_brightness"], fader_inputs["min_brightness"])
        previous_target = previous_target_info["target"]
        if previous_target is not None:
            expected_targets.append(previous_target)

    return expected_targets


def get_fader_inputs(entity_id, current_time):
    formated_entity_id = entity_id.replace(".", "_")
    input_boolean_entity = "input_boolean." + formated_entity_id + "_is_active"
    needs_reset_entity = "input_boolean." + formated_entity_id + "_needs_reset"

    fade_in_start_time_entity = "input_datetime." + formated_entity_id + "_fade_in_start_time"
    fade_in_start_time = get_state(fade_in_start_time_entity)
    if fade_in_start_time is None or fade_in_start_time == SENTINEL_TIME:
        fade_in_start_time = get_state("input_datetime.global_fade_in_start_time")

    start_time_entity = "input_datetime." + formated_entity_id + "_start_time"
    start_time = get_state(start_time_entity)
    if start_time == SENTINEL_TIME:
        start_time = get_state("input_datetime.global_fader_start_time")

    end_time_entity = "input_datetime." + formated_entity_id + "_end_time"
    end_time = get_state(end_time_entity)
    if end_time == SENTINEL_TIME:
        end_time = get_state("input_datetime.global_fader_end_time")

    min_brightness_entity = "input_number." + formated_entity_id + "_min_brightness"
    max_brightness_entity = "input_number." + formated_entity_id + "_max_brightness"
    min_brightness = safe_int(get_state(min_brightness_entity), None)
    max_brightness = safe_int(get_state(max_brightness_entity), None)

    if fade_in_start_time is None or start_time is None or end_time is None or min_brightness is None or max_brightness is None:
        logger.error("Missing fader inputs for {}. current_time={}, fade_in_start={}, start={}, end={}, max={}, min={}".format(entity_id, current_time, fade_in_start_time, start_time, end_time, max_brightness, min_brightness))
        return None

    return {
        "formated_entity_id": formated_entity_id,
        "input_boolean_entity": input_boolean_entity,
        "needs_reset_entity": needs_reset_entity,
        "fade_in_start_time": fade_in_start_time,
        "start_time": start_time,
        "end_time": end_time,
        "min_brightness": min_brightness,
        "max_brightness": max_brightness,
    }


def apply_decision(entity_id, decision, context):
    if decision["action"] == "hold":
        return

    try:
        if decision["action"] == "turn_off":
            hass.services.call("light", "turn_off", {"entity_id": entity_id})
        elif decision["action"] == "turn_on":
            brightness = safe_int(decision["brightness"], None)
            if brightness is None:
                logger.error("Cannot convert brightness to int. Entity ID {}, context {}, decision {}".format(entity_id, context, decision))
                return
            service_data = {"entity_id": entity_id, "brightness": brightness}
            kelvin = get_fader_color_temperature_kelvin()
            if requires_fader_color_temperature(entity_id) and kelvin is not None:
                service_data["color_temp_kelvin"] = kelvin
            hass.services.call("light", "turn_on", service_data)
    except Exception as e:
        logger.error("Fader service call failed for {} with decision {}. Error: {}".format(entity_id, decision, str(e)))


def warm_configured_color_temperature():
    if not fader_is_enabled():
        return

    kelvin = get_fader_color_temperature_kelvin()
    if kelvin is None:
        logger.info("Fader color temperature skipped; {} is not set.".format(FADER_COLOR_TEMPERATURE_ENTITY))
        return

    for helper_state in hass.states.all():
        helper_entity_id = helper_state.entity_id
        if not helper_entity_id.startswith("input_boolean."):
            continue
        if not helper_entity_id.endswith(COLOR_TEMPERATURE_HELPER_SUFFIX):
            continue
        if helper_state.state != "on":
            continue

        helper_object_id = helper_entity_id[len("input_boolean."):]
        light_stem = helper_object_id[:-len(COLOR_TEMPERATURE_HELPER_SUFFIX)]
        light_entity_id = entity_id_from_helper_stem(light_stem)
        light_state = hass.states.get(light_entity_id)
        if light_state is None or light_state.state != "on":
            continue

        try:
            hass.services.call("light", "turn_on", {"entity_id": light_entity_id, "color_temp_kelvin": kelvin})
            logger.info("{} warmed to {}K for fader engagement.".format(light_entity_id, kelvin))
        except Exception as e:
            logger.error("Fader color temperature failed for {} at {}K. Error: {}".format(light_entity_id, kelvin, str(e)))


def adjust_brightness(entity_id, current_time, sunset_time):
    if not fader_is_enabled():
        return

    current_time = minute_aligned_time(current_time)
    fader_inputs = get_fader_inputs(entity_id, current_time)
    if fader_inputs is None:
        return

    input_boolean_entity = fader_inputs["input_boolean_entity"]
    needs_reset_entity = fader_inputs["needs_reset_entity"]

    is_active = get_state(input_boolean_entity, "off") == "on"
    needs_reset = get_state(needs_reset_entity, "off")

    if not is_active and needs_reset != "on":
        logger.info("{} fader inactive; holding.".format(entity_id))
        return

    light_state = hass.states.get(entity_id)
    current_brightness = get_current_brightness(light_state)

    target_info = calculate_target(current_time, fader_inputs["fade_in_start_time"], fader_inputs["start_time"], fader_inputs["end_time"], fader_inputs["max_brightness"], fader_inputs["min_brightness"])
    if should_passive_after_bedtime(target_info, needs_reset):
        target_info = passive_after_bedtime_target()
    expected_targets = expected_scheduled_targets(current_time, fader_inputs, target_info)
    decision = decide_action(entity_id, light_state, current_brightness, target_info, expected_targets, needs_reset)

    logger.info("{} fader period={}, target={}, expected={}, current={}, needs_reset={}, decision={}, reason={}".format(entity_id, target_info["period"], target_info["target"], expected_targets, current_brightness, needs_reset, decision["action"], decision["reason"]))

    if needs_reset == "on":
        hass.services.call("input_boolean", "turn_on", {"entity_id": input_boolean_entity})
        hass.services.call("input_boolean", "turn_off", {"entity_id": needs_reset_entity})

    apply_decision(entity_id, decision, fader_inputs)


def minutes_after_start(current_time, fade_in_start_time, fader_start_time):
    current_minutes, fade_in_start_minutes, start_minutes, end_minutes, lights_off_minutes, morning_minutes = resolve_timeline(current_time, fade_in_start_time, fader_start_time, fader_start_time)
    if fade_in_start_minutes >= start_minutes:
        return None
    return current_minutes - fade_in_start_minutes


def start_fade_in(entity_id, current_time):
    if not fader_is_enabled():
        return

    current_time = minute_aligned_time(current_time)
    fader_inputs = get_fader_inputs(entity_id, current_time)
    if fader_inputs is None:
        return

    elapsed_minutes = minutes_after_start(current_time, fader_inputs["fade_in_start_time"], fader_inputs["start_time"])
    if elapsed_minutes is None or elapsed_minutes < 0 or elapsed_minutes > FADE_IN_START_GRACE_MINUTES:
        logger.info("{} fade-in start skipped. current_time={}, fade_in_start={}, fader_start={}, elapsed={}".format(entity_id, current_time, fader_inputs["fade_in_start_time"], fader_inputs["start_time"], elapsed_minutes))
        return

    target_info = calculate_target(current_time, fader_inputs["fade_in_start_time"], fader_inputs["start_time"], fader_inputs["end_time"], fader_inputs["max_brightness"], fader_inputs["min_brightness"])
    if target_info["period"] != "fade_in" or target_info["target"] is None or target_info["target"] <= 0:
        logger.info("{} fade-in start skipped. period={}, target={}, reason={}".format(entity_id, target_info["period"], target_info["target"], target_info["reason"]))
        return

    hass.services.call("input_boolean", "turn_on", {"entity_id": fader_inputs["input_boolean_entity"]})
    hass.services.call("input_boolean", "turn_off", {"entity_id": fader_inputs["needs_reset_entity"]})

    light_state = hass.states.get(entity_id)
    if light_state is not None and light_state.state == "on":
        logger.info("{} fade-in enrolled; light already on, leaving current brightness.".format(entity_id))
        return

    decision = {"action": "turn_on", "brightness": target_info["target"], "reason": "scheduled_fade_in_start"}
    logger.info("{} fade-in start period={}, target={}, decision={}".format(entity_id, target_info["period"], target_info["target"], decision["action"]))
    apply_decision(entity_id, decision, fader_inputs)


# Get the function to call and the parameters from the input data
function_name = data.get("function_name")
entity_id = data.get("entity_id")
current_time = data.get("current_time")
sunset_time = data.get("sunset_time")

# Call the appropriate function based on the function_name
if function_name == "greet":
    pass
elif function_name == "adjust_brightness":
    adjust_brightness(entity_id, current_time, sunset_time)
elif function_name == "start_fade_in":
    start_fade_in(entity_id, current_time)
elif function_name == "warm_configured_color_temperature":
    warm_configured_color_temperature()
else:
    logger.info("Unknown function: {}".format(function_name))
