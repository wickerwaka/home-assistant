"""The tests for the mqtt climate component."""
import copy
import json
import unittest
from unittest.mock import ANY

import pytest
import voluptuous as vol

from homeassistant.components import climate, mqtt
from homeassistant.components.climate import (
    DEFAULT_MAX_TEMP, DEFAULT_MIN_TEMP, SUPPORT_AUX_HEAT, SUPPORT_AWAY_MODE,
    SUPPORT_FAN_MODE, SUPPORT_HOLD_MODE, SUPPORT_OPERATION_MODE,
    SUPPORT_SWING_MODE, SUPPORT_TARGET_TEMPERATURE)
from homeassistant.components.mqtt.discovery import async_start
from homeassistant.const import STATE_OFF, STATE_UNAVAILABLE
from homeassistant.setup import setup_component
from homeassistant.util.unit_system import METRIC_SYSTEM

from tests.common import (
    MockConfigEntry, async_fire_mqtt_message, async_mock_mqtt_component,
    async_setup_component, fire_mqtt_message, get_test_home_assistant,
    mock_component, mock_mqtt_component, mock_registry)
from tests.components.climate import common

ENTITY_CLIMATE = 'climate.test'

DEFAULT_CONFIG = {
    'climate': {
        'platform': 'mqtt',
        'name': 'test',
        'mode_command_topic': 'mode-topic',
        'temperature_command_topic': 'temperature-topic',
        'fan_mode_command_topic': 'fan-mode-topic',
        'swing_mode_command_topic': 'swing-mode-topic',
        'away_mode_command_topic': 'away-mode-topic',
        'hold_command_topic': 'hold-topic',
        'aux_command_topic': 'aux-topic'
    }}


