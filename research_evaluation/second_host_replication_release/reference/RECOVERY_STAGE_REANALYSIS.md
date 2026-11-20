# Recovery-Stage Reanalysis

The independent stage analysis uses the raw interval endpoints and keeps the
stage definitions distinct:

- T0: independently observed fault activation;
- T1: infrastructure/fault restoration evidence;
- T2: service-readiness evidence;
- T3: first post-T2 application-progress evidence;
- T4: corrected sustained-throughput confirmation;
- T5: terminal oracle/validator completion.

Readiness is not substituted for application progress or sustained
throughput. Every non-control qualifying record retains T0–T3 and T5; T4 is
reported as observed, right-censored, or unobservable.

The corrected T4-minus-T3 observed counts are: C1 30/30, C2 30/30, C3
18/30, C4 28/30, C5 30/30, C6 30/30, and C7 9/30. The C7 value is not a
failure rate: the missing 21 records are right-censored by the finite-workload
tail. The C0 control has no fault-origin T0–T4 endpoint and is correctly
classified as not applicable/unobservable for those fault-recovery stages.

Matched-block contrasts and their exact sign-flip p-values are available in
`matched_block_contrasts.csv`. Exploratory order correlations are in
`block_order_audit.csv`; they are not interpreted causally because execution
order is partly confounded with time and environment. The randomized matched
block design remains the primary comparison.
