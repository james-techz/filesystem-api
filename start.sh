#!/bin/bash

/usr/sbin/nginx

if [[ -z "${DEBUG}" ]]; then
    /usr/local/bin/gunicorn -b 0.0.0.0:8000 -w 4 --threads 128 --access-logfile - --error-logfile - app:app
else
    python app.py
fi
