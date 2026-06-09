"""Mechanistic digital-twin simulation backend (HYDRO_MODE=sim).

Pure Python — no hardware imports. A single World owns plant + reservoir + zone
state; sim drivers are thin views over it. See
docs/superpowers/specs/2026-06-09-digital-twin-grow-sim-design.md.
"""