class TestMQTTClimate(unittest.TestCase):
    """Test the mqtt climate hvac."""

    def setUp(self):  # pylint: disable=invalid-name
        """Set up things to be run when tests are started."""
        self.hass = get_test_home_assistant()
        self.mock_publish = mock_mqtt_component(self.hass)
        self.hass.config.units = METRIC_SYSTEM

    def tearDown(self):  # pylint: disable=invalid-name
        """Stop down everything that was started."""
        self.hass.stop()

    def test_setup_params(self):
        """Test the initial parameters."""
        assert setup_component(self.hass, climate.DOMAIN, DEFAULT_CONFIG)

        state = self.hass.states.get(ENTITY_CLIMATE)
        assert 21 == state.attributes.get('temperature')
        assert "low" == state.attributes.get('fan_mode')
        assert "off" == state.attributes.get('swing_mode')
        assert "off" == state.attributes.get('operation_mode')
        assert DEFAULT_MIN_TEMP == state.attributes.get('min_temp')
        assert DEFAULT_MAX_TEMP == state.attributes.get('max_temp')

    def test_supported_features(self):
        """Test the supported_features."""
        assert setup_component(self.hass, climate.DOMAIN, DEFAULT_CONFIG)

        state = self.hass.states.get(ENTITY_CLIMATE)
        support = (SUPPORT_TARGET_TEMPERATURE | SUPPORT_OPERATION_MODE |
                   SUPPORT_SWING_MODE | SUPPORT_FAN_MODE | SUPPORT_AWAY_MODE |
                   SUPPORT_HOLD_MODE | SUPPORT_AUX_HEAT)

        assert state.attributes.get("supported_features") == support

    def test_get_operation_modes(self):
        """Test that the operation list returns the correct modes."""
        assert setup_component(self.hass, climate.DOMAIN, DEFAULT_CONFIG)

        state = self.hass.states.get(ENTITY_CLIMATE)
        modes = state.attributes.get('operation_list')
        assert [
            climate.STATE_AUTO, STATE_OFF, climate.STATE_COOL,
            climate.STATE_HEAT, climate.STATE_DRY, climate.STATE_FAN_ONLY
        ] == modes

    def test_set_operation_bad_attr_and_state(self):
        """Test setting operation mode without required attribute.

        Also check the state.
        """
        assert setup_component(self.hass, climate.DOMAIN, DEFAULT_CONFIG)

        state = self.hass.states.get(ENTITY_CLIMATE)
        assert "off" == state.attributes.get('operation_mode')
        assert "off" == state.state
        with pytest.raises(vol.Invalid):
            common.set_operation_mode(self.hass, None, ENTITY_CLIMATE)
        self.hass.block_till_done()
        state = self.hass.states.get(ENTITY_CLIMATE)
        assert "off" == state.attributes.get('operation_mode')
        assert "off" == state.state

    def test_set_operation(self):
        """Test setting of new operation mode."""
        assert setup_component(self.hass, climate.DOMAIN, DEFAULT_CONFIG)

        state = self.hass.states.get(ENTITY_CLIMATE)
        assert "off" == state.attributes.get('operation_mode')
        assert "off" == state.state
        common.set_operation_mode(self.hass, "cool", ENTITY_CLIMATE)
        self.hass.block_till_done()
        state = self.hass.states.get(ENTITY_CLIMATE)
        assert "cool" == state.attributes.get('operation_mode')
        assert "cool" == state.state
        self.mock_publish.async_publish.assert_called_once_with(
            'mode-topic', 'cool', 0, False)

    def test_set_operation_pessimistic(self):
        """Test setting operation mode in pessimistic mode."""
        config = copy.deepcopy(DEFAULT_CONFIG)
        config['climate']['mode_state_topic'] = 'mode-state'
        assert setup_component(self.hass, climate.DOMAIN, config)

        state = self.hass.states.get(ENTITY_CLIMATE)
        assert state.attributes.get('operation_mode') is None
        assert "unknown" == state.state

        common.set_operation_mode(self.hass, "cool", ENTITY_CLIMATE)
        self.hass.block_till_done()
        state = self.hass.states.get(ENTITY_CLIMATE)
        assert state.attributes.get('operation_mode') is None
        assert "unknown" == state.state

        fire_mqtt_message(self.hass, 'mode-state', 'cool')
        self.hass.block_till_done()
        state = self.hass.states.get(ENTITY_CLIMATE)
        assert "cool" == state.attributes.get('operation_mode')
        assert "cool" == state.state

        fire_mqtt_message(self.hass, 'mode-state', 'bogus mode')
        self.hass.block_till_done()
        state = self.hass.states.get(ENTITY_CLIMATE)
        assert "cool" == state.attributes.get('operation_mode')
        assert "cool" == state.state

    def test_set_operation_with_power_command(self):
        """Test setting of new operation mode with power command enabled."""
        config = copy.deepcopy(DEFAULT_CONFIG)
        config['climate']['power_command_topic'] = 'power-command'
        assert setup_component(self.hass, climate.DOMAIN, config)

        state = self.hass.states.get(ENTITY_CLIMATE)
        assert "off" == state.attributes.get('operation_mode')
        assert "off" == state.state
        common.set_operation_mode(self.hass, "on", ENTITY_CLIMATE)
        self.hass.block_till_done()
        state = self.hass.states.get(ENTITY_CLIMATE)
        assert "on" == state.attributes.get('operation_mode')
        assert "on" == state.state
        self.mock_publish.async_publish.assert_has_calls([
            unittest.mock.call('power-command', 'ON', 0, False),
            unittest.mock.call('mode-topic', 'on', 0, False)
        ])
        self.mock_publish.async_publish.reset_mock()

        common.set_operation_mode(self.hass, "off", ENTITY_CLIMATE)
        self.hass.block_till_done()
        state = self.hass.states.get(ENTITY_CLIMATE)
        assert "off" == state.attributes.get('operation_mode')
        assert "off" == state.state
        self.mock_publish.async_publish.assert_has_calls([
            unittest.mock.call('power-command', 'OFF', 0, False),
            unittest.mock.call('mode-topic', 'off', 0, False)
        ])
        self.mock_publish.async_publish.reset_mock()

    def test_set_fan_mode_bad_attr(self):
        """Test setting fan mode without required attribute."""
        assert setup_component(self.hass, climate.DOMAIN, DEFAULT_CONFIG)

        state = self.hass.states.get(ENTITY_CLIMATE)
        assert "low" == state.attributes.get('fan_mode')
        with pytest.raises(vol.Invalid):
            common.set_fan_mode(self.hass, None, ENTITY_CLIMATE)
        self.hass.block_till_done()
        state = self.hass.states.get(ENTITY_CLIMATE)
        assert "low" == state.attributes.get('fan_mode')

    def test_set_fan_mode_pessimistic(self):
        """Test setting of new fan mode in pessimistic mode."""
        config = copy.deepcopy(DEFAULT_CONFIG)
        config['climate']['fan_mode_state_topic'] = 'fan-state'
        assert setup_component(self.hass, climate.DOMAIN, config)

        state = self.hass.states.get(ENTITY_CLIMATE)
        assert state.attributes.get('fan_mode') is None

        common.set_fan_mode(self.hass, 'high', ENTITY_CLIMATE)
        self.hass.block_till_done()
        state = self.hass.states.get(ENTITY_CLIMATE)
        assert state.attributes.get('fan_mode') is None

        fire_mqtt_message(self.hass, 'fan-state', 'high')
        self.hass.block_till_done()
        state = self.hass.states.get(ENTITY_CLIMATE)
        assert 'high' == state.attributes.get('fan_mode')

        fire_mqtt_message(self.hass, 'fan-state', 'bogus mode')
        self.hass.block_till_done()
        state = self.hass.states.get(ENTITY_CLIMATE)
        assert 'high' == state.attributes.get('fan_mode')

    def test_set_fan_mode(self):
        """Test setting of new fan mode."""
        assert setup_component(self.hass, climate.DOMAIN, DEFAULT_CONFIG)

        state = self.hass.states.get(ENTITY_CLIMATE)
        assert "low" == state.attributes.get('fan_mode')
        common.set_fan_mode(self.hass, 'high', ENTITY_CLIMATE)
        self.hass.block_till_done()
        self.mock_publish.async_publish.assert_called_once_with(
            'fan-mode-topic', 'high', 0, False)
        state = self.hass.states.get(ENTITY_CLIMATE)
        assert 'high' == state.attributes.get('fan_mode')

    def test_set_swing_mode_bad_attr(self):
        """Test setting swing mode without required attribute."""
        assert setup_component(self.hass, climate.DOMAIN, DEFAULT_CONFIG)

        state = self.hass.states.get(ENTITY_CLIMATE)
        assert "off" == state.attributes.get('swing_mode')
        with pytest.raises(vol.Invalid):
            common.set_swing_mode(self.hass, None, ENTITY_CLIMATE)
        self.hass.block_till_done()
        state = self.hass.states.get(ENTITY_CLIMATE)
        assert "off" == state.attributes.get('swing_mode')

    def test_set_swing_pessimistic(self):
        """Test setting swing mode in pessimistic mode."""
        config = copy.deepcopy(DEFAULT_CONFIG)
        config['climate']['swing_mode_state_topic'] = 'swing-state'
        assert setup_component(self.hass, climate.DOMAIN, config)

        state = self.hass.states.get(ENTITY_CLIMATE)
        assert state.attributes.get('swing_mode') is None

        common.set_swing_mode(self.hass, 'on', ENTITY_CLIMATE)
        self.hass.block_till_done()
        state = self.hass.states.get(ENTITY_CLIMATE)
        assert state.attributes.get('swing_mode') is None

        fire_mqtt_message(self.hass, 'swing-state', 'on')
        self.hass.block_till_done()
        state = self.hass.states.get(ENTITY_CLIMATE)
        assert "on" == state.attributes.get('swing_mode')

        fire_mqtt_message(self.hass, 'swing-state', 'bogus state')
        self.hass.block_till_done()
        state = self.hass.states.get(ENTITY_CLIMATE)
        assert "on" == state.attributes.get('swing_mode')

    def test_set_swing(self):
        """Test setting of new swing mode."""
        assert setup_component(self.hass, climate.DOMAIN, DEFAULT_CONFIG)

        state = self.hass.states.get(ENTITY_CLIMATE)
        assert "off" == state.attributes.get('swing_mode')
        common.set_swing_mode(self.hass, 'on', ENTITY_CLIMATE)
        self.hass.block_till_done()
        self.mock_publish.async_publish.assert_called_once_with(
            'swing-mode-topic', 'on', 0, False)
        state = self.hass.states.get(ENTITY_CLIMATE)
        assert "on" == state.attributes.get('swing_mode')

    def test_set_target_temperature(self):
        """Test setting the target temperature."""
        assert setup_component(self.hass, climate.DOMAIN, DEFAULT_CONFIG)

        state = self.hass.states.get(ENTITY_CLIMATE)
        assert 21 == state.attributes.get('temperature')
        common.set_operation_mode(self.hass, 'heat', ENTITY_CLIMATE)
        self.hass.block_till_done()
        state = self.hass.states.get(ENTITY_CLIMATE)
        assert 'heat' == state.attributes.get('operation_mode')
        self.mock_publish.async_publish.assert_called_once_with(
            'mode-topic', 'heat', 0, False)
        self.mock_publish.async_publish.reset_mock()
        common.set_temperature(self.hass, temperature=47,
                               entity_id=ENTITY_CLIMATE)
        self.hass.block_till_done()
        state = self.hass.states.get(ENTITY_CLIMATE)
        assert 47 == state.attributes.get('temperature')
        self.mock_publish.async_publish.assert_called_once_with(
            'temperature-topic', 47, 0, False)

        # also test directly supplying the operation mode to set_temperature
        self.mock_publish.async_publish.reset_mock()
        common.set_temperature(self.hass, temperature=21,
                               operation_mode="cool",
                               entity_id=ENTITY_CLIMATE)
        self.hass.block_till_done()
        state = self.hass.states.get(ENTITY_CLIMATE)
        assert 'cool' == state.attributes.get('operation_mode')
        assert 21 == state.attributes.get('temperature')
        self.mock_publish.async_publish.assert_has_calls([
            unittest.mock.call('mode-topic', 'cool', 0, False),
            unittest.mock.call('temperature-topic', 21, 0, False)
        ])
        self.mock_publish.async_publish.reset_mock()

    def test_set_target_temperature_pessimistic(self):
        """Test setting the target temperature."""
        config = copy.deepcopy(DEFAULT_CONFIG)
        config['climate']['temperature_state_topic'] = 'temperature-state'
        assert setup_component(self.hass, climate.DOMAIN, config)

        state = self.hass.states.get(ENTITY_CLIMATE)
        assert state.attributes.get('temperature') is None
        common.set_operation_mode(self.hass, 'heat', ENTITY_CLIMATE)
        self.hass.block_till_done()
        common.set_temperature(self.hass, temperature=47,
                               entity_id=ENTITY_CLIMATE)
        self.hass.block_till_done()
        state = self.hass.states.get(ENTITY_CLIMATE)
        assert state.attributes.get('temperature') is None

        fire_mqtt_message(self.hass, 'temperature-state', '1701')
        self.hass.block_till_done()
        state = self.hass.states.get(ENTITY_CLIMATE)
        assert 1701 == state.attributes.get('temperature')

        fire_mqtt_message(self.hass, 'temperature-state', 'not a number')
        self.hass.block_till_done()
        state = self.hass.states.get(ENTITY_CLIMATE)
        assert 1701 == state.attributes.get('temperature')

    def test_receive_mqtt_temperature(self):
        """Test getting the current temperature via MQTT."""
        config = copy.deepcopy(DEFAULT_CONFIG)
        config['climate']['current_temperature_topic'] = 'current_temperature'
        mock_component(self.hass, 'mqtt')
        assert setup_component(self.hass, climate.DOMAIN, config)

        fire_mqtt_message(self.hass, 'current_temperature', '47')
        self.hass.block_till_done()
        state = self.hass.states.get(ENTITY_CLIMATE)
        assert 47 == state.attributes.get('current_temperature')

    def test_set_away_mode_pessimistic(self):
        """Test setting of the away mode."""
        config = copy.deepcopy(DEFAULT_CONFIG)
        config['climate']['away_mode_state_topic'] = 'away-state'
        assert setup_component(self.hass, climate.DOMAIN, config)

        state = self.hass.states.get(ENTITY_CLIMATE)
        assert 'off' == state.attributes.get('away_mode')

        common.set_away_mode(self.hass, True, ENTITY_CLIMATE)
        self.hass.block_till_done()
        state = self.hass.states.get(ENTITY_CLIMATE)
        assert 'off' == state.attributes.get('away_mode')

        fire_mqtt_message(self.hass, 'away-state', 'ON')
        self.hass.block_till_done()
        state = self.hass.states.get(ENTITY_CLIMATE)
        assert 'on' == state.attributes.get('away_mode')

        fire_mqtt_message(self.hass, 'away-state', 'OFF')
        self.hass.block_till_done()
        state = self.hass.states.get(ENTITY_CLIMATE)
        assert 'off' == state.attributes.get('away_mode')

        fire_mqtt_message(self.hass, 'away-state', 'nonsense')
        self.hass.block_till_done()
        state = self.hass.states.get(ENTITY_CLIMATE)
        assert 'off' == state.attributes.get('away_mode')

    def test_set_away_mode(self):
        """Test setting of the away mode."""
        config = copy.deepcopy(DEFAULT_CONFIG)
        config['climate']['payload_on'] = 'AN'
        config['climate']['payload_off'] = 'AUS'

        assert setup_component(self.hass, climate.DOMAIN, config)

        state = self.hass.states.get(ENTITY_CLIMATE)
        assert 'off' == state.attributes.get('away_mode')
        common.set_away_mode(self.hass, True, ENTITY_CLIMATE)
        self.hass.block_till_done()
        self.mock_publish.async_publish.assert_called_once_with(
            'away-mode-topic', 'AN', 0, False)
        self.mock_publish.async_publish.reset_mock()
        state = self.hass.states.get(ENTITY_CLIMATE)
        assert 'on' == state.attributes.get('away_mode')

        common.set_away_mode(self.hass, False, ENTITY_CLIMATE)
        self.hass.block_till_done()
        self.mock_publish.async_publish.assert_called_once_with(
            'away-mode-topic', 'AUS', 0, False)
        state = self.hass.states.get(ENTITY_CLIMATE)
        assert 'off' == state.attributes.get('away_mode')

    def test_set_hold_pessimistic(self):
        """Test setting the hold mode in pessimistic mode."""
        config = copy.deepcopy(DEFAULT_CONFIG)
        config['climate']['hold_state_topic'] = 'hold-state'
        assert setup_component(self.hass, climate.DOMAIN, config)

        state = self.hass.states.get(ENTITY_CLIMATE)
        assert state.attributes.get('hold_mode') is None

        common.set_hold_mode(self.hass, 'on', ENTITY_CLIMATE)
        self.hass.block_till_done()
        state = self.hass.states.get(ENTITY_CLIMATE)
        assert state.attributes.get('hold_mode') is None

        fire_mqtt_message(self.hass, 'hold-state', 'on')
        self.hass.block_till_done()
        state = self.hass.states.get(ENTITY_CLIMATE)
        assert 'on' == state.attributes.get('hold_mode')

        fire_mqtt_message(self.hass, 'hold-state', 'off')
        self.hass.block_till_done()
        state = self.hass.states.get(ENTITY_CLIMATE)
        assert 'off' == state.attributes.get('hold_mode')

    def test_set_hold(self):
        """Test setting the hold mode."""
        assert setup_component(self.hass, climate.DOMAIN, DEFAULT_CONFIG)

        state = self.hass.states.get(ENTITY_CLIMATE)
        assert state.attributes.get('hold_mode') is None
        common.set_hold_mode(self.hass, 'on', ENTITY_CLIMATE)
        self.hass.block_till_done()
        self.mock_publish.async_publish.assert_called_once_with(
            'hold-topic', 'on', 0, False)
        self.mock_publish.async_publish.reset_mock()
        state = self.hass.states.get(ENTITY_CLIMATE)
        assert 'on' == state.attributes.get('hold_mode')

        common.set_hold_mode(self.hass, 'off', ENTITY_CLIMATE)
        self.hass.block_till_done()
        self.mock_publish.async_publish.assert_called_once_with(
            'hold-topic', 'off', 0, False)
        state = self.hass.states.get(ENTITY_CLIMATE)
        assert 'off' == state.attributes.get('hold_mode')

    def test_set_aux_pessimistic(self):
        """Test setting of the aux heating in pessimistic mode."""
        config = copy.deepcopy(DEFAULT_CONFIG)
        config['climate']['aux_state_topic'] = 'aux-state'
        assert setup_component(self.hass, climate.DOMAIN, config)

        state = self.hass.states.get(ENTITY_CLIMATE)
        assert 'off' == state.attributes.get('aux_heat')

        common.set_aux_heat(self.hass, True, ENTITY_CLIMATE)
        self.hass.block_till_done()
        state = self.hass.states.get(ENTITY_CLIMATE)
        assert 'off' == state.attributes.get('aux_heat')

        fire_mqtt_message(self.hass, 'aux-state', 'ON')
        self.hass.block_till_done()
        state = self.hass.states.get(ENTITY_CLIMATE)
        assert 'on' == state.attributes.get('aux_heat')

        fire_mqtt_message(self.hass, 'aux-state', 'OFF')
        self.hass.block_till_done()
        state = self.hass.states.get(ENTITY_CLIMATE)
        assert 'off' == state.attributes.get('aux_heat')

        fire_mqtt_message(self.hass, 'aux-state', 'nonsense')
        self.hass.block_till_done()
        state = self.hass.states.get(ENTITY_CLIMATE)
        assert 'off' == state.attributes.get('aux_heat')

    def test_set_aux(self):
        """Test setting of the aux heating."""
        assert setup_component(self.hass, climate.DOMAIN, DEFAULT_CONFIG)

        state = self.hass.states.get(ENTITY_CLIMATE)
        assert 'off' == state.attributes.get('aux_heat')
        common.set_aux_heat(self.hass, True, ENTITY_CLIMATE)
        self.hass.block_till_done()
        self.mock_publish.async_publish.assert_called_once_with(
            'aux-topic', 'ON', 0, False)
        self.mock_publish.async_publish.reset_mock()
        state = self.hass.states.get(ENTITY_CLIMATE)
        assert 'on' == state.attributes.get('aux_heat')

        common.set_aux_heat(self.hass, False, ENTITY_CLIMATE)
        self.hass.block_till_done()
        self.mock_publish.async_publish.assert_called_once_with(
            'aux-topic', 'OFF', 0, False)
        state = self.hass.states.get(ENTITY_CLIMATE)
        assert 'off' == state.attributes.get('aux_heat')

    def test_custom_availability_payload(self):
        """Test availability by custom payload with defined topic."""
        config = copy.deepcopy(DEFAULT_CONFIG)
        config['climate']['availability_topic'] = 'availability-topic'
        config['climate']['payload_available'] = 'good'
        config['climate']['payload_not_available'] = 'nogood'

        assert setup_component(self.hass, climate.DOMAIN, config)

        state = self.hass.states.get('climate.test')
        assert STATE_UNAVAILABLE == state.state

        fire_mqtt_message(self.hass, 'availability-topic', 'good')
        self.hass.block_till_done()

        state = self.hass.states.get('climate.test')
        assert STATE_UNAVAILABLE != state.state

        fire_mqtt_message(self.hass, 'availability-topic', 'nogood')
        self.hass.block_till_done()

        state = self.hass.states.get('climate.test')
        assert STATE_UNAVAILABLE == state.state

    def test_set_with_templates(self):
        """Test setting of new fan mode in pessimistic mode."""
        config = copy.deepcopy(DEFAULT_CONFIG)
        # By default, just unquote the JSON-strings
        config['climate']['value_template'] = '{{ value_json }}'
        # Something more complicated for hold mode
        config['climate']['hold_state_template'] = \
            '{{ value_json.attribute }}'
        # Rendering to a bool for aux heat
        config['climate']['aux_state_template'] = \
            "{{ value == 'switchmeon' }}"

        config['climate']['mode_state_topic'] = 'mode-state'
        config['climate']['fan_mode_state_topic'] = 'fan-state'
        config['climate']['swing_mode_state_topic'] = 'swing-state'
        config['climate']['temperature_state_topic'] = 'temperature-state'
        config['climate']['away_mode_state_topic'] = 'away-state'
        config['climate']['hold_state_topic'] = 'hold-state'
        config['climate']['aux_state_topic'] = 'aux-state'
        config['climate']['current_temperature_topic'] = 'current-temperature'

        assert setup_component(self.hass, climate.DOMAIN, config)

        # Operation Mode
        state = self.hass.states.get(ENTITY_CLIMATE)
        assert state.attributes.get('operation_mode') is None
        fire_mqtt_message(self.hass, 'mode-state', '"cool"')
        self.hass.block_till_done()
        state = self.hass.states.get(ENTITY_CLIMATE)
        assert "cool" == state.attributes.get('operation_mode')

        # Fan Mode
        assert state.attributes.get('fan_mode') is None
        fire_mqtt_message(self.hass, 'fan-state', '"high"')
        self.hass.block_till_done()
        state = self.hass.states.get(ENTITY_CLIMATE)
        assert 'high' == state.attributes.get('fan_mode')

        # Swing Mode
        assert state.attributes.get('swing_mode') is None
        fire_mqtt_message(self.hass, 'swing-state', '"on"')
        self.hass.block_till_done()
        state = self.hass.states.get(ENTITY_CLIMATE)
        assert "on" == state.attributes.get('swing_mode')

        # Temperature - with valid value
        assert state.attributes.get('temperature') is None
        fire_mqtt_message(self.hass, 'temperature-state', '"1031"')
        self.hass.block_till_done()
        state = self.hass.states.get(ENTITY_CLIMATE)
        assert 1031 == state.attributes.get('temperature')

        # Temperature - with invalid value
        with self.assertLogs(level='ERROR') as log:
            fire_mqtt_message(self.hass, 'temperature-state', '"-INVALID-"')
            self.hass.block_till_done()
            state = self.hass.states.get(ENTITY_CLIMATE)
            # make sure, the invalid value gets logged...
            assert len(log.output) == 1
            assert len(log.records) == 1
            assert "Could not parse temperature from -INVALID-" in \
                log.output[0]
            # ... but the actual value stays unchanged.
            assert 1031 == state.attributes.get('temperature')

        # Away Mode
        assert 'off' == state.attributes.get('away_mode')
        fire_mqtt_message(self.hass, 'away-state', '"ON"')
        self.hass.block_till_done()
        state = self.hass.states.get(ENTITY_CLIMATE)
        assert 'on' == state.attributes.get('away_mode')

        # Away Mode with JSON values
        fire_mqtt_message(self.hass, 'away-state', 'false')
        self.hass.block_till_done()
        state = self.hass.states.get(ENTITY_CLIMATE)
        assert 'off' == state.attributes.get('away_mode')

        fire_mqtt_message(self.hass, 'away-state', 'true')
        self.hass.block_till_done()
        state = self.hass.states.get(ENTITY_CLIMATE)
        assert 'on' == state.attributes.get('away_mode')

        # Hold Mode
        assert state.attributes.get('hold_mode') is None
        fire_mqtt_message(self.hass, 'hold-state', """
            { "attribute": "somemode" }
        """)
        self.hass.block_till_done()
        state = self.hass.states.get(ENTITY_CLIMATE)
        assert 'somemode' == state.attributes.get('hold_mode')

        # Aux mode
        assert 'off' == state.attributes.get('aux_heat')
        fire_mqtt_message(self.hass, 'aux-state', 'switchmeon')
        self.hass.block_till_done()
        state = self.hass.states.get(ENTITY_CLIMATE)
        assert 'on' == state.attributes.get('aux_heat')

        # anything other than 'switchmeon' should turn Aux mode off
        fire_mqtt_message(self.hass, 'aux-state', 'somerandomstring')
        self.hass.block_till_done()
        state = self.hass.states.get(ENTITY_CLIMATE)
        assert 'off' == state.attributes.get('aux_heat')

        # Current temperature
        fire_mqtt_message(self.hass, 'current-temperature', '"74656"')
        self.hass.block_till_done()
        state = self.hass.states.get(ENTITY_CLIMATE)
        assert 74656 == state.attributes.get('current_temperature')

    def test_min_temp_custom(self):
        """Test a custom min temp."""
        config = copy.deepcopy(DEFAULT_CONFIG)
        config['climate']['min_temp'] = 26

        assert setup_component(self.hass, climate.DOMAIN, config)

        state = self.hass.states.get(ENTITY_CLIMATE)
        min_temp = state.attributes.get('min_temp')

        assert isinstance(min_temp, float)
        assert 26 == state.attributes.get('min_temp')

    def test_max_temp_custom(self):
        """Test a custom max temp."""
        config = copy.deepcopy(DEFAULT_CONFIG)
        config['climate']['max_temp'] = 60

        assert setup_component(self.hass, climate.DOMAIN, config)

        state = self.hass.states.get(ENTITY_CLIMATE)
        max_temp = state.attributes.get('max_temp')

        assert isinstance(max_temp, float)
        assert 60 == max_temp

    def test_temp_step_custom(self):
        """Test a custom temp step."""
        config = copy.deepcopy(DEFAULT_CONFIG)
        config['climate']['temp_step'] = 0.01

        assert setup_component(self.hass, climate.DOMAIN, config)

        state = self.hass.states.get(ENTITY_CLIMATE)
        temp_step = state.attributes.get('target_temp_step')

        assert isinstance(temp_step, float)
        assert 0.01 == temp_step


