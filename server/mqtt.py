from __future__ import annotations
import json
from pathlib import Path

import atexit
import logging
from typing import Any, Callable, TypedDict, Union, Optional

import paho.mqtt.client as mqtt

LOGGER = logging.getLogger(__name__)


class MQTTClient:
    def __init__(
        self,
        client_name: str | None = None,
        mqtt_version: mqtt.MQTTProtocolVersion = mqtt.MQTTProtocolVersion.MQTTv5,
        use_tls: bool | str = False,
        username: str = "",
        password: str = "",
    ) -> None:
        self.subscriptions: dict[
            str, Callable[[mqtt.Client, Any, mqtt.MQTTMessage], None]
        ] = {}
        self._client_name = client_name

        self._client = mqtt.Client(
            callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
            client_id=client_name,
            protocol=mqtt_version,
        )
        self._client.on_connect = self._on_connect

        if use_tls:
            self._client.tls_set()
            if use_tls == "insecure":
                self._client.tls_insecure_set(True)

        if username:
            self._client.username_pw_set(username, password)

    def connect(self, host: str, port: int) -> None:
        """
        Connect to the MQTT broker and start event loop in background thread.

        Registers an atexit routine that tears down the client.
        """
        if self._client.is_connected():
            LOGGER.error("Attempting connection, but client is already connected.")
            return

        try:
            self._client.connect_async(host, port, keepalive=60)
        except ValueError:
            LOGGER.error(f"Failed to connect to MQTT broker at {host}:{port}")
            return
        self._client.loop_start()
        atexit.unregister(self.disconnect)  # Avoid duplicate atexit handlers
        atexit.register(self.disconnect)

    def disconnect(self) -> None:
        """Disconnect from the broker and close background event loop."""
        self._client.disconnect()
        self._client.loop_stop()
        atexit.unregister(self.disconnect)

    def subscribe(
        self,
        topic: str,
        callback: Callable[[mqtt.Client, Any, mqtt.MQTTMessage], None],
    ) -> None:
        """Subscribe to a topic and assign a callback for messages."""
        self.subscriptions[topic] = callback
        self._subscribe(topic, callback)

    def _subscribe(
        self,
        topic: str,
        callback: Callable[[mqtt.Client, Any, mqtt.MQTTMessage], None],
    ) -> None:
        LOGGER.debug(f"Subscribing to {topic}")
        self._client.message_callback_add(topic, callback)
        self._client.subscribe(topic, qos=1)

    def unsubscribe(self, topic: str) -> None:
        """Unsubscribe from a topic."""
        try:
            del self.subscriptions[topic]
        except KeyError:
            pass
        self._client.message_callback_remove(topic)
        self._client.unsubscribe(topic)

    def publish(
        self,
        topic: str,
        payload: bytes | str,
        retain: bool = False,
    ) -> None:
        """Publish a message to the broker."""
        if not self._client.is_connected():
            LOGGER.debug(
                "Attempted to publish message, but client is not connected.",
            )
            return

        try:
            self._client.publish(topic, payload=payload, retain=retain, qos=1)
        except ValueError as e:
            raise ValueError(f"Cannot publish to MQTT topic: {topic}") from e

    def _on_connect(
        self,
        client: mqtt.Client,
        userdata: Any,
        connect_flags: mqtt.ConnectFlags,
        reason_code: mqtt.ReasonCode,
        properties: mqtt.Properties | None = None,
    ) -> None:
        if reason_code.is_failure:
            LOGGER.warning(
                f"Failed to connect to MQTT broker. Return code: {reason_code.getName()}"  # type: ignore[no-untyped-call]
            )
            return

        LOGGER.debug("Connected to MQTT broker.")

        for topic, callback in self.subscriptions.items():
            self._subscribe(topic, callback)


class MQTTVariables(TypedDict):
    host: str
    port: int
    use_tls: Union[bool, str]
    username: Optional[str]
    password: Optional[str]


def load_mqtt_config(filename: Path) -> MQTTVariables:
    config = json.loads(filename.read_text())
    return MQTTVariables(
        host=config["mqtt_server"],
        port=8883,
        use_tls=True,
        username=config["mqtt_user"],
        password=config["mqtt_passwd"],
    )
