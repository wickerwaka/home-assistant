"""The tests for the MQTT cover platform."""
import json
import unittest
from unittest.mock import ANY

from homeassistant.components import cover, mqtt
from homeassistant.components.cover import ATTR_POSITION, ATTR_TILT_POSITION
from homeassistant.components.mqtt.cover import MqttCover
from homeassistant.components.mqtt.discovery import async_start
from homeassistant.const import (
    ATTR_ASSUMED_STATE, ATTR_ENTITY_ID, SERVICE_CLOSE_COVER,
    SERVICE_CLOSE_COVER_TILT, SERVICE_OPEN_COVER, SERVICE_OPEN_COVER_TILT,
    SERVICE_SET_COVER_POSITION, SERVICE_SET_COVER_TILT_POSITION,
    SERVICE_STOP_COVER, STATE_CLOSED, STATE_OPEN, STATE_UNAVAILABLE,
    STATE_UNKNOWN)
from homeassistant.setup import async_setup_component, setup_component

from tests.common import (
    MockConfigEntry, async_fire_mqtt_message, async_mock_mqtt_component,
    fire_mqtt_message, get_test_home_assistant, mock_mqtt_component,
    mock_registry)


class TestCoverMQTT(unittest.TestCase):
    """Test the MQTT cover."""

    def setUp(self):  # pylint: disable=invalid-name
        """Set up things to be run when tests are started."""
        self.hass = get_test_home_assistant()
        self.mock_publish = mock_mqtt_component(self.hass)

    def tearDown(self):  # pylint: disable=invalid-name
        """Stop down everything that was started."""
        self.hass.stop()

    def test_state_via_state_topic(self):
        """Test the controlling state via topic."""
        assert setup_component(self.hass, cover.DOMAIN, {
            cover.DOMAIN: {
                'platform': 'mqtt',
                'name': 'test',
                'state_topic': 'state-topic',
                'command_topic': 'command-topic',
                'qos': 0,
                'payload_open': 'OPEN',
                'payload_close': 'CLOSE',
                'payload_stop': 'STOP'
            }
        })

        state = self.hass.states.get('cover.test')
        assert STATE_UNKNOWN == state.state
        assert not state.attributes.get(ATTR_ASSUMED_STATE)

        fire_mqtt_message(self.hass, 'state-topic', STATE_CLOSED)
        self.hass.block_till_done()

        state = self.hass.states.get('cover.test')
        assert STATE_CLOSED == state.state

        fire_mqtt_message(self.hass, 'state-topic', STATE_OPEN)
        self.hass.block_till_done()

        state = self.hass.states.get('cover.test')
        assert STATE_OPEN == state.state

    def test_position_via_position_topic(self):
        """Test the controlling state via topic."""
        self.assertTrue(setup_component(self.hass, cover.DOMAIN, {
            cover.DOMAIN: {
                'platform': 'mqtt',
                'name': 'test',
                'position_topic': 'get-position-topic',
                'position_open': 100,
                'position_closed': 0,
                'command_topic': 'command-topic',
                'qos': 0,
                'payload_open': 'OPEN',
                'payload_close': 'CLOSE',
                'payload_stop': 'STOP'
            }
        }))

        state = self.hass.states.get('cover.test')
        assert STATE_UNKNOWN == state.state
        assert not state.attributes.get(ATTR_ASSUMED_STATE)

        fire_mqtt_message(self.hass, 'get-position-topic', '0')
        self.hass.block_till_done()

        state = self.hass.states.get('cover.test')
        assert STATE_CLOSED == state.state

        fire_mqtt_message(self.hass, 'get-position-topic', '100')
        self.hass.block_till_done()

        state = self.hass.states.get('cover.test')
        assert STATE_OPEN == state.state

    def test_state_via_template(self):
        """Test the controlling state via topic."""
        assert setup_component(self.hass, cover.DOMAIN, {
            cover.DOMAIN: {
                'platform': 'mqtt',
                'name': 'test',
                'state_topic': 'state-topic',
                'command_topic': 'command-topic',
                'qos': 0,
                'value_template': '\
                    {% if (value | multiply(0.01) | int) == 0  %}\
                      closed\
                    {% else %}\
                      open\
                    {% endif %}'
            }
        })

        state = self.hass.states.get('cover.test')
        assert STATE_UNKNOWN == state.state

        fire_mqtt_message(self.hass, 'state-topic', '10000')
        self.hass.block_till_done()

        state = self.hass.states.get('cover.test')
        assert STATE_OPEN == state.state

        fire_mqtt_message(self.hass, 'state-topic', '99')
        self.hass.block_till_done()

        state = self.hass.states.get('cover.test')
        assert STATE_CLOSED == state.state

    def test_position_via_template(self):
        """Test the controlling state via topic."""
        self.assertTrue(setup_component(self.hass, cover.DOMAIN, {
            cover.DOMAIN: {
                'platform': 'mqtt',
                'name': 'test',
                'position_topic': 'get-position-topic',
                'command_topic': 'command-topic',
                'qos': 0,
                'value_template': '{{ (value | multiply(0.01)) | int }}'
            }
        }))

        state = self.hass.states.get('cover.test')
        self.assertEqual(STATE_UNKNOWN, state.state)

        fire_mqtt_message(self.hass, 'get-position-topic', '10000')
        self.hass.block_till_done()

        state = self.hass.states.get('cover.test')
        self.assertEqual(STATE_OPEN, state.state)

        fire_mqtt_message(self.hass, 'get-position-topic', '5000')
        self.hass.block_till_done()

        state = self.hass.states.get('cover.test')
        self.assertEqual(STATE_OPEN, state.state)

        fire_mqtt_message(self.hass, 'get-position-topic', '99')
        self.hass.block_till_done()

        state = self.hass.states.get('cover.test')
        self.assertEqual(STATE_CLOSED, state.state)

    def test_optimistic_state_change(self):
        """Test changing state optimistically."""
        assert setup_component(self.hass, cover.DOMAIN, {
            cover.DOMAIN: {
                'platform': 'mqtt',
                'name': 'test',
                'command_topic': 'command-topic',
                'qos': 0,
            }
        })

        state = self.hass.states.get('cover.test')
        assert STATE_UNKNOWN == state.state
        assert state.attributes.get(ATTR_ASSUMED_STATE)

        self.hass.services.call(
            cover.DOMAIN, SERVICE_OPEN_COVER,
            {ATTR_ENTITY_ID: 'cover.test'}, blocking=True)
        self.hass.block_till_done()

        self.mock_publish.async_publish.assert_called_once_with(
            'command-topic', 'OPEN', 0, False)
        self.mock_publish.async_publish.reset_mock()
        state = self.hass.states.get('cover.test')
        assert STATE_OPEN == state.state

        self.hass.services.call(
            cover.DOMAIN, SERVICE_CLOSE_COVER,
            {ATTR_ENTITY_ID: 'cover.test'}, blocking=True)
        self.hass.block_till_done()

        self.mock_publish.async_publish.assert_called_once_with(
            'command-topic', 'CLOSE', 0, False)
        state = self.hass.states.get('cover.test')
        assert STATE_CLOSED == state.state

    def test_send_open_cover_command(self):
        """Test the sending of open_cover."""
        assert setup_component(self.hass, cover.DOMAIN, {
            cover.DOMAIN: {
                'platform': 'mqtt',
                'name': 'test',
                'state_topic': 'state-topic',
                'command_topic': 'command-topic',
                'qos': 2
            }
        })

        state = self.hass.states.get('cover.test')
        assert STATE_UNKNOWN == state.state

        self.hass.services.call(
            cover.DOMAIN, SERVICE_OPEN_COVER,
            {ATTR_ENTITY_ID: 'cover.test'}, blocking=True)
        self.hass.block_till_done()

        self.mock_publish.async_publish.assert_called_once_with(
            'command-topic', 'OPEN', 2, False)
        state = self.hass.states.get('cover.test')
        assert STATE_UNKNOWN == state.state

    def test_send_close_cover_command(self):
        """Test the sending of close_cover."""
        assert setup_component(self.hass, cover.DOMAIN, {
            cover.DOMAIN: {
                'platform': 'mqtt',
                'name': 'test',
                'state_topic': 'state-topic',
                'command_topic': 'command-topic',
                'qos': 2
            }
        })

        state = self.hass.states.get('cover.test')
        assert STATE_UNKNOWN == state.state

        self.hass.services.call(
            cover.DOMAIN, SERVICE_CLOSE_COVER,
            {ATTR_ENTITY_ID: 'cover.test'}, blocking=True)
        self.hass.block_till_done()

        self.mock_publish.async_publish.assert_called_once_with(
            'command-topic', 'CLOSE', 2, False)
        state = self.hass.states.get('cover.test')
        assert STATE_UNKNOWN == state.state

    def test_send_stop__cover_command(self):
        """Test the sending of stop_cover."""
        assert setup_component(self.hass, cover.DOMAIN, {
            cover.DOMAIN: {
                'platform': 'mqtt',
                'name': 'test',
                'state_topic': 'state-topic',
                'command_topic': 'command-topic',
                'qos': 2
            }
        })

        state = self.hass.states.get('cover.test')
        assert STATE_UNKNOWN == state.state

        self.hass.services.call(
            cover.DOMAIN, SERVICE_STOP_COVER,
            {ATTR_ENTITY_ID: 'cover.test'}, blocking=True)
        self.hass.block_till_done()

        self.mock_publish.async_publish.assert_called_once_with(
            'command-topic', 'STOP', 2, False)
        state = self.hass.states.get('cover.test')
        assert STATE_UNKNOWN == state.state

    def test_current_cover_position(self):
        """Test the current cover position."""
        assert setup_component(self.hass, cover.DOMAIN, {
            cover.DOMAIN: {
                'platform': 'mqtt',
                'name': 'test',
                'position_topic': 'get-position-topic',
                'command_topic': 'command-topic',
                'position_open': 100,
                'position_closed': 0,
                'payload_open': 'OPEN',
                'payload_close': 'CLOSE',
                'payload_stop': 'STOP'
            }
        })

        state_attributes_dict = self.hass.states.get(
            'cover.test').attributes
        assert not ('current_position' in state_attributes_dict)
        assert not ('current_tilt_position' in state_attributes_dict)
        assert not (4 & self.hass.states.get(
            'cover.test').attributes['supported_features'] == 4)

        fire_mqtt_message(self.hass, 'get-position-topic', '0')
        self.hass.block_till_done()
        current_cover_position = self.hass.states.get(
            'cover.test').attributes['current_position']
        assert 0 == current_cover_position

        fire_mqtt_message(self.hass, 'get-position-topic', '50')
        self.hass.block_till_done()
        current_cover_position = self.hass.states.get(
            'cover.test').attributes['current_position']
        assert 50 == current_cover_position

        fire_mqtt_message(self.hass, 'get-position-topic', 'non-numeric')
        self.hass.block_till_done()
        current_cover_position = self.hass.states.get(
            'cover.test').attributes['current_position']
        assert 50 == current_cover_position

        fire_mqtt_message(self.hass, 'get-position-topic', '101')
        self.hass.block_till_done()
        current_cover_position = self.hass.states.get(
            'cover.test').attributes['current_position']
        assert 100 == current_cover_position

    def test_current_cover_position_inverted(self):
        """Test the current cover position."""
        assert setup_component(self.hass, cover.DOMAIN, {
            cover.DOMAIN: {
                'platform': 'mqtt',
                'name': 'test',
                'position_topic': 'get-position-topic',
                'command_topic': 'command-topic',
                'position_open': 0,
                'position_closed': 100,
                'payload_open': 'OPEN',
                'payload_close': 'CLOSE',
                'payload_stop': 'STOP'
            }
        })

        state_attributes_dict = self.hass.states.get(
            'cover.test').attributes
        assert not ('current_position' in state_attributes_dict)
        assert not ('current_tilt_position' in state_attributes_dict)
        assert not (4 & self.hass.states.get(
            'cover.test').attributes['supported_features'] == 4)

        fire_mqtt_message(self.hass, 'get-position-topic', '100')
        self.hass.block_till_done()
        current_percentage_cover_position = self.hass.states.get(
            'cover.test').attributes['current_position']
        assert 0 == current_percentage_cover_position
        assert STATE_CLOSED == self.hass.states.get(
            'cover.test').state

        fire_mqtt_message(self.hass, 'get-position-topic', '0')
        self.hass.block_till_done()
        current_percentage_cover_position = self.hass.states.get(
            'cover.test').attributes['current_position']
        assert 100 == current_percentage_cover_position
        assert STATE_OPEN == self.hass.states.get(
            'cover.test').state

        fire_mqtt_message(self.hass, 'get-position-topic', '50')
        self.hass.block_till_done()
        current_percentage_cover_position = self.hass.states.get(
            'cover.test').attributes['current_position']
        assert 50 == current_percentage_cover_position
        assert STATE_OPEN == self.hass.states.get(
            'cover.test').state

        fire_mqtt_message(self.hass, 'get-position-topic', 'non-numeric')
        self.hass.block_till_done()
        current_percentage_cover_position = self.hass.states.get(
            'cover.test').attributes['current_position']
        assert 50 == current_percentage_cover_position
        assert STATE_OPEN == self.hass.states.get(
            'cover.test').state

        fire_mqtt_message(self.hass, 'get-position-topic', '101')
        self.hass.block_till_done()
        current_percentage_cover_position = self.hass.states.get(
            'cover.test').attributes['current_position']
        assert 0 == current_percentage_cover_position
        assert STATE_CLOSED == self.hass.states.get(
            'cover.test').state

    def test_set_cover_position(self):
        """Test setting cover position."""
        assert setup_component(self.hass, cover.DOMAIN, {
            cover.DOMAIN: {
                'platform': 'mqtt',
                'name': 'test',
                'position_topic': 'get-position-topic',
                'command_topic': 'command-topic',
                'set_position_topic': 'set-position-topic',
                'position_open': 100,
                'position_closed': 0,
                'payload_open': 'OPEN',
                'payload_close': 'CLOSE',
                'payload_stop': 'STOP'
            }
        })

        state_attributes_dict = self.hass.states.get(
            'cover.test').attributes
        assert not ('current_position' in state_attributes_dict)
        assert not ('current_tilt_position' in state_attributes_dict)
        assert 4 & self.hass.states.get(
            'cover.test').attributes['supported_features'] == 4

        fire_mqtt_message(self.hass, 'get-position-topic', '22')
        self.hass.block_till_done()
        state_attributes_dict = self.hass.states.get(
            'cover.test').attributes
        assert 'current_position' in state_attributes_dict
        assert not ('current_tilt_position' in state_attributes_dict)
        current_cover_position = self.hass.states.get(
            'cover.test').attributes['current_position']
        assert 22 == current_cover_position

    def test_set_position_templated(self):
        """Test setting cover position via template."""
        assert setup_component(self.hass, cover.DOMAIN, {
            cover.DOMAIN: {
                'platform': 'mqtt',
                'name': 'test',
                'position_topic': 'get-position-topic',
                'command_topic': 'command-topic',
                'position_open': 100,
                'position_closed': 0,
                'set_position_topic': 'set-position-topic',
                'set_position_template': '{{100-62}}',
                'payload_open': 'OPEN',
                'payload_close': 'CLOSE',
                'payload_stop': 'STOP'
            }
        })

        self.hass.services.call(
            cover.DOMAIN, SERVICE_SET_COVER_POSITION,
            {ATTR_ENTITY_ID: 'cover.test', ATTR_POSITION: 100}, blocking=True)
        self.hass.block_till_done()

        self.mock_publish.async_publish.assert_called_once_with(
            'set-position-topic', '38', 0, False)

    def test_set_position_untemplated(self):
        """Test setting cover position via template."""
        assert setup_component(self.hass, cover.DOMAIN, {
            cover.DOMAIN: {
                'platform': 'mqtt',
                'name': 'test',
                'position_topic': 'state-topic',
                'command_topic': 'command-topic',
                'set_position_topic': 'position-topic',
                'payload_open': 'OPEN',
                'payload_close': 'CLOSE',
                'payload_stop': 'STOP'
            }
        })

        self.hass.services.call(
            cover.DOMAIN, SERVICE_SET_COVER_POSITION,
            {ATTR_ENTITY_ID: 'cover.test', ATTR_POSITION: 62}, blocking=True)
        self.hass.block_till_done()

        self.mock_publish.async_publish.assert_called_once_with(
            'position-topic', 62, 0, False)

    def test_no_command_topic(self):
        """Test with no command topic."""
        assert setup_component(self.hass, cover.DOMAIN, {
            cover.DOMAIN: {
                'platform': 'mqtt',
                'name': 'test',
                'qos': 0,
                'payload_open': 'OPEN',
                'payload_close': 'CLOSE',
                'payload_stop': 'STOP',
                'tilt_command_topic': 'tilt-command',
                'tilt_status_topic': 'tilt-status'
            }
        })

        assert 240 == self.hass.states.get(
            'cover.test').attributes['supported_features']

    def test_with_command_topic_and_tilt(self):
        """Test with command topic and tilt config."""
        assert setup_component(self.hass, cover.DOMAIN, {
            cover.DOMAIN: {
                'command_topic': 'test',
                'platform': 'mqtt',
                'name': 'test',
                'qos': 0,
                'payload_open': 'OPEN',
                'payload_close': 'CLOSE',
                'payload_stop': 'STOP',
                'tilt_command_topic': 'tilt-command',
                'tilt_status_topic': 'tilt-status'
            }
        })

        assert 251 == self.hass.states.get(
            'cover.test').attributes['supported_features']

    def test_tilt_defaults(self):
        """Test the defaults."""
        assert setup_component(self.hass, cover.DOMAIN, {
            cover.DOMAIN: {
                'platform': 'mqtt',
                'name': 'test',
                'state_topic': 'state-topic',
                'command_topic': 'command-topic',
                'qos': 0,
                'payload_open': 'OPEN',
                'payload_close': 'CLOSE',
                'payload_stop': 'STOP',
                'tilt_command_topic': 'tilt-command',
                'tilt_status_topic': 'tilt-status'
            }
        })

        state_attributes_dict = self.hass.states.get(
            'cover.test').attributes
        assert 'current_tilt_position' in state_attributes_dict

        current_cover_position = self.hass.states.get(
            'cover.test').attributes['current_tilt_position']
        assert STATE_UNKNOWN == current_cover_position

    def test_tilt_via_invocation_defaults(self):
        """Test tilt defaults on close/open."""
        assert setup_component(self.hass, cover.DOMAIN, {
            cover.DOMAIN: {
                'platform': 'mqtt',
                'name': 'test',
                'state_topic': 'state-topic',
                'command_topic': 'command-topic',
                'qos': 0,
                'payload_open': 'OPEN',
                'payload_close': 'CLOSE',
                'payload_stop': 'STOP',
                'tilt_command_topic': 'tilt-command-topic',
                'tilt_status_topic': 'tilt-status-topic'
            }
        })

        self.hass.services.call(
            cover.DOMAIN, SERVICE_OPEN_COVER_TILT,
            {ATTR_ENTITY_ID: 'cover.test'}, blocking=True)
        self.hass.block_till_done()

        self.mock_publish.async_publish.assert_called_once_with(
            'tilt-command-topic', 100, 0, False)
        self.mock_publish.async_publish.reset_mock()

        self.hass.services.call(
            cover.DOMAIN, SERVICE_CLOSE_COVER_TILT,
            {ATTR_ENTITY_ID: 'cover.test'}, blocking=True)
        self.hass.block_till_done()

        self.mock_publish.async_publish.assert_called_once_with(
            'tilt-command-topic', 0, 0, False)

    def test_tilt_given_value(self):
        """Test tilting to a given value."""
        assert setup_component(self.hass, cover.DOMAIN, {
            cover.DOMAIN: {
                'platform': 'mqtt',
                'name': 'test',
                'state_topic': 'state-topic',
                'command_topic': 'command-topic',
                'qos': 0,
                'payload_open': 'OPEN',
                'payload_close': 'CLOSE',
                'payload_stop': 'STOP',
                'tilt_command_topic': 'tilt-command-topic',
                'tilt_status_topic': 'tilt-status-topic',
                'tilt_opened_value': 400,
                'tilt_closed_value': 125
            }
        })

        self.hass.services.call(
            cover.DOMAIN, SERVICE_OPEN_COVER_TILT,
            {ATTR_ENTITY_ID: 'cover.test'}, blocking=True)
        self.hass.block_till_done()

        self.mock_publish.async_publish.assert_called_once_with(
            'tilt-command-topic', 400, 0, False)
        self.mock_publish.async_publish.reset_mock()

        self.hass.services.call(
            cover.DOMAIN, SERVICE_CLOSE_COVER_TILT,
            {ATTR_ENTITY_ID: 'cover.test'}, blocking=True)
        self.hass.block_till_done()

        self.mock_publish.async_publish.assert_called_once_with(
            'tilt-command-topic', 125, 0, False)

    def test_tilt_via_topic(self):
        """Test tilt by updating status via MQTT."""
        assert setup_component(self.hass, cover.DOMAIN, {
            cover.DOMAIN: {
                'platform': 'mqtt',
                'name': 'test',
                'state_topic': 'state-topic',
                'command_topic': 'command-topic',
                'qos': 0,
                'payload_open': 'OPEN',
                'payload_close': 'CLOSE',
                'payload_stop': 'STOP',
                'tilt_command_topic': 'tilt-command-topic',
                'tilt_status_topic': 'tilt-status-topic',
                'tilt_opened_value': 400,
                'tilt_closed_value': 125
            }
        })

        fire_mqtt_message(self.hass, 'tilt-status-topic', '0')
        self.hass.block_till_done()

        current_cover_tilt_position = self.hass.states.get(
            'cover.test').attributes['current_tilt_position']
        assert 0 == current_cover_tilt_position

        fire_mqtt_message(self.hass, 'tilt-status-topic', '50')
        self.hass.block_till_done()

        current_cover_tilt_position = self.hass.states.get(
            'cover.test').attributes['current_tilt_position']
        assert 50 == current_cover_tilt_position

    def test_tilt_via_topic_altered_range(self):
        """Test tilt status via MQTT with altered tilt range."""
        assert setup_component(self.hass, cover.DOMAIN, {
            cover.DOMAIN: {
                'platform': 'mqtt',
                'name': 'test',
                'state_topic': 'state-topic',
                'command_topic': 'command-topic',
                'qos': 0,
                'payload_open': 'OPEN',
                'payload_close': 'CLOSE',
                'payload_stop': 'STOP',
                'tilt_command_topic': 'tilt-command-topic',
                'tilt_status_topic': 'tilt-status-topic',
                'tilt_opened_value': 400,
                'tilt_closed_value': 125,
                'tilt_min': 0,
                'tilt_max': 50
            }
        })

        fire_mqtt_message(self.hass, 'tilt-status-topic', '0')
        self.hass.block_till_done()

        current_cover_tilt_position = self.hass.states.get(
            'cover.test').attributes['current_tilt_position']
        assert 0 == current_cover_tilt_position

        fire_mqtt_message(self.hass, 'tilt-status-topic', '50')
        self.hass.block_till_done()

        current_cover_tilt_position = self.hass.states.get(
            'cover.test').attributes['current_tilt_position']
        assert 100 == current_cover_tilt_position

        fire_mqtt_message(self.hass, 'tilt-status-topic', '25')
        self.hass.block_till_done()

        current_cover_tilt_position = self.hass.states.get(
            'cover.test').attributes['current_tilt_position']
        assert 50 == current_cover_tilt_position

    def test_tilt_position(self):
        """Test tilt via method invocation."""
        assert setup_component(self.hass, cover.DOMAIN, {
            cover.DOMAIN: {
                'platform': 'mqtt',
                'name': 'test',
                'state_topic': 'state-topic',
                'command_topic': 'command-topic',
                'qos': 0,
                'payload_open': 'OPEN',
                'payload_close': 'CLOSE',
                'payload_stop': 'STOP',
                'tilt_command_topic': 'tilt-command-topic',
                'tilt_status_topic': 'tilt-status-topic',
                'tilt_opened_value': 400,
                'tilt_closed_value': 125
            }
        })

        self.hass.services.call(
            cover.DOMAIN, SERVICE_SET_COVER_TILT_POSITION,
            {ATTR_ENTITY_ID: 'cover.test', ATTR_TILT_POSITION: 50},
            blocking=True)
        self.hass.block_till_done()

        self.mock_publish.async_publish.assert_called_once_with(
            'tilt-command-topic', 50, 0, False)

    def test_tilt_position_altered_range(self):
        """Test tilt via method invocation with altered range."""
        assert setup_component(self.hass, cover.DOMAIN, {
            cover.DOMAIN: {
                'platform': 'mqtt',
                'name': 'test',
                'state_topic': 'state-topic',
                'command_topic': 'command-topic',
                'qos': 0,
                'payload_open': 'OPEN',
                'payload_close': 'CLOSE',
                'payload_stop': 'STOP',
                'tilt_command_topic': 'tilt-command-topic',
                'tilt_status_topic': 'tilt-status-topic',
                'tilt_opened_value': 400,
                'tilt_closed_value': 125,
                'tilt_min': 0,
                'tilt_max': 50
            }
        })

        self.hass.services.call(
            cover.DOMAIN, SERVICE_SET_COVER_TILT_POSITION,
            {ATTR_ENTITY_ID: 'cover.test', ATTR_TILT_POSITION: 50},
            blocking=True)
        self.hass.block_till_done()

        self.mock_publish.async_publish.assert_called_once_with(
            'tilt-command-topic', 25, 0, False)

    def test_find_percentage_in_range_defaults(self):
        """Test find percentage in range with default range."""
        mqtt_cover = MqttCover(
            {
                'name': 'cover.test',
                'state_topic': 'state-topic',
                'get_position_topic': None,
                'command_topic': 'command-topic',
                'availability_topic': None,
                'tilt_command_topic': 'tilt-command-topic',
                'tilt_status_topic': 'tilt-status-topic',
                'qos': 0,
                'retain': False,
                'state_open': 'OPEN', 'state_closed': 'CLOSE',
                'position_open': 100,  'position_closed': 0,
                'payload_open': 'OPEN', 'payload_close': 'CLOSE',
                'payload_stop': 'STOP',
                'payload_available': None, 'payload_not_available': None,
                'optimistic': False, 'value_template': None,
                'tilt_open_position': 100, 'tilt_closed_position': 0,
                'tilt_min': 0, 'tilt_max': 100, 'tilt_optimistic': False,
                'tilt_invert_state': False,
                'set_position_topic': None, 'set_position_template': None,
                'unique_id': None, 'device_config': None,
            },
            None,
            None)

        assert 44 == mqtt_cover.find_percentage_in_range(44)
        assert 44 == mqtt_cover.find_percentage_in_range(44, 'cover')

    def test_find_percentage_in_range_altered(self):
        """Test find percentage in range with altered range."""
        mqtt_cover = MqttCover(
            {
                'name': 'cover.test',
                'state_topic': 'state-topic',
                'get_position_topic': None,
                'command_topic': 'command-topic',
                'availability_topic': None,
                'tilt_command_topic': 'tilt-command-topic',
                'tilt_status_topic': 'tilt-status-topic',
                'qos': 0,
                'retain': False,
                'state_open': 'OPEN', 'state_closed': 'CLOSE',
                'position_open': 180,  'position_closed': 80,
                'payload_open': 'OPEN', 'payload_close': 'CLOSE',
                'payload_stop': 'STOP',
                'payload_available': None, 'payload_not_available': None,
                'optimistic': False, 'value_template': None,
                'tilt_open_position': 180, 'tilt_closed_position': 80,
                'tilt_min': 80, 'tilt_max': 180, 'tilt_optimistic': False,
                'tilt_invert_state': False,
                'set_position_topic': None, 'set_position_template': None,
                'unique_id': None, 'device_config': None,
            },
            None,
            None)

        assert 40 == mqtt_cover.find_percentage_in_range(120)
        assert 40 == mqtt_cover.find_percentage_in_range(120, 'cover')

    def test_find_percentage_in_range_defaults_inverted(self):
        """Test find percentage in range with default range but inverted."""
        mqtt_cover = MqttCover(
            {
                'name': 'cover.test',
                'state_topic': 'state-topic',
                'get_position_topic': None,
                'command_topic': 'command-topic',
                'availability_topic': None,
                'tilt_command_topic': 'tilt-command-topic',
                'tilt_status_topic': 'tilt-status-topic',
                'qos': 0,
                'retain': False,
                'state_open': 'OPEN', 'state_closed': 'CLOSE',
                'position_open': 0,  'position_closed': 100,
                'payload_open': 'OPEN', 'payload_close': 'CLOSE',
                'payload_stop': 'STOP',
                'payload_available': None, 'payload_not_available': None,
                'optimistic': False, 'value_template': None,
                'tilt_open_position': 100, 'tilt_closed_position': 0,
                'tilt_min': 0, 'tilt_max': 100, 'tilt_optimistic': False,
                'tilt_invert_state': True,
                'set_position_topic': None, 'set_position_template': None,
                'unique_id': None, 'device_config': None,
            },
            None,
            None)

        assert 56 == mqtt_cover.find_percentage_in_range(44)
        assert 56 == mqtt_cover.find_percentage_in_range(44, 'cover')

    def test_find_percentage_in_range_altered_inverted(self):
        """Test find percentage in range with altered range and inverted."""
        mqtt_cover = MqttCover(
            {
                'name': 'cover.test',
                'state_topic': 'state-topic',
                'get_position_topic': None,
                'command_topic': 'command-topic',
                'availability_topic': None,
                'tilt_command_topic': 'tilt-command-topic',
                'tilt_status_topic': 'tilt-status-topic',
                'qos': 0,
                'retain': False,
                'state_open': 'OPEN', 'state_closed': 'CLOSE',
                'position_open': 80,  'position_closed': 180,
                'payload_open': 'OPEN', 'payload_close': 'CLOSE',
                'payload_stop': 'STOP',
                'payload_available': None, 'payload_not_available': None,
                'optimistic': False, 'value_template': None,
                'tilt_open_position': 180, 'tilt_closed_position': 80,
                'tilt_min': 80, 'tilt_max': 180, 'tilt_optimistic': False,
                'tilt_invert_state': True,
                'set_position_topic': None, 'set_position_template': None,
                'unique_id': None, 'device_config': None,
            },
            None,
            None)

        assert 60 == mqtt_cover.find_percentage_in_range(120)
        assert 60 == mqtt_cover.find_percentage_in_range(120, 'cover')

    def test_find_in_range_defaults(self):
        """Test find in range with default range."""
        mqtt_cover = MqttCover(
            {
                'name': 'cover.test',
                'state_topic': 'state-topic',
                'get_position_topic': None,
                'command_topic': 'command-topic',
                'availability_topic': None,
                'tilt_command_topic': 'tilt-command-topic',
                'tilt_status_topic': 'tilt-status-topic',
                'qos': 0,
                'retain': False,
                'state_open': 'OPEN', 'state_closed': 'CLOSE',
                'position_open': 100, 'position_closed': 0,
                'payload_open': 'OPEN', 'payload_close': 'CLOSE',
                'payload_stop': 'STOP',
                'payload_available': None, 'payload_not_available': None,
                'optimistic': False, 'value_template': None,
                'tilt_open_position': 100, 'tilt_closed_position': 0,
                'tilt_min': 0, 'tilt_max': 100, 'tilt_optimistic': False,
                'tilt_invert_state': False,
                'set_position_topic': None, 'set_position_template': None,
                'unique_id': None, 'device_config': None,
            },
            None,
            None)

        assert 44 == mqtt_cover.find_in_range_from_percent(44)
        assert 44 == mqtt_cover.find_in_range_from_percent(44, 'cover')

    def test_find_in_range_altered(self):
        """Test find in range with altered range."""
        mqtt_cover = MqttCover(
            {
                'name': 'cover.test',
                'state_topic': 'state-topic',
                'get_position_topic': None,
                'command_topic': 'command-topic',
                'availability_topic': None,
                'tilt_command_topic': 'tilt-command-topic',
                'tilt_status_topic': 'tilt-status-topic',
                'qos': 0,
                'retain': False,
                'state_open': 'OPEN', 'state_closed': 'CLOSE',
                'position_open': 180, 'position_closed': 80,
                'payload_open': 'OPEN', 'payload_close': 'CLOSE',
                'payload_stop': 'STOP',
                'payload_available': None, 'payload_not_available': None,
                'optimistic': False, 'value_template': None,
                'tilt_open_position': 180, 'tilt_closed_position': 80,
                'tilt_min': 80, 'tilt_max': 180, 'tilt_optimistic': False,
                'tilt_invert_state': False,
                'set_position_topic': None, 'set_position_template': None,
                'unique_id': None, 'device_config': None,
            },
            None,
            None)

        assert 120 == mqtt_cover.find_in_range_from_percent(40)
        assert 120 == mqtt_cover.find_in_range_from_percent(40, 'cover')

    def test_find_in_range_defaults_inverted(self):
        """Test find in range with default range but inverted."""
        mqtt_cover = MqttCover(
            {
                'name': 'cover.test',
                'state_topic': 'state-topic',
                'get_position_topic': None,
                'command_topic': 'command-topic',
                'availability_topic': None,
                'tilt_command_topic': 'tilt-command-topic',
                'tilt_status_topic': 'tilt-status-topic',
                'qos': 0,
                'retain': False,
                'state_open': 'OPEN', 'state_closed': 'CLOSE',
                'position_open': 0, 'position_closed': 100,
                'payload_open': 'OPEN', 'payload_close': 'CLOSE',
                'payload_stop': 'STOP',
                'payload_available': None, 'payload_not_available': None,
                'optimistic': False, 'value_template': None,
                'tilt_open_position': 100, 'tilt_closed_position': 0,
                'tilt_min': 0, 'tilt_max': 100, 'tilt_optimistic': False,
                'tilt_invert_state': True,
                'set_position_topic': None, 'set_position_template': None,
                'unique_id': None, 'device_config': None,
            },
            None,
            None)

        assert 44 == mqtt_cover.find_in_range_from_percent(56)
        assert 44 == mqtt_cover.find_in_range_from_percent(56, 'cover')

    def test_find_in_range_altered_inverted(self):
        """Test find in range with altered range and inverted."""
        mqtt_cover = MqttCover(
            {
                'name': 'cover.test',
                'state_topic': 'state-topic',
                'get_position_topic': None,
                'command_topic': 'command-topic',
                'availability_topic': None,
                'tilt_command_topic': 'tilt-command-topic',
                'tilt_status_topic': 'tilt-status-topic',
                'qos': 0,
                'retain': False,
                'state_open': 'OPEN', 'state_closed': 'CLOSE',
                'position_open': 80, 'position_closed': 180,
                'payload_open': 'OPEN', 'payload_close': 'CLOSE',
                'payload_stop': 'STOP',
                'payload_available': None, 'payload_not_available': None,
                'optimistic': False, 'value_template': None,
                'tilt_open_position': 180, 'tilt_closed_position': 80,
                'tilt_min': 80, 'tilt_max': 180, 'tilt_optimistic': False,
                'tilt_invert_state': True,
                'set_position_topic': None, 'set_position_template': None,
                'unique_id': None, 'device_config': None,
            },
            None,
            None)

        assert 120 == mqtt_cover.find_in_range_from_percent(60)
        assert 120 == mqtt_cover.find_in_range_from_percent(60, 'cover')

    def test_availability_without_topic(self):
        """Test availability without defined availability topic."""
        assert setup_component(self.hass, cover.DOMAIN, {
            cover.DOMAIN: {
                'platform': 'mqtt',
                'name': 'test',
                'state_topic': 'state-topic',
                'command_topic': 'command-topic'
            }
        })

        state = self.hass.states.get('cover.test')
        assert STATE_UNAVAILABLE != state.state

    def test_availability_by_defaults(self):
        """Test availability by defaults with defined topic."""
        assert setup_component(self.hass, cover.DOMAIN, {
            cover.DOMAIN: {
                'platform': 'mqtt',
                'name': 'test',
                'state_topic': 'state-topic',
                'command_topic': 'command-topic',
                'availability_topic': 'availability-topic'
            }
        })

        state = self.hass.states.get('cover.test')
        assert STATE_UNAVAILABLE == state.state

        fire_mqtt_message(self.hass, 'availability-topic', 'online')
        self.hass.block_till_done()

        state = self.hass.states.get('cover.test')
        assert STATE_UNAVAILABLE != state.state

        fire_mqtt_message(self.hass, 'availability-topic', 'offline')
        self.hass.block_till_done()

        state = self.hass.states.get('cover.test')
        assert STATE_UNAVAILABLE == state.state

    def test_availability_by_custom_payload(self):
        """Test availability by custom payload with defined topic."""
        assert setup_component(self.hass, cover.DOMAIN, {
            cover.DOMAIN: {
                'platform': 'mqtt',
                'name': 'test',
                'state_topic': 'state-topic',
                'command_topic': 'command-topic',
                'availability_topic': 'availability-topic',
                'payload_available': 'good',
                'payload_not_available': 'nogood'
            }
        })

        state = self.hass.states.get('cover.test')
        assert STATE_UNAVAILABLE == state.state

        fire_mqtt_message(self.hass, 'availability-topic', 'good')
        self.hass.block_till_done()

        state = self.hass.states.get('cover.test')
        assert STATE_UNAVAILABLE != state.state

        fire_mqtt_message(self.hass, 'availability-topic', 'nogood')
        self.hass.block_till_done()

        state = self.hass.states.get('cover.test')
        assert STATE_UNAVAILABLE == state.state

    def test_valid_device_class(self):
        """Test the setting of a valid sensor class."""
        assert setup_component(self.hass, cover.DOMAIN, {
            cover.DOMAIN: {
                'platform': 'mqtt',
                'name': 'test',
                'device_class': 'garage',
                'state_topic': 'test-topic',
            }
        })

        state = self.hass.states.get('cover.test')
        assert 'garage' == state.attributes.get('device_class')

    def test_invalid_device_class(self):
        """Test the setting of an invalid sensor class."""
        assert setup_component(self.hass, cover.DOMAIN, {
            cover.DOMAIN: {
                'platform': 'mqtt',
                'name': 'test',
                'device_class': 'abc123',
                'state_topic': 'test-topic',
            }
        })

        state = self.hass.states.get('cover.test')
        assert state is None


