# Phase 3 research — pH auto-dosing for a single small reservoir

Practical findings backing the controller defaults in `PHASE3_PLAN.md`. Context:
20 L bench reservoir (`profiles/bench.yaml` resA), one INTLLAB peristaltic pump
(~50 mL/min) dosing commercial pH-Down (phosphoric-acid based), DFRobot Gravity
pH V2 probe on an ADS1115.

## 1 · How much does a mL of pH-Down move a small reservoir?

- Rule-of-thumb dosing for diluted commercial pH-Down: **~0.25–0.5 mL per 10 L**
  per adjustment step, re-test before adding more ([GroWorks pH Down][gw],
  [growing.farm calculator][gf]).
- For soft/RO water, ~1 mL/10 L can move pH by a full point; hard, well-buffered
  water needs several times more — **buffering capacity dominates**, so a fixed
  mL→ΔpH constant is only valid per-site ([growing.farm][gf],
  [How Hydroponics pH-Down guide][hh]).
- Phosphoric acid adds phosphorus (a macronutrient); chronic heavy pH-down use
  shifts the nutrient profile — another reason for small doses and daily caps
  ([Science in Hydroponics][sih]).
- **Implication for a 20 L reservoir:** 1 mL/dose ≈ 0.1–0.3 pH expected effect.
  Bluelab's setup rule — size the dose so **three dose cycles change pH by no
  more than ~0.1** — is the calibration target ([Bluelab pH Controller
  guide][bl-start]).
- At 50 mL/min, 1 mL = a 1.2 s pump run — comfortably above the relay's
  switching resolution.

## 2 · Mixing, settle time, probe lag

- Bluelab's controller exposes "Off Time" (lockout between doses) of **1–60
  min** and tells users to **start long and shorten only if no overshoot**;
  mixing quality sets the floor ([Bluelab device settings][bl-settings]).
- Community/vendor practice for small recirculated reservoirs: **≥10 min**
  between doses; 15–20 min for small tanks or weak circulation
  ([Garden Culture dosing guide][gc], [ZipGrow dosing systems][zg]).
- DFRobot Gravity pH V2: accuracy **±0.1 pH @ 25 °C**; glass-electrode response
  settles over tens of seconds, and readings immediately after a dose reflect
  the unmixed plume near the probe — i.e. **post-dose readings are not
  decision-grade until mixing completes** ([DFRobot wiki SEN0161-V2][dfr]).
- **Implication:** a hard *settle window* (ignore readings for the decision
  signal) of ~5 min after a dose, plus a *cooldown* (no next dose) of ~15 min.

## 3 · Bang-bang + hysteresis: deadband sizing, anti-oscillation, watchdog

- Bang-bang controllers need a **deadband/hysteresis band** around the
  threshold or they chatter; the band must exceed sensor noise and measurement
  uncertainty ([Wikipedia: bang-bang control][wiki-bb],
  [InstruNexus: hysteresis & deadband][inx]).
- With probe accuracy ±0.1 pH, the deadband must be **≥ 2× accuracy → 0.2 pH**
  so noise alone can never trigger or untrigger dosing.
- Overshoot/limit-cycling mechanism: dosing again before the previous dose is
  visible at the probe → integrated overdose → oscillation. The fix is exactly
  settle + cooldown + small fixed doses ([InstruNexus][inx], [Bluelab
  guide][bl-start]).
- **Watchdog precedent:** Bluelab stops dosing if it "senses dosing is not
  having an effect" after **15 dose cycles** ([Bluelab guide][bl-start]). 15 is
  generous for a commercial product with unknown tanks; for our known 20 L
  reservoir, **3 ineffective doses** (no measurable movement toward band) is a
  safer trip point — it bounds a runaway at 3 mL, not 15 mL.

## 4 · Failure modes and the interlocks that catch them

| Failure | Evidence | Interlock |
|---|---|---|
| Empty bottle / air-locked line | dose has no effect; pumps "run unattended for hours" are the classic failure ([Thomson Process][tp]) | watchdog → FAULT after `watchdog_doses` ineffective doses |
| Dry-running pump | peristaltics tolerate dry-run briefly but unattended dry-run wears tubing ([Thomson Process][tp], [Blue-White tube wear][bw]) | level sensor / `volume_budget_ml` gate + daily mL cap |
| Tubing fatigue/leak | rollers fatigue tubing → cracks, leaks, falling flow ([Blue-White][bw]); industrial pumps add leak-detect shutoffs ([Patsnap safety protocols][pp]) | flow not measurable in Phase 3 → bounded by caps + watchdog; tubing inspection noted in `control.md` maintenance |
| Stuck/drifted probe | glass probes drift with age and fouling; DFRobot recommends **calibrating ~monthly** ([DFRobot wiki][dfr], [Hackster review][hk]) | calibration-freshness interlock (refuse auto-dose if cal missing or >30 d); flat-line/stuck-value detection via the median filter window |
| Spike / NaN / disconnected probe | ADC float or broken lead reads garbage | physical-range gate (pH 0–14), staleness gate, median filter |
| Power loss mid-dose | relay drops → pump stops (fail-safe by hardware); systemd restarts the service | fail-safe boot to `monitor` + persisted E-STOP; dose ledger records the interrupted dose |
| Wrong-direction need (pH too low) | only pH-Down is stocked | direction interlock: no `dose-ph-up` role on the reservoir → HOLD + alert |

