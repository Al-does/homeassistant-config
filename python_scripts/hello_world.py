BOOKSHELF_LIGHT_ENTITIES = [
    "light.dimmable_light_1_2",
    "light.dimmable_light_1_3",
    "light.dimmable_light_1_4",
]


def get_bookshelf_current_brightness():
    """Return the brightest active shelf bulb, or 0 if all are off."""
    brightness = 0
    for light_entity in BOOKSHELF_LIGHT_ENTITIES:
        light_state = hass.states.get(light_entity)
        if light_state and light_state.state == "on":
            bulb_brightness = light_state.attributes.get("brightness")
            if bulb_brightness is not None:
                brightness = max(brightness, int(bulb_brightness))
    return brightness


def calculate_brightness(current_time, start_time, end_time, max_brightness, min_brightness, input_boolean_entity, formated_entity_id, sunset_time, current_brightness_override=None):
    # Helper function to convert time string to minutes
    def time_to_minutes(time_str):
        h, m, s = time_str.split(':')
        return int(h) * 60 + int(m) + int(s) / 60

    # Convert times to minutes
    current_minutes = time_to_minutes(current_time)
    start_minutes = time_to_minutes(start_time)
    end_minutes = time_to_minutes(end_time)
    sunset_minutes = time_to_minutes(sunset_time)
    
    # Convert global times to minutes
    global_lights_off_time = hass.states.get("input_datetime.global_lights_off_time").state
    global_morning_time = hass.states.get("input_datetime.global_morning_time").state
    global_lights_off_minutes = time_to_minutes(global_lights_off_time)
    global_morning_minutes = time_to_minutes(global_morning_time)

    # Convert brightness values to integers
    max_brightness = int(float(max_brightness))
    min_brightness = int(float(min_brightness))
    
    # Get the light's current brightness
    if current_brightness_override is not None:
        current_brightness = current_brightness_override
    else:
        light_state = hass.states.get(entity_id)
        if light_state and 'brightness' in light_state.attributes:
            current_brightness = light_state.attributes['brightness']
            if current_brightness is None:
                current_brightness = 0
        else:
            current_brightness = 0  # Light is off or brightness attribute is not available
    
    # Adjust for wrap-around times
    if 0 <= global_lights_off_minutes < global_morning_minutes:
        global_lights_off_minutes += 24 * 60
    if 0 <= end_minutes < global_morning_minutes:
        end_minutes += 24 * 60
    if 0 <= current_minutes < global_morning_minutes:
        current_minutes += 24 * 60
    global_morning_minutes += 24 * 60

    # Cubic easing function
    def cubic_ease_in_out(t):
        if t < 0.5:
            return 4 * t * t * t
        else:
            return 1 - (-2 * t + 2) ** 3 / 2
    
    # Check if we need to boost brightness
    fader_booster_is_active = hass.states.get("input_boolean.fader_booster_is_active").state
    if fader_booster_is_active == "on":
        fader_boost = 1.2
        if min_brightness > 0:
            min_brightness = max(min_brightness, 20)
    else:
        fader_boost = 1
        
    #check if we need to reset the light to the calculated path
    needs_reset_entity = "input_boolean." + formated_entity_id + "_needs_reset"
    needs_reset = hass.states.get(needs_reset_entity).state
        
    # Determine brightness based on the time conditions
    if start_minutes <= current_minutes <= end_minutes:
        total_minutes = end_minutes - start_minutes
        elapsed_minutes = current_minutes - start_minutes
        
        # Calculate brightness using cubic easing and fading, if necessary
        brightness_range = max_brightness - min_brightness
        fade_progress = elapsed_minutes / total_minutes
        ease_progress = cubic_ease_in_out(fade_progress)
        calculated_brightness = max_brightness - int(brightness_range * ease_progress)
        calculated_brightness = min(255, max(0, calculated_brightness * fader_boost))
        # there's a better way to do the line above such that it doesn't have to clip at the top
        output = calculated_brightness
    elif end_minutes < current_minutes <= global_lights_off_minutes:
        # After end time but before global lights off time
        logger.info(f"{entity_id} set to min brightness {min_brightness} after end time.")
        output = min_brightness
    elif global_lights_off_minutes < current_minutes < global_morning_minutes:
        # After global lights off time but before global morning time
        logger.info(f"{entity_id} turned off after global lights off time if no party mode.")
        if fader_booster_is_active == "on":
            #maybe change this is if the jump is too rapid?
            output = min_brightness / 2
        else:
            output = 0
    # else:
    #     # Outside all specified times, keep current brightness
    #     if input_boolean_entity == "input_boolean.light_under_cabinet_lights_is_active":
    #         logger.error(f"got UCL. needs_reset is {needs_reset}")
    #     logger.info(f"{entity_id} calc'ed outside time. Brtns: {current_brightness}")
    #     if needs_reset == "on":
    #         output = 0
    #     else:
    #         output = max(0, current_brightness)
    else:
        # Outside all specified times, keep current brightness
        if input_boolean_entity == "input_boolean.light_under_cabinet_lights_is_active":
            logger.error(f"got UCL. needs_reset is {needs_reset}")
        logger.info(f"{entity_id} calc'ed outside time. Brtns: {current_brightness}")
        if current_minutes < sunset_minutes and needs_reset == "on":
            output = 0
        else:
            output = max(0, current_brightness)
    
    if needs_reset == "off":
        if current_brightness == 0 or output < 0.8 * current_brightness or output > 1.2 * current_brightness:
            hass.services.call('input_boolean', 'turn_off', {'entity_id': input_boolean_entity})
            return current_brightness
        else:
            return output
    elif needs_reset == "on":
        hass.services.call('input_boolean', 'turn_on', {'entity_id': input_boolean_entity})
        hass.services.call('input_boolean', 'turn_off', {'entity_id': needs_reset_entity})
        return output
    else:
        return output
        
