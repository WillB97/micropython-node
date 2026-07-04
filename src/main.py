import json
import network
import ntptime
import neopixel
from machine import Pin
from time import time_ns, sleep_ms
from random import randint

import rfm_trx
from mqtt import do_mqtt
from boot_utils import get_creds, get_led, get_version
from utils import lookup_node_id
CONFIG = get_creds()
CLIENT = None
LED = get_led()
VERSION = get_version()
BOOT_VER = get_version("boot_version.txt")
CS_PIN = 7
LED_CYCLE = [(20, 0, 0), (0, 20, 0), (0, 0, 20)]
NODE_ID = lookup_node_id(CONFIG['client_id'])

def board_status():
    import esp32
    import network
    sta_if = network.WLAN(network.WLAN.IF_STA)
    return {
        'identifier': CLIENT.client_id, 'temp': esp32.mcu_temperature(),
        'ssid': sta_if.config('ssid'), 'wifi_rssi': sta_if.status('rssi'),
        'version': VERSION, 'boot_version': BOOT_VER, 'source': 'mqtt', 'node_id': NODE_ID
    }

def sub_cb(topic, payload):
    try:
        try:
            data = json.loads(payload)
        except ValueError:
            print(f"Payload on {topic} not json")
            return

        if topic.startswith(b'ctrl/'):
            if data.get('identify') in {True, False}:
                # identify: bool - flash led @ 0.5hz
                if data['identify']:
                    print("Identify on")
                    LED.flash(1000)
                else:
                    print("Identify off")
                    LED.on()
            if data.get('script'):
                # script: str - exec as python
                exec(data['script'])
            if data.get('wifi'):
                # wifi: {ssid: str, psk: str} - set new wifi creds
                if not (data['wifi'].get('ssid') and data['wifi'].get('psk')):
                    print("Missing wifi creds")
                    return
                print(f"Updating WiFI to {data['wifi']['ssid']}")
                creds = get_creds(exclude_id=True)
                creds['ssid'] = data['wifi']['ssid']
                creds['psk'] = data['wifi']['psk']
                with open('/creds.json', 'w') as f:
                    json.dump(creds, f)
            if data.get('wifi') or data.get('update'):
                # update: bool - reboot to trigger an OTA pull
                from machine import reset
                reset()
        else:
            print(f"Received message on unknown topic: {topic}")
    except Exception as e:
        import sys
        print("Fatal error in callback:")
        sys.print_exception(e)

# Detect if we are transmitter or receiver
CFG1_STRAP = Pin(0, Pin.IN, Pin.PULL_DOWN)
IS_TX = not CFG1_STRAP.value()

print("Node ID", NODE_ID)

LEDS = neopixel.NeoPixel(Pin(10), 5, timing=(300,900,600,600))
LEDS.fill((0, 0, 0))
LEDS.write()

for x in range(8):
    for idx in range(5):
        LEDS[idx] = (5 if idx == x else 0, 5 if idx+1 == x else 0, 5 if idx+2 == x else 0)
    LEDS.write()
    sleep_ms(200)

# LED 5 - green=TX, blue=RX
LEDS[4] = (0, 20 if IS_TX else 0, 20 if not IS_TX else 0)
LEDS.write()

CLIENT = None
MQTT_STARTED = False
sta_if = network.WLAN(network.WLAN.IF_STA)
WIFI_ESTABLISHED = sta_if.isconnected()

rfm_trx.spi_init(CS_PIN)
WITH_TRX = rfm_trx.detect_trx()

def ensure_wifi():
    global WIFI_ESTABLISHED, CLIENT
    # Wifi will auto-reconnect
    WIFI_ESTABLISHED = sta_if.isconnected()
    if WIFI_ESTABLISHED and CLIENT is None:
        # Do ntp sync if we are connected
        for _ in range(10):
            try:
                ntptime.settime()
                break
            except OSError:
                print("NTP sync failed")
        CLIENT = do_mqtt(CONFIG, [f'ctrl/{CONFIG['client_id']}'], sub_cb)

    # LED 4 - blue=no rfm, red=no WiFi
    LEDS[3] = (20 if not sta_if.isconnected() else 0, 0, 20 if not WITH_TRX else 0)
    LEDS.write()