async def test_setting_attribute_via_mqtt_json_message(hass, mqtt_mock):
    """Test the setting of attribute via MQTT with JSON payload."""
    assert await async_setup_component(hass, climate.DOMAIN, {
        climate.DOMAIN: {
            'platform': 'mqtt',
            'name': 'test',
            'power_state_topic': 'test-topic',
            'power_command_topic': 'test_topic',
            'json_attributes_topic': 'attr-topic'
        }
    })

    async_fire_mqtt_message(hass, 'attr-topic', '{ "val": "100" }')
    await hass.async_block_till_done()
    state = hass.states.get('climate.test')

    assert '100' == state.attributes.get('val')


async def test_update_with_json_attrs_not_dict(hass, mqtt_mock, caplog):
    """Test attributes get extracted from a JSON result."""
    assert await async_setup_component(hass, climate.DOMAIN, {
        climate.DOMAIN: {
            'platform': 'mqtt',
            'name': 'test',
            'power_state_topic': 'test-topic',
            'power_command_topic': 'test_topic',
            'json_attributes_topic': 'attr-topic'
        }
    })

    async_fire_mqtt_message(hass, 'attr-topic', '[ "list", "of", "things"]')
    await hass.async_block_till_done()
    state = hass.states.get('climate.test')

    assert state.attributes.get('val') is None
    assert 'JSON result was not a dictionary' in caplog.text