async def test_setting_attribute_via_mqtt_json_message(hass, mqtt_mock):
    """Test the setting of attribute via MQTT with JSON payload."""
    assert await async_setup_component(hass, cover.DOMAIN, {
        cover.DOMAIN: {
            'platform': 'mqtt',
            'name': 'test',
            'state_topic': 'test-topic',
            'json_attributes_topic': 'attr-topic'
        }
    })

    async_fire_mqtt_message(hass, 'attr-topic', '{ "val": "100" }')
    await hass.async_block_till_done()
    state = hass.states.get('cover.test')

    assert '100' == state.attributes.get('val')


async def test_update_with_json_attrs_not_dict(hass, mqtt_mock, caplog):
    """Test attributes get extracted from a JSON result."""
    assert await async_setup_component(hass, cover.DOMAIN, {
        cover.DOMAIN: {
            'platform': 'mqtt',
            'name': 'test',
            'state_topic': 'test-topic',
            'json_attributes_topic': 'attr-topic'
        }
    })

    async_fire_mqtt_message(hass, 'attr-topic', '[ "list", "of", "things"]')
    await hass.async_block_till_done()
    state = hass.states.get('cover.test')

    assert state.attributes.get('val') is None
    assert 'JSON result was not a dictionary' in caplog.text


async def test_update_with_json_attrs_bad_JSON(hass, mqtt_mock, caplog):
    """Test attributes get extracted from a JSON result."""
    assert await async_setup_component(hass, cover.DOMAIN, {
        cover.DOMAIN: {
            'platform': 'mqtt',
            'name': 'test',
            'state_topic': 'test-topic',
            'json_attributes_topic': 'attr-topic'
        }
    })

    async_fire_mqtt_message(hass, 'attr-topic', 'This is not JSON')
    await hass.async_block_till_done()

    state = hass.states.get('cover.test')
    assert state.attributes.get('val') is None
    assert 'Erroneous JSON: This is not JSON' in caplog.text


