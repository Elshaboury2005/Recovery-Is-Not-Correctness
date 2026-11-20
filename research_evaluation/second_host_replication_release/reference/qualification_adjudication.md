# Qualification adjudication

The raw attempt directories are immutable. One attempt was classified by an
earlier runner revision before the strict correctness acceptance rule was
installed:

- `pilot_attempts/c240-20261120t005408-7def330925/attempt_status.json` records
  `PILOT_VALID`.

Its own preserved evidence records `oracle.json.exit_code: 1`,
`production_validation.json.exit_code: 1`, `output_correct: null`, and the
HDFS metadata `IncompleteRead(0 bytes read, 16181 more expected)` error. It is
therefore adjudicated **non-qualifying/invalid** and must not be counted.

The subsequent attempt
`pilot_attempts/c240-20261120t005811-1d023a06d8` was run under the corrected
acceptance rule and is explicitly `PILOT_INVALID`. The pilot schedule is
`PILOT_INVALID`, with zero accepted pilot cells and zero main qualifying runs.
