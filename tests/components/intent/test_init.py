"""Tests for Intent component."""
import pytest

from homeassistant.setup import async_setup_component
from homeassistant.helpers import intent
from homeassistant.components.cover import SERVICE_OPEN_COVER

from tests.common import async_mock_service


async def test_http_handle_intent(hass, hass_client, hass_admin_user):
    """Test handle intent via HTTP API."""

    class TestIntentHandler(intent.IntentHandler):
        """Test Intent Handler."""

        intent_type = "OrderBeer"

        async def async_handle(self, intent):
            """Handle the intent."""
            assert intent.context.user_id == hass_admin_user.id
            response = intent.create_response()
            response.async_set_speech(
                "I've ordered a {}!".format(intent.slots["type"]["value"])
            )
            response.async_set_card(
                "Beer ordered", "You chose a {}.".format(intent.slots["type"]["value"])
            )
            return response

    intent.async_register(hass, TestIntentHandler())

    result = await async_setup_component(hass, "intent", {})
    assert result

    client = await hass_client()
    resp = await client.post(
        "/api/intent/handle", json={"name": "OrderBeer", "data": {"type": "Belgian"}}
    )

    assert resp.status == 200
    data = await resp.json()

    assert data == {
        "card": {
            "simple": {"content": "You chose a Belgian.", "title": "Beer ordered"}
        },
        "speech": {"plain": {"extra_data": None, "speech": "I've ordered a Belgian!"}},
    }


async def test_cover_intents_loading(hass):
    """Test Cover Intents Loading."""
    assert await async_setup_component(hass, "intent", {})

    with pytest.raises(intent.UnknownIntent):
        await intent.async_handle(
            hass, "test", "HassOpenCover", {"name": {"value": "garage door"}}
        )

    assert await async_setup_component(hass, "cover", {})

    hass.states.async_set("cover.garage_door", "closed")
    calls = async_mock_service(hass, "cover", SERVICE_OPEN_COVER)

    response = await intent.async_handle(
        hass, "test", "HassOpenCover", {"name": {"value": "garage door"}}
    )
    await hass.async_block_till_done()

    assert response.speech["plain"]["speech"] == "Opened garage door"
    assert len(calls) == 1
    call = calls[0]
    assert call.domain == "cover"
    assert call.service == "open_cover"
    assert call.data == {"entity_id": "cover.garage_door"}
