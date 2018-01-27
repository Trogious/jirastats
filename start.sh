#!/bin/sh -

BASEDIR=$(dirname "$0")
#pep8 --ignore=E501 $BASEDIR/jirastats.py 1>&2
env \
JS_USERNAME='' \
JS_PASSWORD='' \
JS_BASE_URL='https://jira.yggdrasilgaming.com' \
JS_OUTPUT_JSON_FILE=$BASEDIR/data.json \
python3 $BASEDIR/jirastats.py $@
