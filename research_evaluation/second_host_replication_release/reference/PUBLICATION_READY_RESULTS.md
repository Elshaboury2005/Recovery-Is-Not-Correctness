# Publication-Ready Results Summary

## Primary study

The primary ChaosFlow campaign contains 240 strict-qualifying observations:
eight scenarios, two observer states, and 15 observations per scenario ×
observer cell. The full attempt ledger contains 256 attempt-status records,
including 16 invalid attempts and 15 replacement-history slots. All 240 latest
qualifying records passed both the independent full-row correctness oracle and
the production validator.

The independent matched-block ON-minus-OFF end-to-end contrasts were: C0
15.04 s (95% CI −2.08 to 32.17), C1 17.77 s (−0.64 to 36.18), C2 −1.02 s
(−14.04 to 11.99), C3 4.28 s (−10.01 to 18.57), C4 −7.93 s (−30.32 to
14.46), C5 −10.48 s (−23.02 to 2.06), C6 −5.39 s (−19.56 to 8.77), and C7
−7.38 s (−17.94 to 3.19). These are descriptive randomized-block contrasts;
they do not establish a universal observer overhead.

## T4 measurement sensitivity

The original recorded T4 classification was 115 observed, 95 right-censored,
and 30 unobservable. Independent reanalysis corrected the interval-gap
predicate without changing raw timestamps or fabricating endpoints, yielding
175 observed, 35 right-censored, and 30 unobservable. C1 and C2 become 15/15
observed in both observer states under the corrected predicate. The remaining
censoring is concentrated in finite-workload tails, especially C7.

## Follow-up boundary

A separate 2M-workload C7 pilot was attempted. It produced five preserved
infrastructure-invalid attempts, zero valid pilot observations, and zero main
follow-up runs. No changed-protocol observation is included in the primary
results. C7 under the extended workload must be described as an unresolved
validation question, not as a negative recovery result.

## Evidence locations

The machine-readable audit tables are in this directory, the original raw
campaign is under `chaosflow_240_campaign_20261120_1`, and the separate pilot
is under `chaosflow_post240_c7_followup_20261120_1`. The final ZIP manifest
records exactly which runtime state directories and credential-bearing files
were excluded.

