import sys
from boot_utils import get_creds, do_connect, get_led, fetch_ota_update

do_connect(get_creds())
LED = get_led()
LED.flash(500)
fetch_ota_update()
LED.on()