async def test_update_with_json_attrs_bad_JSON(hass, mqtt_mock, caplog):
    """Test attributes get extracted from a JSON result."""
    assert await async_setup_component(hass, climate.DOMAIN, {
        climate.DOMAIN: {
            'platform': 'mqtt',
            'name': 'test',
            'power_state_topic': 'test-topic',
            'power_command_topic': 'test_topic',
            'json_attributes_topic': 'attr-topic'
        }
    })

    async_fire_mqtt_message(hass, 'attr-topic', 'This is not JSON')
    await hass.async_block_till_done()

    state = hass.states.get('climate.test')
    assert state.attributes.get('val') is None
    assert 'Erroneous JSON: This is not JSON' in caplog.text


async def test_discovery_update_attr(hass, mqtt_mock, caplog):
    """Test update of discovered MQTTAttributes."""
    entry = MockConfigEntry(domain=mqtt.DOMAIN)
    await async_start(hass, 'homeassistant', {}, entry)
    data1 = (
        '{ "name": "Beer",'
        '  "power_state_topic": "test-topic",'
        '  "power_command_topic": "test_topic",'
        '  "json_attributes_topic": "attr-topic1" }'
    )
    data2 = (
        '{ "name": "Beer",'
        '  "power_state_topic": "test-topic",'
        '  "power_command_topic": "test_topic",'
        '  "json_attributes_topic": "attr-topic2" }'
    )
    async_fire_mqtt_message(hass, 'homeassistant/climate/bla/config',
                            data1)
    await hass.async_block_till_done()
    async_fire_mqtt_message(hass, 'attr-topic1', '{ "val": "100" }')
    await hass.async_block_till_done()
    await hass.async_block_till_done()
    state = hass.states.get('climate.beer')
    assert '100' == state.attributes.get('val')

    # Change json_attributes_topic
    async_fire_mqtt_message(hass, 'homeassistant/climate/bla/config',
                            data2)
    await hass.async_block_till_done()
    await hass.async_block_till_done()

    # Verify we are no longer subscribing to the old topic
    async_fire_mqtt_message(hass, 'attr-topic1', '{ "val": "50" }')
    await hass.async_block_till_done()
    await hass.async_block_till_done()
    state = hass.states.get('climate.beer')
    assert '100' == state.attributes.get('val')

    # Verify we are subscribing to the new topic
    async_fire_mqtt_message(hass, 'attr-topic2', '{ "val": "75" }')
    await hass.async_block_till_done()
    await hass.async_block_till_done()
    state = hass.states.get('climate.beer')
    assert '75' == state.attributes.get('val')


