# Replication sample-size plan

The confirmatory replication target is 240 **qualifying** observations:

| factor | levels | repetitions |
|---|---:|---:|
| fault scenario | 8 (`C0`–`C7`) | 15 per scenario/observer cell |
| observer state | 2 (`ON`, `OFF`) | 15 per cell |
| qualifying total | 16 cells | 240 |

Invalid attempts are retained in the second host's local audit trail but do not count toward the 240 qualifying observations. Replacement attempts must follow the frozen adjudication rules and must never be silently relabeled as successful runs. The 16 invalid primary attempts are historical exclusions, not observations to be imported into this replication.

