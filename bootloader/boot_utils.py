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
    import os
    try:
        os.stat(file)
        return True
    except OSError:
        return False

def rmtree(root):
    import os
    # is dir
    if not (exists(root) and (os.stat(root)[0] & 0x4000)):
        return
    for file, ftype, _, _ in os.ilistdir(root):
        if ftype & 0x4000: # dir
            rmtree(f"{root}/{file}")
        os.remove(f"{root}/{file}")
    os.rmdir(root)

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

def do_connect(config, timeout_ms=20000):
    if not (config.get('ssid') and config.get('psk', -1)) != -1:
        print("Credentials not configured")
        return False

    import network
    from time import ticks_ms
    sta_if = network.WLAN(network.WLAN.IF_STA)
    if not sta_if.isconnected():
        print('connecting to network...')
        sta_if.active(True)
        sta_if.connect(config['ssid'], config['psk'])
        end_time = ticks_ms() + timeout_ms
        while not sta_if.isconnected() and ticks_ms() < end_time:
            pass
        if not sta_if.isconnected():
            print('failed to connect')
            return False
    print('network config:', sta_if.ipconfig('addr4'))
    return True

def get_version(filename='version.txt'):
    try:
        with open(filename) as f:
            return f.read().strip()
    except OSError:
        return ''

def verify_package_hashes(url, git_ver=True, root=""):
    import mip
    response = mip.requests.get(url)
    if response.status_code != 200:
        print("Failed to get hashes.json")
        return None, None
    rsp_json = response.json()
    ver_key = 'commit_hash' if git_ver else 'version'
    version = rsp_json.get(ver_key)
    for path, hash in rsp_json.get('hashes', {}).items():
        path_full =  '/'.join([root, path])
        if not mip._check_exists(path_full, hash):
            print(f"Hash mismatch for: {path}")
            return version, True
    return version, False

def check_package_hashes(url, filename='version.txt', git_ver=True):
    raw_version, do_update = verify_package_hashes(url, git_ver)
    version = raw_version or get_version(filename)
    # Mask being unable to fetch hashes
    return version, do_update is True

def fetch_ota_update():
    import machine
    import mip
    import os
    import time
    package_hashes = "https://willb97.github.io/micropython-node/hashes.json"
    package = "github:willb97/micropython-node/package.json"

    # Check if package files match published hashes
    version, do_update = check_package_hashes(package_hashes)
    if not do_update:
        return

    rmtree('/lib/future')
    # Abuse _install_package so that we get a return code
    success = mip._install_package(package, "https://micropython.org/pi/v2", target='/lib', version=None, mpy=True)
    # on success, remove /active and mv /future to /active
    if success:
        rmtree('/active')
        os.rename('/lib/future', '/active')
        with open('version.txt', 'w') as f:
            f.write(version)
    else:
        print('Update failed')
        rmtree('/lib/future')
        time.sleep(5)
        machine.reset()

def fetch_boot_ota_update():
    import os
    import mip
    package_hashes = "https://willb97.github.io/micropython-node/bootloader/hashes.json"
    package = "github:willb97/micropython-node/bootloader/package.json"

    # Check if package files match published hashes
    version, do_update = check_package_hashes(package_hashes, "boot_version.txt", git_ver=False)
    if not do_update:
        return

    print("Updating bootloader to version", version)

    # Create & clear /new_boot
    rmtree('/new_boot')
    os.mkdir('/new_boot')

    # Abuse _install_package so that we get a return code
    success = mip._install_package(package, "https://micropython.org/pi/v2", target='/new_boot', version=None, mpy=True)

    if success:
        # Recheck hashes and ensure versions still match
        version_check, _ = verify_package_hashes(package_hashes, git_ver=False, root='/new_boot')
        if version_check == version:
            # copy files (non-recursive) to /
            for name, dtype, _, _ in os.ilistdir('/new_boot'):
                if dtype == 0x4000:
                    continue # skip dirs
                path = '/'.join(['/new_boot', name])
                os.rename(path, name)
            with open('boot_version.txt', 'w') as f:
                f.write(version)
            print("Updated bootloader")
        else:
            print("Bootloader update failed")
    else:
        print("Bootloader update failed")

    # Unconditionally remove /new_boot
    rmtree('/new_boot')