async def test_unique_id(hass):
    """Test unique id option only creates one climate per unique_id."""
    await async_mock_mqtt_component(hass)
    assert await async_setup_component(hass, climate.DOMAIN, {
        climate.DOMAIN: [{
            'platform': 'mqtt',
            'name': 'Test 1',
            'power_state_topic': 'test-topic',
            'power_command_topic': 'test_topic',
            'unique_id': 'TOTALLY_UNIQUE'
        }, {
            'platform': 'mqtt',
            'name': 'Test 2',
            'power_state_topic': 'test-topic',
            'power_command_topic': 'test_topic',
            'unique_id': 'TOTALLY_UNIQUE'
        }]
    })
    async_fire_mqtt_message(hass, 'test-topic', 'payload')
    await hass.async_block_till_done()
    assert len(hass.states.async_entity_ids(climate.DOMAIN)) == 1


async def test_discovery_removal_climate(hass, mqtt_mock, caplog):
    """Test removal of discovered climate."""
    entry = MockConfigEntry(domain=mqtt.DOMAIN)
    await async_start(hass, 'homeassistant', {}, entry)
    data = (
        '{ "name": "Beer" }'
    )
    async_fire_mqtt_message(hass, 'homeassistant/climate/bla/config',
                            data)
    await hass.async_block_till_done()
    state = hass.states.get('climate.beer')
    assert state is not None
    assert state.name == 'Beer'
    async_fire_mqtt_message(hass, 'homeassistant/climate/bla/config',
                            '')
    await hass.async_block_till_done()
    await hass.async_block_till_done()
    state = hass.states.get('climate.beer')
    assert state is None