def adjust_brightness(entity_id, current_time, sunset_time):
    # Get the boolean value
    formated_entity_id = entity_id.replace(".", "_")
    input_boolean_entity = "input_boolean." + formated_entity_id + "_is_active"
    is_active = hass.states.get(input_boolean_entity).state == "on"
    
    # Get the start time
    start_time_entity = "input_datetime." + formated_entity_id + "_start_time"
    start_time = hass.states.get(start_time_entity).state
    if start_time == "12:34:56":
        start_time = hass.states.get("input_datetime.global_fader_start_time").state
    
    # Get the end time
    end_time_entity = "input_datetime." + formated_entity_id + "_end_time"
    end_time = hass.states.get(end_time_entity).state
    if end_time == "12:34:56":
        end_time = hass.states.get("input_datetime.global_fader_end_time").state
    
    # Get the min brightness value
    min_brightness_entity = "input_number." + formated_entity_id + "_min_brightness"
    min_brightness = float(hass.states.get(min_brightness_entity).state)
    
    # Get the max brightness value
    max_brightness_entity = "input_number." + formated_entity_id + "_max_brightness"
    max_brightness = float(hass.states.get(max_brightness_entity).state)

    # Calculate what the brightness should be
    brightness = calculate_brightness(current_time, start_time, end_time, max_brightness, min_brightness, input_boolean_entity, formated_entity_id, sunset_time)

    try:
        brightness = int(brightness)
    except (TypeError, ValueError) as e:
        # Log an error if conversion fails
        logger.error("Cannot convert to int. Entity ID {}, time {}, start {}, end {}, max {}, min {}. Error: {}".format(entity_id, current_time, start_time, end_time, max_brightness, min_brightness, str(e)))
        return  # Exit the function
    
    if is_active:
        # Set the brightness of the light
        hass.services.call("light", "turn_on", {"entity_id": entity_id, "brightness": brightness})


def adjust_bookshelf_brightness(current_time, sunset_time):
    """Use light_bookshelf_lights helpers but drive the three shelf bulbs."""
    entity_id = "light.bookshelf_lights"
    formated_entity_id = entity_id.replace(".", "_")
    input_boolean_entity = "input_boolean." + formated_entity_id + "_is_active"
    is_active = hass.states.get(input_boolean_entity).state == "on"

    start_time_entity = "input_datetime." + formated_entity_id + "_start_time"
    start_time = hass.states.get(start_time_entity).state
    if start_time == "12:34:56":
        start_time = hass.states.get("input_datetime.global_fader_start_time").state

    end_time_entity = "input_datetime." + formated_entity_id + "_end_time"
    end_time = hass.states.get(end_time_entity).state
    if end_time == "12:34:56":
        end_time = hass.states.get("input_datetime.global_fader_end_time").state

    min_brightness = float(
        hass.states.get("input_number." + formated_entity_id + "_min_brightness").state
    )
    max_brightness = float(
        hass.states.get("input_number." + formated_entity_id + "_max_brightness").state
    )

    brightness = calculate_brightness(
        current_time,
        start_time,
        end_time,
        max_brightness,
        min_brightness,
        input_boolean_entity,
        formated_entity_id,
        sunset_time,
        current_brightness_override=get_bookshelf_current_brightness(),
    )

    try:
        brightness = int(brightness)
    except (TypeError, ValueError) as e:
        logger.error(
            "Cannot convert bookshelf brightness to int. time {}, start {}, end {}, max {}, min {}. Error: {}".format(
                current_time, start_time, end_time, max_brightness, min_brightness, str(e)
            )
        )
        return

    if is_active:
        for light_entity in BOOKSHELF_LIGHT_ENTITIES:
            hass.services.call(
                "light", "turn_on", {"entity_id": light_entity, "brightness": brightness}
            )


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
elif function_name == "adjust_bookshelf_brightness":
    adjust_bookshelf_brightness(current_time, sunset_time)
else:
    logger.info("Unknown function: {}".format(function_name))
