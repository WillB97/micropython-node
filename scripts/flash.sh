#!/bin/bash -e
# TODO switch this to a python script

cd $(dirname $0)/..

# Install the OTA boot code
mpremote cp -v bootloader/* :

# TODO install libraries
mpremote mip install ./package.json
mpremote exec 'import os;os.rename("/lib/future","/active")'

# TODO config wifi/mqtt creds
# mpremote cp ... :creds.json

mpremote exec 'import machine;print(f"Unique identifier: {machine.unique_id().hex()}")'
