#!/bin/bash
# Erase any existing firmware
esptool erase_flash

# Flash micropython
cd $(basename $0)
esptool write_flash 0 ESP32_GENERIC_C3-*-v1.27.0.bin