async def test_discovery_update_attr(hass, mqtt_mock, caplog):
    """Test update of discovered MQTTAttributes."""
    entry = MockConfigEntry(domain=mqtt.DOMAIN)
    await async_start(hass, 'homeassistant', {}, entry)
    data1 = (
        '{ "name": "Beer",'
        '  "command_topic": "test_topic",'
        '  "json_attributes_topic": "attr-topic1" }'
    )
    data2 = (
        '{ "name": "Beer",'
        '  "command_topic": "test_topic",'
        '  "json_attributes_topic": "attr-topic2" }'
    )
    async_fire_mqtt_message(hass, 'homeassistant/cover/bla/config',
                            data1)
    await hass.async_block_till_done()
    async_fire_mqtt_message(hass, 'attr-topic1', '{ "val": "100" }')
    await hass.async_block_till_done()
    await hass.async_block_till_done()
    state = hass.states.get('cover.beer')
    assert '100' == state.attributes.get('val')

    # Change json_attributes_topic
    async_fire_mqtt_message(hass, 'homeassistant/cover/bla/config',
                            data2)
    await hass.async_block_till_done()
    await hass.async_block_till_done()

    # Verify we are no longer subscribing to the old topic
    async_fire_mqtt_message(hass, 'attr-topic1', '{ "val": "50" }')
    await hass.async_block_till_done()
    await hass.async_block_till_done()
    state = hass.states.get('cover.beer')
    assert '100' == state.attributes.get('val')

    # Verify we are subscribing to the new topic
    async_fire_mqtt_message(hass, 'attr-topic2', '{ "val": "75" }')
    await hass.async_block_till_done()
    await hass.async_block_till_done()
    state = hass.states.get('cover.beer')
    assert '75' == state.attributes.get('val')