## 5 · Research-derived defaults (20 L bench reservoir)

| Tunable | Value | Reasoning |
|---|---|---|
| `dose_ml` | **1.0** | 0.25–0.5 mL/10 L guideline ([GroWorks][gw]) ⇒ 0.5–1 mL for 20 L; sized to Bluelab's "≤0.1 pH per 3 cycles" rule ([Bluelab][bl-start]). 1.2 s pump run at 50 mL/min. |
| `settle_seconds` | **300** (5 min) | probe sees unmixed plume until circulation completes; ≥ small-tank mixing floor ([Garden Culture][gc], [DFRobot][dfr]) |
| `cooldown_seconds` | **900** (15 min) | Bluelab Off-Time guidance "start long" for small tanks; 10 min common floor, 15–20 min for small reservoirs ([Bluelab settings][bl-settings], [ZipGrow][zg]) |
| `max_doses_per_hour` | **3** | consistent with 15-min cooldown; bounds worst-case hourly addition to 3 mL |
| `max_ml_per_day` | **20** (= 1 mL/L) | bounds daily acid addition to ~1 pH-point-equivalent even in soft water ([growing.farm][gf]); also caps P added ([Science in Hydroponics][sih]) |
| `deadband` | **0.2 pH** | ≥ 2× probe accuracy (±0.1) so noise can't trigger dosing ([DFRobot][dfr], [InstruNexus][inx]) |
| `watchdog_doses` | **3** | trips FAULT after 3 mL with no effect; far tighter than Bluelab's 15-cycle lockout ([Bluelab][bl-start]) |
| `hard_limits` | **pH 4.5–8.5** | outside this, readings indicate fault or emergency; refuse to dose, FAULT + alert |
| calibration freshness | **30 days** | DFRobot recommends ~monthly recalibration ([DFRobot wiki][dfr]) |

Scaling note: these defaults are *per-profile config*, derived for 20 L. The
commercial profile (200 L reservoirs) scales `dose_ml` and `max_ml_per_day`
~10× — the mock closed-loop already scales effect by `volume_l`, so the same
convergence tests validate both.

## Sources

[bl-start]: https://support.bluelab.com/bluelab-ph-controller
[bl-settings]: https://support.bluelab.com/hc/en-us/articles/360000112476-device-settings-explained-for-bluelab-connect-software
[gw]: https://groworks.co.uk/products/ph-down
[gf]: https://growing.farm/tools/water-ph-down-calculator
[hh]: https://howhydroponics.com/ph-down-guide-hydroponics/
[sih]: https://scienceinhydroponics.com/2020/10/how-much-phosphorous-are-you-adding-to-your-solution-to-adjust-ph.html
[gc]: https://gardenculturemagazine.com/a-guide-to-nutrient-dosing-machines/
[zg]: https://zipgrow.com/all-about-dosing-systems-for-indoor-growers/
[dfr]: https://wiki.dfrobot.com/Gravity__Analog_pH_Sensor_Meter_Kit_V2_SKU_SEN0161-V2
[hk]: https://www.hackster.io/sainisagar7294/a-review-to-dfrobot-gravity-ph-sensor-kit-v2-925041
[wiki-bb]: https://en.wikipedia.org/wiki/Bang%E2%80%93bang_control
[inx]: https://instrunexus.com/understanding-control-valve-hysteresis-deadband-response-time/
[tp]: https://www.thomsonprocess.ie/peristaltic-pumps-common-challenges-and-smart-fixes-that-work/
[bw]: https://www.blue-white.com/article/understanding-wear-factors-for-peristaltic-pump-tubes-and-other-components/
[pp]: https://eureka.patsnap.com/report-peristaltic-pump-safety-protocols-for-industrial-fluid-management

- [Bluelab pH Controller — getting started][bl-start]
- [Bluelab Connect — device settings explained][bl-settings]
- [GroWorks — pH Down (phosphoric acid) dosing guidance][gw]
- [growing.farm — pH-down dose calculator][gf]
- [How Hydroponics — pH Down guide][hh]
- [Science in Hydroponics — phosphorus added by pH adjustment][sih]
- [Garden Culture — nutrient dosing machines][gc]
- [ZipGrow — dosing systems for indoor growers][zg]
- [DFRobot wiki — Gravity Analog pH Sensor V2 (SEN0161-V2)][dfr]
- [Hackster — DFRobot Gravity pH Kit V2 review][hk]
- [Wikipedia — bang-bang control][wiki-bb]
- [InstruNexus — control hysteresis, deadband, response time][inx]
- [Thomson Process — peristaltic pump challenges][tp]
- [Blue-White — peristaltic tube wear factors][bw]
- [Patsnap — peristaltic pump safety protocols][pp]
