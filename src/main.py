
import json

from mqtt import do_mqtt
from boot_utils import get_creds, get_led
CONFIG = get_creds()
CLIENT = None
LED = get_led()

def board_status():
    import esp32
    import network
    sta_if = network.WLAN(network.WLAN.IF_STA)
    return {
        'identifier': CLIENT.client_id, 'temp': esp32.mcu_temperature(),
        'ssid': sta_if.config('ssid'), 'rssi': sta_if.status('rssi')
    }

def sub_cb(topic, payload):
    try:
        try:
            data = json.loads(payload)
        except ValueError:
            print(f"Payload on {topic} not json")
            return

        if topic == b'time':
            msg = board_status()
            msg['timestamp'] = data.get('time', 0)
            CLIENT.publish(f'reports/{CLIENT.client_id}',json.dumps(msg), retain=True)
        elif topic.startswith(b'ctrl/'):
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

# time = respond on reports/<uid>
# ctrl/<uid> = ota/exec/wifi update
CLIENT = do_mqtt(CONFIG, ['time', f'ctrl/{CONFIG['client_id']}'], sub_cb)

CLIENT.publish(f'status/{CLIENT.client_id}',json.dumps(board_status()))
while True:
    # Replace with CLIENT.check_msg() to do other things in the loop
    CLIENT.wait_msg()
