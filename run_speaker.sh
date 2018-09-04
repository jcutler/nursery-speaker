#!/bin/bash

DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" >/dev/null && pwd )"

RUNCOMMAND="${DIR}/env/bin/python ${DIR}/device.py"

STOPFILE="/tmp/nursery_speaker_stop_file"

if [[ -z $(pidof $RUNCOMMAND) ]]; then
    echo "Process not found."
    if [[ -e $STOPFILE ]]; then
        echo "Stopfile present, exiting."
	    exit
    else
        echo "Running command."
        $RUNCOMMAND &
    fi
else
    echo "Process found."
fi
