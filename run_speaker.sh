#!/bin/bash

DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" >/dev/null && pwd )"

RUNCOMMAND="${DIR}/env/bin/python ${DIR}/device.py"

STOPFILE="/tmp/nursery_speaker_stop_file"


if [[ -z $(pidof $RUNCOMMAND) ]]; then
    if [[ -e $STOPFILE ]]; then
        echo "Process not found. Stopfile present. Exiting."
	exit
    else
        echo "Process not found. Running command."
        $RUNCOMMAND &
    fi
else
    echo "Process found."
fi