async def test_discovery_removal_cover(hass, mqtt_mock, caplog):
    """Test removal of discovered cover."""
    entry = MockConfigEntry(domain=mqtt.DOMAIN)
    await async_start(hass, 'homeassistant', {}, entry)
    data = (
        '{ "name": "Beer",'
        '  "command_topic": "test_topic" }'
    )
    async_fire_mqtt_message(hass, 'homeassistant/cover/bla/config',
                            data)
    await hass.async_block_till_done()
    state = hass.states.get('cover.beer')
    assert state is not None
    assert state.name == 'Beer'
    async_fire_mqtt_message(hass, 'homeassistant/cover/bla/config',
                            '')
    await hass.async_block_till_done()
    await hass.async_block_till_done()
    state = hass.states.get('cover.beer')
    assert state is None


async def test_discovery_update_cover(hass, mqtt_mock, caplog):
    """Test update of discovered cover."""
    entry = MockConfigEntry(domain=mqtt.DOMAIN)
    await async_start(hass, 'homeassistant', {}, entry)
    data1 = (
        '{ "name": "Beer",'
        '  "command_topic": "test_topic" }'
    )
    data2 = (
        '{ "name": "Milk",'
        '  "command_topic": "test_topic" }'
    )
    async_fire_mqtt_message(hass, 'homeassistant/cover/bla/config',
                            data1)
    await hass.async_block_till_done()
    state = hass.states.get('cover.beer')
    assert state is not None
    assert state.name == 'Beer'

    async_fire_mqtt_message(hass, 'homeassistant/cover/bla/config',
                            data2)
    await hass.async_block_till_done()
    await hass.async_block_till_done()

    state = hass.states.get('cover.beer')
    assert state is not None
    assert state.name == 'Milk'

    state = hass.states.get('cover.milk')
    assert state is None