def time_modulo(time_offset):
    return (time_ns() + 2_500_000_000 - time_offset) % 5_000_000_000

# Do not run MQTT operations if not connected, they will hang until reconnected
# WiFi automatically reconnects, MQTT will reconnect on next action
ensure_wifi()

LED_ENTRY = 0
if IS_TX:
    # For transmitter
    rfm_trx.tx_init()

    # Precalculate time offset from node id in ns
    time_offset = int(NODE_ID * 0.1e9)

    while True:
        LEDS[0] = LED_CYCLE[LED_ENTRY]
        LEDS.write()
        LED_ENTRY = (LED_ENTRY + 1) % 3
        # Every 5s, each node gets a 100ms timeslot, ordered by node id
        ensure_wifi()
        if sta_if.isconnected() and CLIENT is not None:
            CLIENT.publish(f'status/{CLIENT.client_id}',json.dumps(board_status()))

        # split timeslot into 20x5ms slot. Align window so that modulo has 2.5s before window and 2.4s after
        # pick 2 random 5ms slots in the timeslot and send message twice
        slots= [randint(0, 19), randint(0, 19)]
        slots.sort()
        # ensure slots are different
        if slots[0] == slots[1]:
            slots[1] = (slots[1] + 1) % 20
        # in ms
        slots = [(slot * 5 + 2500) for slot in slots]
        payload = bytes.fromhex(CONFIG['client_id'])

        # Spin until modulo wraps and is under 2.5
        while time_modulo(time_offset) > 2.5e9:
            if sta_if.isconnected() and CLIENT is not None:
                CLIENT.check_msg()

        if WITH_TRX:
            # sleep for first slot
            sleep_for = slots[0] - (time_modulo(time_offset) // 1_000_000)
            sleep_ms(sleep_for)

            rfm_trx.tx_msg(payload)

            # sleep for second slot
            sleep_for = slots[1] - (time_modulo(time_offset) // 1_000_000)
            if sleep_for > 0:
                sleep_ms(sleep_for)
            rfm_trx.tx_msg(payload)
            print("Transmitted")
        else:
            sleep_ms(2500)

else:
    RECV_COUNT = 0
    # For receiver
    rfm_trx.rx_init()
    slot_idx = time_ns() // 5_000_000_000
    while True:
        LEDS[0] = LED_CYCLE[LED_ENTRY]
        LEDS.write()
        LED_ENTRY = (LED_ENTRY + 1) % 3

        if WITH_TRX:
            recvd_msg = rfm_trx.rx_msg()
            if recvd_msg:
                print(*recvd_msg, sep=':')
                if sta_if.isconnected() and CLIENT is not None:
                    node_serial, node_id, rssi = recvd_msg
                    CLIENT.publish(f'status/{node_serial}',json.dumps(
                        {
                            "identifier": node_serial,
                            "rssi": rssi,
                            "source": "rfm",
                            "node_id": node_id,
                        }
                    ))

                LEDS[1] = LED_CYCLE[RECV_COUNT % 3]
                LEDS.write()
                RECV_COUNT += 1

        ensure_wifi()

        if sta_if.isconnected() and CLIENT is not None:
            CLIENT.check_msg()

        if (time_ns() // 5_000_000_000) > slot_idx:
            # TODO remove
            if sta_if.isconnected() and CLIENT is not None:
                CLIENT.publish(f'status/{CLIENT.client_id}',json.dumps(board_status()))
                CLIENT.publish(f'status/{CLIENT.client_id}',json.dumps(
                    {
                        "identifier": CLIENT.client_id,
                        "rssi": 255,
                        "source": "rfm",
                        "node_id": NODE_ID,
                    }
                ))

            print(CONFIG['client_id'], NODE_ID, 255, sep=':')
            slot_idx = time_ns() // 5_000_000_000
