light_id = "light.hue_white_lamp_1"  # Replace with your actual light entity ID
state = hass.states.get(light_id).state

# Toggle the light based on current state
new_state = "off" if state == "on" else "on"
service_data = {"entity_id": light_id}
hass.services.call("light", "turn_" + new_state, service_data, False)
