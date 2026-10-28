#!/usr/bin/env sh
# Seed a real API session after docker compose up --build.
set -eu
python scripts/seed_demo.py
