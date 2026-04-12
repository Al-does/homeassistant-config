"""Light Profile Restorer Integration."""

from .light_controller import LightProfileRestorer

async def async_setup(hass, config):
    """Set up the Light Profile Restorer integration."""
    restorer = LightProfileRestorer(hass)
    await restorer.async_setup()
    return True
