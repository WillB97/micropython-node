#!/usr/bin/env python3
from time import sleep
import argparse
import logging
import json
import re
from pathlib import Path

import serial

from mqtt import MQTTClient, load_mqtt_config


LOGGER = logging.getLogger(__name__)
RX_LOG = logging.getLogger("rfm_receiver")


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

    serial_port: serial.Serial = serial.serial_for_url("hwgrep://303A:1001")
    while True:
        try:
            line = serial_port.readline().decode().strip()
        except (serial.SerialException, UnicodeDecodeError):
            while True:
                try:
                    serial_port.close()
                    sleep(2)
                    serial_port.open()
                    serial_port.reset_input_buffer()
                except serial.SerialException:
                    pass
                else:
                    break
            continue
        output = re.fullmatch(r"([0-9a-f]{12}):([0-9]+):([0-9]+)", line)
        if output:
            node_serial, node_id_str, rssi_str = output.groups()
            node_id = int(node_id_str)
            rssi = int(rssi_str)
            LOGGER.info(
                f"Received broadcast from {node_id} ({node_serial}) with rssi {rssi}"
            )
            mqtt_client.publish(
                f"status/{node_serial}",
                json.dumps(
                    {
                        "identifier": node_serial,
                        "rssi": rssi,
                        "source": "rfm",
                        "node_id": node_id,
                    }
                ),
            )
        else:
            RX_LOG.info(line)


if __name__ == '__main__':
    main()
