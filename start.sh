#!/bin/bash

nohup celery -A app.celery_app worker -c 4 &
if [[ -z "${DEBUG}" ]]; then
    gunicorn -b 0.0.0.0:8000 -w 4 --threads 128 --access-logfile - --error-logfile - app:app
else
    python app.py
fi
