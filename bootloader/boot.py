
def do_boot():
    from boot_utils import get_creds, do_connect, get_led, fetch_ota_update

    LED = get_led()
    if do_connect(get_creds()):
        LED.flash(500)
        fetch_ota_update()
    LED.on()

do_boot()
# Clear boot functions from globals
del do_boot
