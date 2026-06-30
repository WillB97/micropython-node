"""
Transmit and receive functions for RFM42/31 modules.

Packet structure:
- 64b preamble
- 16b sync word
- 8b header
- 8b packet length
- payload - 48b device ID
- 16b crc

160b@40kbps = 4ms
"""
import time
import machine
from machine import Pin
from utils import lookup_node_id

SPI: machine.SPI = None
CS: Pin = None

def spi_init(cs_pin):
    global SPI, CS
    SPI = machine.SPI(1, baudrate=5000000, polarity=0, phase=0, sck=Pin(4), mosi=Pin(6), miso=Pin(5))
    CS = Pin(cs_pin, Pin.OUT)
    CS.on()

def spi_write(payload):
    payload[0] = payload[0] | 0x80
    CS.off()
    SPI.write(payload)
    CS.on()

def spi_read(payload, length):
    CS.off()
    SPI.write(payload)
    result = bytearray(length)
    SPI.readinto(result)
    CS.on()
    return result

def detect_trx():
    version = spi_read(bytearray([0x01]), 1)[0]
    return version == 0x06

def tx_init():
    # Software reset
    spi_write(bytearray([0x07, 0x80]))

    # Wait for chip to be ready
    while not (int.from_bytes(spi_read(bytearray([0x04]), 1)) & 0x01):
        time.sleep(0.001)

    # Set Operating mode to READY
    spi_write(bytearray([0x07, 0x01]))
    # Set TX power to max
    spi_write(bytearray([0x6D, 0x1F]))

    # Frequency: 864.1MHz -> hbsel=1, fb=19, fc=13120
    spi_write(bytearray([0x75, 0x73, 0x33, 0x40]))
    # Leave datarate at 40kbps

    # 8 bit header & set preamble to 64 bit
    spi_write(bytearray([0x33, 0x12, 0x10]))
    # Set header value
    spi_write(bytearray([0x3A, 0b10100101]))

    # Set Modulation Mode Control 2 to GFSK & FIFO mode
    spi_write(bytearray([0x71, 0x23]))

def rx_init():
    # Software reset
    spi_write(bytearray([0x07, 0x80]))

    # Wait for chip to be ready
    while not (int.from_bytes(spi_read(bytearray([0x04]), 1)) & 0x01):
        time.sleep(0.001)

    # Set Operating mode to READY
    spi_write(bytearray([0x07, 0x01]))

    # Frequency: 864.1MHz -> hbsel=1, fb=19, fc=13120
    spi_write(bytearray([0x75, 0x73, 0x33, 0x40]))

    # Enable RX multi packet
    spi_write(bytearray([0x08, 0x10]))

    # 8 bit header & set preamble to 64 bit
    spi_write(bytearray([0x33, 0x12, 0x10]))
    # Set expected header
    spi_write(bytearray([0x3F, 0b10100101]))
    # Enable header check
    spi_write(bytearray([0x32, 0x08]))

    # Leave IF filter at default (40kbps, 20kHz)
    # Leave AGC enabled

    # Disable AFC
    spi_write(bytearray([0x1D, 0x04]))

    # Set Modulation Mode Control 2 to GFSK & FIFO
    spi_write(bytearray([0x71, 0x23]))

    # Enable receive
    spi_write(bytearray([0x07, 0x05]))

def tx_msg(data: bytes):
    # data = bytes(list(range(16)))
    # Write data to FIFO
    spi_write(bytearray([0x7F]) + data)

    # Set Transmit Packet Length to 16 bytes
    spi_write(bytearray([0x3E, len(data)]))

    # Set TX mode to send packet
    spi_write(bytearray([0x07, 0x09]))

    # Monitor progress of sending by checking ipksent status
    while not (int.from_bytes(spi_read(bytearray([0x03]), 1)) & 0x04):
        time.sleep(0.001)

def clear_rx_fifo():
    old_val = spi_read(bytearray([0x08]), 1)
    spi_write(bytearray([0x08, 0x02]))
    spi_write(bytearray([0x08]) + old_val)

def rx_msg(timeout_s=5):
    end_time = time.time()+timeout_s
    # Wait for fifo empty to clear
    while (int.from_bytes(spi_read(bytearray([0x02]), 1)) & 0x20):
        time.sleep(0.001)
        if time.time() > end_time:
            return False

    # Measure RSSI, hopefully in a packet
    rssi = int.from_bytes(spi_read(bytearray([0x26]), 1))

    # Wait for receive to complete
    while (int.from_bytes(spi_read(bytearray([0x31]), 1)) & 0x10):
        time.sleep(0.001)

    # Read header and packet length
    header, recv_len = spi_read(bytearray([0x7F]), 2)

    # Check valid header
    if header != 0b10100101:
        return False

    if recv_len > 0:
        # try reading out FIFO
        payload = spi_read(bytearray([0x7F]), recv_len).hex()

        print(payload, lookup_node_id(payload), rssi, sep=':')
        # print("Msg received (", recv_len, "b, RSSI", rssi, "):", payload)
        return True
    return False