async def test_discovery_update_climate(hass, mqtt_mock, caplog):
    """Test update of discovered climate."""
    entry = MockConfigEntry(domain=mqtt.DOMAIN)
    await async_start(hass, 'homeassistant', {}, entry)
    data1 = (
        '{ "name": "Beer" }'
    )
    data2 = (
        '{ "name": "Milk" }'
    )
    async_fire_mqtt_message(hass, 'homeassistant/climate/bla/config',
                            data1)
    await hass.async_block_till_done()

    state = hass.states.get('climate.beer')
    assert state is not None
    assert state.name == 'Beer'

    async_fire_mqtt_message(hass, 'homeassistant/climate/bla/config',
                            data2)
    await hass.async_block_till_done()
    await hass.async_block_till_done()

    state = hass.states.get('climate.beer')
    assert state is not None
    assert state.name == 'Milk'

    state = hass.states.get('climate.milk')
    assert state is None


async def test_discovery_broken(hass, mqtt_mock, caplog):
    """Test handling of bad discovery message."""
    entry = MockConfigEntry(domain=mqtt.DOMAIN)
    await async_start(hass, 'homeassistant', {}, entry)

    data1 = (
        '{ "name": "Beer",'
        '  "power_command_topic": "test_topic#" }'
    )
    data2 = (
        '{ "name": "Milk", '
        '  "power_command_topic": "test_topic" }'
    )

    async_fire_mqtt_message(hass, 'homeassistant/climate/bla/config',
                            data1)
    await hass.async_block_till_done()

    state = hass.states.get('climate.beer')
    assert state is None

    async_fire_mqtt_message(hass, 'homeassistant/climate/bla/config',
                            data2)
    await hass.async_block_till_done()
    await hass.async_block_till_done()

    state = hass.states.get('climate.milk')
    assert state is not None
    assert state.name == 'Milk'
    state = hass.states.get('climate.beer')
    assert state is None


