"""The tests for tg_test device triggers."""
import pytest

from homeassistant.components.tg_test import DOMAIN
import homeassistant.components.automation as automation
from homeassistant.const import STATE_OFF, STATE_ON
from homeassistant.helpers import device_registry
from homeassistant.setup import async_setup_component

from tests.common import (
    MockConfigEntry,
    assert_lists_same,
    async_get_device_automations,
    async_mock_service,
    mock_device_registry,
    mock_registry,
)


@pytest.fixture
def device_reg(hass):
    """Return an empty, loaded, registry."""
    return mock_device_registry(hass)


@pytest.fixture
def entity_reg(hass):
    """Return an empty, loaded, registry."""
    return mock_registry(hass)


@pytest.fixture
def calls(hass):
    """Track calls to a mock service."""
    return async_mock_service(hass, "test", "automation")


async def test_get_triggers(hass, device_reg, entity_reg):
    """Test we get the expected triggers from a tg_test."""
    config_entry = MockConfigEntry(domain="test", data={})
    config_entry.add_to_hass(hass)
    device_entry = device_reg.async_get_or_create(
        config_entry_id=config_entry.entry_id,
        connections={(device_registry.CONNECTION_NETWORK_MAC, "12:34:56:AB:CD:EF")},
    )
    entity_reg.async_get_or_create(DOMAIN, "test", "5678", device_id=device_entry.id)
    expected_triggers = [
        {
            "platform": "device",
            "domain": DOMAIN,
            "type": "turned_off",
            "device_id": device_entry.id,
            "entity_id": f"{DOMAIN}.test_5678",
        },
        {
            "platform": "device",
            "domain": DOMAIN,
            "type": "turned_on",
            "device_id": device_entry.id,
            "entity_id": f"{DOMAIN}.test_5678",
        },
    ]
    triggers = await async_get_device_automations(hass, "trigger", device_entry.id)
    assert_lists_same(triggers, expected_triggers)


async def test_if_fires_on_state_change(hass, calls):
    """Test for turn_on and turn_off triggers firing."""
    hass.states.async_set("tg_test.entity", STATE_OFF)

    assert await async_setup_component(
        hass,
        automation.DOMAIN,
        {
            automation.DOMAIN: [
                {
                    "trigger": {
                        "platform": "device",
                        "domain": DOMAIN,
                        "device_id": "",
                        "entity_id": "tg_test.entity",
                        "type": "turned_on",
                    },
                    "action": {
                        "service": "test.automation",
                        "data_template": {
                            "some": (
                                "turn_on - {{ trigger.platform}} - "
                                "{{ trigger.entity_id}} - {{ trigger.from_state.state}} - "
                                "{{ trigger.to_state.state}} - {{ trigger.for }}"
                            )
                        },
                    },
                },
                {
                    "trigger": {
                        "platform": "device",
                        "domain": DOMAIN,
                        "device_id": "",
                        "entity_id": "tg_test.entity",
                        "type": "turned_off",
                    },
                    "action": {
                        "service": "test.automation",
                        "data_template": {
                            "some": (
                                "turn_off - {{ trigger.platform}} - "
                                "{{ trigger.entity_id}} - {{ trigger.from_state.state}} - "
                                "{{ trigger.to_state.state}} - {{ trigger.for }}"
                            )
                        },
                    },
                },
            ]
        },
    )

    # Fake that the entity is turning on.
    hass.states.async_set("tg_test.entity", STATE_ON)
    await hass.async_block_till_done()
    assert len(calls) == 1
    assert calls[0].data["some"] == "turn_on - device - {} - off - on - None".format(
        "tg_test.entity"
    )

    # Fake that the entity is turning off.
    hass.states.async_set("tg_test.entity", STATE_OFF)
    await hass.async_block_till_done()
    assert len(calls) == 2
    assert calls[1].data["some"] == "turn_off - device - {} - on - off - None".format(
        "tg_test.entity"
    )
