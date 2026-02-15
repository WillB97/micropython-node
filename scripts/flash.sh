#!/bin/bash
# TODO switch this to a python script

cd $(basename $0)/..

# Copy files into place
mpremote cp -v bootloader/* :
mpremote mkdir :active
mpremote cp -rv src/* :active

# TODO install libraries
# mpremote mip install

# TODO config wifi/mqtt creds
# mpremote cp ... creds.json