async def test_entity_device_info_with_identifier(hass, mqtt_mock):
    """Test MQTT climate device registry integration."""
    entry = MockConfigEntry(domain=mqtt.DOMAIN)
    entry.add_to_hass(hass)
    await async_start(hass, 'homeassistant', {}, entry)
    registry = await hass.helpers.device_registry.async_get_registry()

    data = json.dumps({
        'platform': 'mqtt',
        'name': 'Test 1',
        'device': {
            'identifiers': ['helloworld'],
            'connections': [
                ["mac", "02:5b:26:a8:dc:12"],
            ],
            'manufacturer': 'Whatever',
            'name': 'Beer',
            'model': 'Glass',
            'sw_version': '0.1-beta',
        },
        'unique_id': 'veryunique'
    })
    async_fire_mqtt_message(hass, 'homeassistant/climate/bla/config',
                            data)
    await hass.async_block_till_done()
    await hass.async_block_till_done()

    device = registry.async_get_device({('mqtt', 'helloworld')}, set())
    assert device is not None
    assert device.identifiers == {('mqtt', 'helloworld')}
    assert device.connections == {('mac', "02:5b:26:a8:dc:12")}
    assert device.manufacturer == 'Whatever'
    assert device.name == 'Beer'
    assert device.model == 'Glass'
    assert device.sw_version == '0.1-beta'


