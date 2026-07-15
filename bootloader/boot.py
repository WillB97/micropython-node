from machine import WDT

wdt = WDT(timeout=60000)
wdt.feed()

def do_boot():
    from boot_utils import get_creds, do_connect, get_led, fetch_ota_update, fetch_boot_ota_update

    LED = get_led()
    # TODO handle bootloader errors
    try:
        if do_connect(get_creds()):
            LED.flash(500)
            fetch_boot_ota_update()
            wdt.feed()
            fetch_ota_update()
            wdt.feed()
    except:
        pass
    LED.on()

do_boot()
# Clear boot functions from globals
del do_boot
