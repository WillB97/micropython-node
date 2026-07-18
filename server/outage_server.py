#!/usr/bin/env python3
# ```json
# {
#     "<serial>": {
#         "node_id": "<node id>"
#         "rfm": "<timestamp>",
#         "wifi": "<timestamp>",
#         "extra_data": "<mqtt payload + rfm rssi>",
#         "offline_confidence": 0,
#     }
# }
# ```
from pathlib import Path
import argparse
import logging
import json
from collections import defaultdict
from dataclasses import dataclass, field, asdict
from threading import Lock
from time import sleep, time
from typing import Any

import requests
from paho.mqtt.client import MQTTMessage
from paho.mqtt.client import Client as BaseMQTTClient

from mqtt import MQTTClient, load_mqtt_config

LOGGER = logging.getLogger(__name__)
OFFLINE_THRESHOLD = 30


@dataclass
class DeviceData:
    node_id: int = 0
    rfm: float = 0.0
    wifi: float = 0.0
    extra_data: dict[str, Any] = field(default_factory=dict)
    offline_confidence: int = -1


STATE_LOCK = Lock()
DEVICE_STATES = defaultdict(lambda: DeviceData())


def on_forget_message(client: BaseMQTTClient, userdata: Any, message: MQTTMessage):
    LOGGER.debug(f"Message received ({message.topic}) {message.payload}")
    try:
        payload = json.loads(message.payload)
    except json.JSONDecodeError:
        LOGGER.warning(f"Failed to decode message {message.payload}")
        return

    if "device" not in payload:
        LOGGER.warning(f"Message is missing required keys: {message.payload}")
        return

    with STATE_LOCK:
        if DEVICE_STATES.pop(payload["device"], None):
            LOGGER.info(f"Forgetting {payload['device']}")


def on_reset_message(client: BaseMQTTClient, userdata: Any, message: MQTTMessage):
    LOGGER.debug(f"Message received ({message.topic}) {message.payload}")
    try:
        payload = json.loads(message.payload)
    except json.JSONDecodeError:
        LOGGER.warning(f"Failed to decode message {message.payload}")
        return

    if payload.get("reset", False):
        LOGGER.info("Resetting seen devices")
        with STATE_LOCK:
            DEVICE_STATES.clear()


def on_state_message(client: BaseMQTTClient, userdata: Any, message: MQTTMessage):
    LOGGER.debug(f"Message received ({message.topic}) {message.payload}")
    try:
        payload = json.loads(message.payload)
    except json.JSONDecodeError:
        LOGGER.warning(f"Failed to decode message {message.payload}")
        return

    if "devices" not in payload:
        LOGGER.warning(f"Message is missing required keys: {message.payload}")
        return

    with STATE_LOCK:
        DEVICE_STATES.clear()
        for device, data in payload["devices"].items():
            DEVICE_STATES[device] = DeviceData(**data)

    LOGGER.info("Loaded previous state")


def on_message(client: BaseMQTTClient, userdata: Any, message: MQTTMessage):
    LOGGER.debug(f"Message received ({message.topic}) {message.payload}")
    timestamp = time()
    try:
        payload = json.loads(message.payload)
    except json.JSONDecodeError:
        LOGGER.warning(f"Failed to decode message {message.payload}")
        return

    if (
        "identifier" not in payload
        or "source" not in payload
        or "node_id" not in payload
    ):
        LOGGER.warning(f"Message is missing required keys: {message.payload}")
        return

    with STATE_LOCK:
        data = DEVICE_STATES[payload["identifier"]]
        if payload["source"] == "rfm":
            data.rfm = timestamp
        elif payload["source"] == "mqtt":
            data.wifi = timestamp
        data.node_id = payload["node_id"]
        data.extra_data.update(payload)
        data.extra_data.pop("source", None)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("config", type=Path, help="MQTT server configuration")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
    )

    mqtt_config = load_mqtt_config(args.config)
    mqtt_client = MQTTClient(
        username=mqtt_config["username"] or "",
        password=mqtt_config["password"] or "",
        use_tls=mqtt_config["use_tls"],
    )
    mqtt_client.connect(mqtt_config["host"], mqtt_config["port"])
    mqtt_client.subscribe("status/#", on_message)
    mqtt_client.subscribe("reset", on_reset_message)
    mqtt_client.subscribe("forget", on_forget_message)
    mqtt_client.subscribe("state", on_state_message)

    sleep(2)
    mqtt_client.unsubscribe("state")
    sleep(8)

    while True:
        current_time = time()
        # fetch node map
        try:
            r = requests.get("https://power.emf.camp/distro/status/json").json()[
                "distros"
            ]
            node_lookup = {
                node["monitoring_node_id"]: node["distro_id"]
                for node in r
                if node["monitoring_node_id"] is not None
            }
        except Exception:
            LOGGER.warning("Failed to load lookup")
            node_lookup = {}

        with STATE_LOCK:
            for device, data in DEVICE_STATES.items():
                last_seen = max(data.rfm, data.wifi)
                seen_delta = current_time - last_seen
                prev_confidence = data.offline_confidence
                raw_confidence = int(max(0, seen_delta - OFFLINE_THRESHOLD))
                data.offline_confidence = int(min(100, raw_confidence))

                distro_id = node_lookup.get(data.node_id)

                if 0 < raw_confidence < 150:
                    LOGGER.info(
                        f"Device offline: {device} ({data.node_id}), certainty {data.offline_confidence}%"
                    )
                    # Post outage
                    if distro_id is not None:
                        requests.post(
                            "http://vm-power02.emf.camp/nodeState",
                            json={
                                "nodeID": distro_id,
                                "state": "dead",
                                "source": "monitor",
                                "confidence": data.offline_confidence / 100,
                            },
                        )
                elif prev_confidence and not raw_confidence:
                    LOGGER.info(f"Device reconnected: {device} ({data.node_id})")
                    # Post restored
                    if distro_id is not None:
                        requests.post(
                            "http://vm-power02.emf.camp/nodeState",
                            json={
                                "nodeID": distro_id,
                                "state": "alive",
                                "source": "monitor",
                            },
                        )
                elif (int(last_seen) % 10) == 0:
                    if distro_id is not None:
                        requests.post(
                            "http://vm-power02.emf.camp/nodeState",
                            json={
                                "nodeID": distro_id,
                                "state": "alive",
                                "source": "monitor",
                            },
                        )

            payload = {
                "current_time": current_time,
                "devices": {
                    device: asdict(data) for device, data in DEVICE_STATES.items()
                },
            }

        mqtt_client.publish(
            "state",
            json.dumps(payload),
            retain=True,
        )
        sleep(1)


if __name__ == "__main__":
    main()