async def test_discovery_broken(hass, mqtt_mock, caplog):
    """Test handling of bad discovery message."""
    entry = MockConfigEntry(domain=mqtt.DOMAIN)
    await async_start(hass, 'homeassistant', {}, entry)

    data1 = (
        '{ "name": "Beer",'
        '  "command_topic": "test_topic#" }'
    )
    data2 = (
        '{ "name": "Milk",'
        '  "command_topic": "test_topic" }'
    )

    async_fire_mqtt_message(hass, 'homeassistant/cover/bla/config',
                            data1)
    await hass.async_block_till_done()

    state = hass.states.get('cover.beer')
    assert state is None

    async_fire_mqtt_message(hass, 'homeassistant/cover/bla/config',
                            data2)
    await hass.async_block_till_done()
    await hass.async_block_till_done()

    state = hass.states.get('cover.milk')
    assert state is not None
    assert state.name == 'Milk'
    state = hass.states.get('cover.beer')
    assert state is None


async def test_unique_id(hass):
    """Test unique_id option only creates one cover per id."""
    await async_mock_mqtt_component(hass)
    assert await async_setup_component(hass, cover.DOMAIN, {
        cover.DOMAIN: [{
            'platform': 'mqtt',
            'name': 'Test 1',
            'state_topic': 'test-topic',
            'unique_id': 'TOTALLY_UNIQUE'
        }, {
            'platform': 'mqtt',
            'name': 'Test 2',
            'state_topic': 'test-topic',
            'unique_id': 'TOTALLY_UNIQUE'
        }]
    })

    async_fire_mqtt_message(hass, 'test-topic', 'payload')
    await hass.async_block_till_done()

    assert len(hass.states.async_entity_ids(cover.DOMAIN)) == 1


