#!/usr/bin/env bash
cd /home/denisk/Projects/teams-notifications/daemon
exec .venv/bin/python3 -m teams_notifications.native_host
