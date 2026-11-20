# Statistical Validity Report — Pre-Follow-Up

## What is supported

The primary campaign has 240 strict qualifying observations, balanced at 15
per scenario/observer cell, a reconciled 256-record attempt ledger, complete
correctness pass for the latest qualifying records, and preserved invalid and
replacement history. Independent paired block calculations reproduce the
population and provide a more appropriate observer comparison than unpaired
cell summaries.

The corrected T4 sensitivity analysis is reproducible from raw progress
intervals and changes no raw evidence. Censoring is explicitly retained.

## Limitations

The original analysis implementation did not fully provide the frozen
matched-block/order diagnostics and used ordinary unpaired normal summaries
for several headline comparisons. The present audit adds paired block
contrasts, exact sign-flip p-values, interval confidence summaries, and
exploratory order diagnostics. Confidence intervals are still descriptive
for this audit; no claim is adjusted into significance merely because a
nominal p-value is below 0.05.

The main T4 endpoint is not complete under the original finite workload for
C3/C4/C7. T4 is a time-to-event-like endpoint with right censoring, so
complete-case means are not a substitute for a censored analysis. The
corrected T4 results are a measurement-sensitivity analysis, not a license to
pool a changed workload with the original 240.

Power is limited for small effects. The paired 80%-power normal MDE for
end-to-end duration ranges approximately from 15.1 to 32.0 seconds across
the eight scenarios. This is sufficient to rule out only relatively large
observer effects, not small overheads. The exact per-cell values are in
`matched_block_contrasts.csv`.

## Follow-up rule

No Kafka follow-up is statistically necessary for the T4 measurement gap
after correction. A C7 follow-up is justified only to test observability under
a longer workload, and only after a separate pilot verifies the endpoint.
Changed-protocol observations must remain separate from the primary 240.
