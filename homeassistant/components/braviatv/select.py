from homeassistant.helpers.entity import DeviceInfo
from homeassistant.components.select import SelectEntity
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import BraviaTVCoordinator
from .const import ATTR_MANUFACTURER, DEFAULT_NAME, DOMAIN

async def async_setup_entry(hass, config_entry, async_add_devices):
    coordinator = hass.data[DOMAIN][config_entry.entry_id]
    unique_id = config_entry.unique_id
    assert unique_id is not None
    device_info = DeviceInfo(
        identifiers={(DOMAIN, unique_id)},
        manufacturer=ATTR_MANUFACTURER,
        model=config_entry.title,
        name=DEFAULT_NAME,
    )
    async_add_devices([BraviaTvAudioOutputSelect(coordinator, device_info, config_entry)])


class BraviaTvAudioOutputSelect(CoordinatorEntity, SelectEntity):
    def __init__(self, coordinator: BraviaTVCoordinator, device, config_entry):
        self._device = device
        self._coordinator = coordinator
        self._config_entry = config_entry
        super().__init__(coordinator)

    @property
    def unique_id(self):
        """Return a unique ID to use for this entity."""
        return (f"{self._config_entry.entry_id}-audio_output")

    @property
    def name(self):
        """Return the name of the sensor."""
        return f"{self._device['name']} audio output"

    @property
    def icon(self):
        return "mdi:speaker-multiple"

    @property
    def current_option(self):
        return self.coordinator.sound_output

    @property
    def available(self):
        return self.coordinator.sound_output != None

    async def async_select_option(self, option: str) -> None:
        await self.coordinator.async_set_sound_output(option)

    @property
    def options(self):
        return ["speaker", "audioSystem"]


