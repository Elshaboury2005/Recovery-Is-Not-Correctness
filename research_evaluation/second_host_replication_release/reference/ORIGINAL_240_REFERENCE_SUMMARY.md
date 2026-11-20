# Primary 240-run reference summary

The reference campaign was frozen under protocol `CHAOSFLOW-240-OBSERVER-RECOVERY-V1` with:

- 8 scenarios (`C0` through `C7`)
- 2 observer states (`OBSERVER_ON`, `OBSERVER_OFF`)
- 15 repetitions per cell
- 240 qualifying observations, executed sequentially
- randomization seed `20261120`
- 256 total attempts, including 16 invalid attempts that are excluded from the qualifying sample

The second host must execute a fresh 240-qualifying-run campaign. It must not copy primary attempt identifiers, statuses, metrics, or evidence into its schedules. The supplied `run_schedule.csv` and `pilot_schedule.csv` are clean planned templates; the original schedules are retained under `reference/` for design comparison only.

Scenario details and qualification rules are in `reference/frozen_protocol.md` and `reference/qualification_adjudication.md`.

