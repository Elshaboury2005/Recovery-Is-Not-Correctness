# Observer ON/OFF Reanalysis

The primary observer analysis uses the 15 randomized matched blocks within
each scenario. All 120 observer-ON qualifying runs have
`observer_started_ok=true` and nested observer evidence. The OFF runs carry
the explicit disabled-observer record. Thus observer exposure is complete for
the qualifying population.

The independent paired ON-minus-OFF end-to-end results are in
`matched_block_contrasts.csv`. The largest nominal differences are C1
(+17.77 s, exact paired p=0.0401) and C0 (+15.04 s, p=0.0645). Their 95%
intervals include zero, and eight scenario comparisons are made. After
multiplicity-aware interpretation, the data support only a cautious statement
that the observer may add measurable duration overhead in some cells; they do
not support a universal constant overhead or an observer-driven change in
correctness.

For the corrected T4-minus-T3 endpoint, paired differences are available for
all 15 pairs in C1, C2, C5, and C6 and have intervals that include zero. C3,
C4, and C7 retain censoring and are not treated as complete observer
comparisons for T4. Corrected T4 duration summaries must therefore be read
with their observed/censored denominators, not as complete-case proof of no
overhead.

All correctness cells are 15/15 oracle-pass and 15/15 production-validator
pass. Observer state is therefore not associated with a correctness failure
in this campaign.
