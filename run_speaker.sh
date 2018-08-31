#!/bin/bash

DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" >/dev/null && pwd )"

RUNCOMMAND="${DIR}/env/bin/python ${DIR}/device.py"

if [[ -z $(pidof $RUNCOMMAND) ]]; then
    echo "Process not found. Running command."
    $RUNCOMMAND &
else
    echo "Process found."
fi
