class LED:
    def __init__(self, pin):
        from machine import Pin, Signal, Timer
        self._led = Signal(Pin(pin, Pin.OUT), invert=True)
        self._timer = Timer(0)
        self._flashing = False

    def on(self):
        if self._flashing:
            self._timer.deinit()
            self._flashing = False
        self._led.on()

    def off(self):
        if self._flashing:
            self._timer.deinit()
            self._flashing = False
        self._led.off()

    def value(self, val=None):
        if val is None:
            return self._led.value()
        if self._flashing:
            self._timer.deinit()
            self._flashing = False
        self._led.value(val)

    def flash(self, period):
        self._timer.init(period=period, callback=self._toggle)
        self._flashing = True

    def _toggle(self, t):
        self._led.value(not self._led.value())

_LED = LED(8)

def get_led():
    return _LED

def exists(file):
    try:
        with open(file):
            return True
    except OSError:
        return False

def get_creds(cred_file = "/creds.json", exclude_id=False):
    import json
    import machine
    creds = {}
    if not exclude_id:
        creds = {'client_id': machine.unique_id().hex()}
    if not exists(cred_file):
        return creds
    try:
        with open(cred_file) as f:
            creds.update(json.load(f))
            return creds
    except ValueError:
        return creds

def do_connect(config):
    if not (config.get('ssid') and config.get('psk')):
        print("Credentials not configured")
        return

    import network
    sta_if = network.WLAN(network.WLAN.IF_STA)
    if not sta_if.isconnected():
        print('connecting to network...')
        sta_if.active(True)
        sta_if.connect(config['ssid'], config['psk'])
        while not sta_if.isconnected():
            pass
    print('network config:', sta_if.ipconfig('addr4'))

def fetch_ota_update():
    # TODO
    pass
