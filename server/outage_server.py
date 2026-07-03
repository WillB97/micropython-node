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
    offline_confidence: int = 0


STATE_LOCK = Lock()
DEVICE_STATES = defaultdict(lambda: DeviceData())

# TODO add handlers for "state/forget" and "state/reset" topics

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

    while True:
        current_time = time()
        with STATE_LOCK:
            for device, data in DEVICE_STATES.items():
                last_seen = max(data.rfm, data.wifi)
                seen_delta = current_time - last_seen
                prev_confidence = data.offline_confidence
                raw_confidence = int(max(0, seen_delta - OFFLINE_THRESHOLD))
                data.offline_confidence = int(min(100, raw_confidence))

                if 0 < raw_confidence < 150:
                    LOGGER.info(f"Device offline: {device} ({data.node_id}), certainty {data.offline_confidence}%")
                    # TODO post outage
                elif prev_confidence and not raw_confidence:
                    LOGGER.info(f"Device reconnected: {device} ({data.node_id})")
                    # TODO post restored

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
        sleep(5)


if __name__ == '__main__':
    main()