async def test_entity_device_info_with_identifier(hass, mqtt_mock):
    """Test MQTT cover device registry integration."""
    entry = MockConfigEntry(domain=mqtt.DOMAIN)
    entry.add_to_hass(hass)
    await async_start(hass, 'homeassistant', {}, entry)
    registry = await hass.helpers.device_registry.async_get_registry()

    data = json.dumps({
        'platform': 'mqtt',
        'name': 'Test 1',
        'state_topic': 'test-topic',
        'command_topic': 'test-command-topic',
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
    async_fire_mqtt_message(hass, 'homeassistant/cover/bla/config',
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
        'state_topic': 'test-topic',
        'command_topic': 'test-command-topic',
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
    async_fire_mqtt_message(hass, 'homeassistant/cover/bla/config',
                            data)
    await hass.async_block_till_done()
    await hass.async_block_till_done()

    device = registry.async_get_device({('mqtt', 'helloworld')}, set())
    assert device is not None
    assert device.name == 'Beer'

    config['device']['name'] = 'Milk'
    data = json.dumps(config)
    async_fire_mqtt_message(hass, 'homeassistant/cover/bla/config',
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
    assert await async_setup_component(hass, cover.DOMAIN, {
        cover.DOMAIN: [{
            'platform': 'mqtt',
            'name': 'beer',
            'state_topic': 'test-topic',
            'availability_topic': 'avty-topic',
            'unique_id': 'TOTALLY_UNIQUE'
        }]
    })

    state = hass.states.get('cover.beer')
    assert state is not None
    assert mock_mqtt.async_subscribe.call_count == 2
    mock_mqtt.async_subscribe.assert_any_call('test-topic', ANY, 0, 'utf-8')
    mock_mqtt.async_subscribe.assert_any_call('avty-topic', ANY, 0, 'utf-8')
    mock_mqtt.async_subscribe.reset_mock()

    registry.async_update_entity('cover.beer', new_entity_id='cover.milk')
    await hass.async_block_till_done()
    await hass.async_block_till_done()

    state = hass.states.get('cover.beer')
    assert state is None

    state = hass.states.get('cover.milk')
    assert state is not None
    assert mock_mqtt.async_subscribe.call_count == 2
    mock_mqtt.async_subscribe.assert_any_call('test-topic', ANY, 0, 'utf-8')
    mock_mqtt.async_subscribe.assert_any_call('avty-topic', ANY, 0, 'utf-8')
