# Wiring

The 13 connections for the Phase 1 controller. See `PHASE1_BRIEFING.md` for the
hardware list and `docs/pi-hardening.md` for the OS side.

| # | From | To |
|---|---|---|
| 1 | Pi 3V3 | ADS1115 VDD |
| 2 | Pi GND | ADS1115 GND |
| 3 | Pi SDA (pin 3) | ADS1115 SDA |
| 4 | Pi SCL (pin 5) | ADS1115 SCL |
| 5 | pH Po | ADS1115 A0 |
| 6 | TDS A | ADS1115 A1 |
| 7 | Pi GPIO4 (pin 7) | DS18B20 data |
| 8 | Pi GPIO17 (pin 11) | Relay IN1 |
| 9 | Pi 5V | Relay VCC |
| 10 | 12V PSU + | Relay COM |
| 11 | Relay NO | Pump +12V |
| 12 | 12V PSU GND | Pump GND |
| 13 | (isolation) | 12V and 5V share NO common ground — optocoupler isolation |

## Safety

Do **not** bridge the 12V and 5V grounds. The relay's optocoupler keeps the
power and logic domains isolated. Bridging them defeats the isolation and can
feed pump-motor noise (or worse) into the Pi.

## Notes for bring-up

- **DS18B20 needs a 4.7kΩ pull-up** between its data line (GPIO4) and 3V3.
- The Elegoo relay board is **active-low**: the driver energizes IN1 on logic
  low. `hal/factory.py` builds the pump with `active_high=False` to match —
  verify channel behavior before trusting a dose (a relay click should occur on
  `run_for_ms`). If yours is active-high, flip that one flag.
- After wiring, confirm the I2C device appears: `i2cdetect -y 1` should show the
  ADS1115 (default address `0x48`).
- Confirm the 1-Wire probe enumerates: `ls /sys/bus/w1/devices/` should list a
  `28-*` device.
