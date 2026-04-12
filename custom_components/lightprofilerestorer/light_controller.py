import logging
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.helpers.entity_component import EntityComponent
from homeassistant.util import dt as dt_util

_LOGGER = logging.getLogger(__name__)

class LightProfileRestorer:
    def __init__(self, hass: HomeAssistant):
        self.hass = hass
        self.active_lights = {}  # Dictionary to track active state of lights

    async def async_setup(self):
        """Set up custom services."""
        _LOGGER.debug("Setting up custom services for Light Profile Restorer")
        self.hass.services.async_register("lightprofilerestorer", "start_dimming", self.start_dimming)
        self.hass.services.async_register("lightprofilerestorer", "adjust_brightness", self.adjust_brightness)
        self.hass.services.async_register("lightprofilerestorer", "deactivate_fader", self.deactivate_fader)
        self.hass.services.async_register("lightprofilerestorer", "reactivate_fader", self.reactivate_fader)

    async def start_dimming(self, call: ServiceCall):
        """Start the dimming process for a light."""
        entity_id = call.data.get('entity_id')
        self.active_lights[entity_id] = True
        _LOGGER.debug(f"Starting dimming for {entity_id}")
        # Get current brightness
        current_brightness = self.hass.states.get(entity_id).attributes.get('brightness', 255)
        self.hass.states.async_set(f"input_number.{entity_id}_current_brightness", current_brightness)
        await self.adjust_brightness(call)

    async def adjust_brightness(self, call: ServiceCall):
        """Adjust the brightness of the light based on the current time and dimming curve."""
        entity_id = call.data.get('entity_id')
        entity_name = entity_id.replace(".", "_")
        _LOGGER.debug(f"Adjusting brightness for {entity_id}")
        
        if entity_id not in self.active_lights or not self.active_lights[entity_id]:
            _LOGGER.debug(f"{entity_id} is not active")
            return
    
        # Check if the dimming is active
        if not self.hass.states.get(f"input_boolean.{entity_name}_dimming_active").state == 'on':
            _LOGGER.debug(f"{entity_id} dimming is not active")
            return
        
        current_time = dt_util.now()
        start_time = dt_util.as_local(dt_util.parse_datetime(
            self.hass.states.get(f"input_datetime.{entity_name}_start_time").state))
        end_time = dt_util.as_local(dt_util.parse_datetime(
            self.hass.states.get(f"input_datetime.{entity_name}_end_time").state))
        current_brightness = int(self.hass.states.get(f"input_number.{entity_name}_current_brightness").state)
        min_brightness = int(self.hass.states.get(f"input_number.{entity_name}_min_brightness").state)
        
        brightness = self.calculate_brightness(current_time, start_time, end_time, current_brightness, min_brightness)
        brightness = int(brightness * 2.55)  # Convert 0-100 to 0-255
        _LOGGER.debug(f"Calculated brightness for {entity_id}: {brightness}")
        
        light_state = self.hass.states.get(entity_id)
        if light_state.state != 'on':
            _LOGGER.debug(f"{entity_id} is not on, turning it on")
            await self.hass.services.async_call('light', 'turn_on', {'entity_id': entity_id})
            
        #delete the below after debugging
        brightness = 1
        
        _LOGGER.debug(f"Calling light.turn_on service for {entity_id} with brightness {brightness}")
        try:
            await self.hass.services.async_call('light', 'turn_on', {'entity_id': entity_id, 'brightness': brightness})
        except Exception as e:
            _LOGGER.error(f"Error adjusting brightness for {entity_id}: {str(e)}")

    def calculate_brightness(self, current_time, start_time, end_time, current_brightness, min_brightness):
        """Calculate brightness based on a cubic or other dimming curve."""
        # Example calculation: simple linear interpolation (replace with cubic as needed)
        total_duration = (end_time - start_time).total_seconds()
        elapsed = (current_time - start_time).total_seconds()
        if elapsed > total_duration:
            return min_brightness
        return int(min_brightness + (current_brightness - min_brightness) * (1 - elapsed / total_duration))

    async def deactivate_fader(self, call: ServiceCall):
        """Deactivate the dimming for a light."""
        entity_id = call.data.get('entity_id')
        _LOGGER.debug(f"Deactivating fader for {entity_id}")
        self.active_lights[entity_id] = False
        # Turn off the dimming active boolean
        await self.hass.services.async_call('input_boolean', 'turn_off', {'entity_id': f'input_boolean.{entity_id}_dimming_active'})

    async def reactivate_fader(self, call: ServiceCall):
        """Reactivate the dimming after it was deactivated."""
        entity_id = call.data.get('entity_id')
        _LOGGER.debug(f"Reactivating fader for {entity_id}")
        if dt_util.as_local(dt_util.now()).time() < dt_util.parse_time(
                self.hass.states.get(f"input_datetime.{entity_id}_end_time").state):
            self.active_lights[entity_id] = True
            # Turn on the dimming active boolean
            await self.hass.services.async_call('input_boolean', 'turn_on', {'entity_id': f'input_boolean.{entity_id}_dimming_active'})
            await self.adjust_brightness(call)
