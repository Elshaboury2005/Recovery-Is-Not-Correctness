# Research results

The evidence supports a bounded, single-host measurement case study. It does
not support a universal exactly-once, physical-durability, independent-host,
or performance-superiority claim.

| Population | Authoritative interpretation |
|---|---|
| Original Kafka confirmatory | 18-run large campaign; 1,000,000 source records and 966,002 expected transformed occurrences. |
| N1 interruption | 12 qualifying matched pairs, 16 executable fault attempts, 13 exact-correct attempts, and 3 recovered-but-incorrect source-delivery duplicate observations. |
| N2 latency | 12 valid matched pairs; exact correctness and runtime/recovery statistics retained. |
| N3 packet loss | 12 valid matched pairs; exact correctness and packet-drop counters retained. No measured loss percentage is invented. |
| Worker recovery | Corrected repeated-v2 campaign: 12 completed valid W1/W2 observations, 12 exact-correct, mean `T_confirm` approximately 83.788 s. Historical confirmed/unconfirmed populations remain separate. |
| S1 and S4 | Valid failed-closed observations are preserved; they are not automatic recovery successes. |
| Replicated HDFS | R0 6/6 exact-correct; R1 0/6 exact-correct and failure-closed under the held fault; R2 5/6 exact-correct with one incomplete source-consumption observation. |
| Source duplicate mitigation | 24 valid runs, 20 exact-oracle passes, 4 exact-oracle failures: A0 6/6, A1 2/6, B0 6/6, B1 6/6. |
| Native Spark comparison | Six valid matched pairs per condition, 24 exact-correct runs, two early invalid harness attempts retained; no superiority claim. |
| Physical durability / independent host | `NOT_OBSERVABLE` / `NOT_EXECUTED_NO_SECOND_PHYSICAL_HOST`. |

The R2 source-drain correction is executable and regression-tested, but its
preserved-evidence tests are not a new live fault rerun. The full claim-to-file
mapping is in `research_artifacts/EVIDENCE_CATALOG.csv` and
`research_artifacts/CORRECTION_SUPERSESSION_MAP.csv`.
