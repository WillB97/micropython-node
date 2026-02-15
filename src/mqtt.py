import time
from umqtt import simple


# Reproduced from mqtt.robust
class MQTTClient(simple.MQTTClient):
    DELAY = 2
    DEBUG = False
    subscriptions = []

    def delay(self, i):
        time.sleep(self.DELAY)

    def log(self, in_reconnect, e):
        if self.DEBUG:
            if in_reconnect:
                print("mqtt reconnect: %r" % e)
            else:
                print("mqtt: %r" % e)

    def reconnect(self):
        i = 0
        while 1:
            try:
                super().connect(False)
                # Resubscribe after connection
                for (topic, qos) in self.subscriptions:
                    super().subscribe(topic, qos)
            except OSError as e:
                self.log(True, e)
                i += 1
                self.delay(i)

    def subscribe(self, topic, qos=0):
        self.subscriptions.append((topic, qos))
        super().subscribe(topic, qos)

    def unsubscribe(self, topic):
        for sub in self.subscriptions:
            if sub[0] == topic:
                self.subscriptions.remove(sub)
                break
        super().unsubscribe(topic)

    def publish(self, topic, msg, retain=False, qos=0):
        while 1:
            try:
                return super().publish(topic, msg, retain, qos)
            except OSError as e:
                self.log(False, e)
            self.reconnect()

    def wait_msg(self):
        while 1:
            try:
                return super().wait_msg()
            except OSError as e:
                self.log(False, e)
            self.reconnect()

    def check_msg(self, attempts=2):
        while attempts:
            self.sock.setblocking(False)
            try:
                return super().wait_msg()
            except OSError as e:
                self.log(False, e)
            self.reconnect()
            attempts -= 1


def do_mqtt(config, subs=[], sub_cb=None, last_will=None):
    for key in ['mqtt_server', 'mqtt_user', 'mqtt_passwd', 'client_id']:
        if not config.get(key):
            print("MQTT not configured")
            return
    c=MQTTClient(
        config['client_id'],
        config['mqtt_server'],
        user=config['mqtt_user'],
        password=config['mqtt_passwd'],
        ssl=True)
    if sub_cb:
        c.set_callback(sub_cb)
    if last_will:
        # topic, payload, retain, qos
        assert len(last_will) == 4
        c.set_last_will(*last_will)
    c.connect()
    for sub in subs:
        c.subscribe(sub)
    return c
