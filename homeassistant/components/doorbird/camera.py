"""Support for viewing the camera feed from a DoorBird video doorbell."""
import asyncio
import datetime
import logging

import aiohttp
import async_timeout

from homeassistant.components.camera import SUPPORT_STREAM, Camera
from homeassistant.helpers.aiohttp_client import async_get_clientsession
import homeassistant.util.dt as dt_util

from .const import DOMAIN, DOOR_STATION, DOOR_STATION_INFO
from .entity import DoorBirdEntity

_LAST_VISITOR_INTERVAL = datetime.timedelta(minutes=2)
_LAST_MOTION_INTERVAL = datetime.timedelta(seconds=30)
_LIVE_INTERVAL = datetime.timedelta(seconds=45)
_LOGGER = logging.getLogger(__name__)
_TIMEOUT = 15  # seconds


async def async_setup_entry(hass, config_entry, async_add_entities):
    """Set up the DoorBird camera platform."""
    config_entry_id = config_entry.entry_id
    doorstation = hass.data[DOMAIN][config_entry_id][DOOR_STATION]
    doorstation_info = hass.data[DOMAIN][config_entry_id][DOOR_STATION_INFO]
    device = doorstation.device

    async_add_entities(
        [
            DoorBirdCamera(
                doorstation,
                doorstation_info,
                device.live_image_url,
                "live",
                f"{doorstation.name} Live",
                _LIVE_INTERVAL,
                device.rtsp_live_video_url,
            ),
            DoorBirdCamera(
                doorstation,
                doorstation_info,
                device.history_image_url(1, "doorbell"),
                "last_ring",
                f"{doorstation.name} Last Ring",
                _LAST_VISITOR_INTERVAL,
            ),
            DoorBirdCamera(
                doorstation,
                doorstation_info,
                device.history_image_url(1, "motionsensor"),
                "last_motion",
                f"{doorstation.name} Last Motion",
                _LAST_MOTION_INTERVAL,
            ),
        ]
    )


class DoorBirdCamera(DoorBirdEntity, Camera):
    """The camera on a DoorBird device."""

    def __init__(
        self,
        doorstation,
        doorstation_info,
        url,
        camera_id,
        name,
        interval=None,
        stream_url=None,
    ):
        """Initialize the camera on a DoorBird device."""
        super().__init__(doorstation, doorstation_info)
        self._url = url
        self._stream_url = stream_url
        self._name = name
        self._last_image = None
        self._supported_features = SUPPORT_STREAM if self._stream_url else 0
        self._interval = interval or datetime.timedelta
        self._last_update = datetime.datetime.min
        self._unique_id = f"{self._mac_addr}_{camera_id}"

    async def stream_source(self):
        """Return the stream source."""
        return self._stream_url

    @property
    def unique_id(self):
        """Camera Unique id."""
        return self._unique_id

    @property
    def supported_features(self):
        """Return supported features."""
        return self._supported_features

    @property
    def name(self):
        """Get the name of the camera."""
        return self._name

    async def async_camera_image(self):
        """Pull a still image from the camera."""
        now = dt_util.utcnow()

        if self._last_image and now - self._last_update < self._interval:
            return self._last_image

        try:
            websession = async_get_clientsession(self.hass)
            with async_timeout.timeout(_TIMEOUT):
                response = await websession.get(self._url)

            self._last_image = await response.read()
            self._last_update = now
            return self._last_image
        except asyncio.TimeoutError:
            _LOGGER.error("DoorBird %s: Camera image timed out", self._name)
            return self._last_image
        except aiohttp.ClientError as error:
            _LOGGER.error(
                "DoorBird %s: Error getting camera image: %s", self._name, error
            )
            return self._last_image