async def test_entity_device_info_update(hass, mqtt_mock):
    """Test device registry update."""
    entry = MockConfigEntry(domain=mqtt.DOMAIN)
    entry.add_to_hass(hass)
    await async_start(hass, 'homeassistant', {}, entry)
    registry = await hass.helpers.device_registry.async_get_registry()

    config = {
        'platform': 'mqtt',
        'name': 'Test 1',
        'power_state_topic': 'test-topic',
        'power_command_topic': 'test-command-topic',
        'device': {
            'identifiers': ['helloworld'],
            'connections': [
                ["mac", "02:5b:26:a8:dc:12"],
            ],
            'manufacturer': 'Whatever',
            'name': 'Beer',
            'model': 'Glass',
            'sw_version': '0.1-beta',
        },
        'unique_id': 'veryunique'
    }

    data = json.dumps(config)
    async_fire_mqtt_message(hass, 'homeassistant/climate/bla/config',
                            data)
    await hass.async_block_till_done()
    await hass.async_block_till_done()

    device = registry.async_get_device({('mqtt', 'helloworld')}, set())
    assert device is not None
    assert device.name == 'Beer'

    config['device']['name'] = 'Milk'
    data = json.dumps(config)
    async_fire_mqtt_message(hass, 'homeassistant/climate/bla/config',
                            data)
    await hass.async_block_till_done()
    await hass.async_block_till_done()

    device = registry.async_get_device({('mqtt', 'helloworld')}, set())
    assert device is not None
    assert device.name == 'Milk'


async def test_entity_id_update(hass, mqtt_mock):
    """Test MQTT subscriptions are managed when entity_id is updated."""
    registry = mock_registry(hass, {})
    mock_mqtt = await async_mock_mqtt_component(hass)
    assert await async_setup_component(hass, climate.DOMAIN, {
        climate.DOMAIN: [{
            'platform': 'mqtt',
            'name': 'beer',
            'mode_state_topic': 'test-topic',
            'availability_topic': 'avty-topic',
            'unique_id': 'TOTALLY_UNIQUE'
        }]
    })

    state = hass.states.get('climate.beer')
    assert state is not None
    assert mock_mqtt.async_subscribe.call_count == 2
    mock_mqtt.async_subscribe.assert_any_call('test-topic', ANY, 0, 'utf-8')
    mock_mqtt.async_subscribe.assert_any_call('avty-topic', ANY, 0, 'utf-8')
    mock_mqtt.async_subscribe.reset_mock()

    registry.async_update_entity('climate.beer', new_entity_id='climate.milk')
    await hass.async_block_till_done()
    await hass.async_block_till_done()

    state = hass.states.get('climate.beer')
    assert state is None

    state = hass.states.get('climate.milk')
    assert state is not None
    assert mock_mqtt.async_subscribe.call_count == 2
    mock_mqtt.async_subscribe.assert_any_call('test-topic', ANY, 0, 'utf-8')
    mock_mqtt.async_subscribe.assert_any_call('avty-topic', ANY, 0, 'utf-8')
