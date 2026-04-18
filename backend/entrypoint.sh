#!/bin/sh
set -eu

python -m config.startup
exec daphne -b 0.0.0.0 -p 8000 config.asgi:application
