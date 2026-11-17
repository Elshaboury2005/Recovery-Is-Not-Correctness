# Experiments

ChaosLab supports controlled fault injection against containers that pass the
project safety checks. The default Compose stack is shared mutable state and is
not an appropriate target for an unapproved campaign.

## Safe execution rules

1. Freeze a protocol, workload contract, image versions, host resources, and
   output oracle before a campaign.
2. Use an isolated Compose project and dedicated volumes for live experiments.
3. Record every attempt, including invalid exposure, incomplete drain, failed
   closed, and unknown outcomes.
4. Separate fault exposure, application recovery, source consumption, sink
   output, and exact correctness.
5. Preserve raw logs before producing derived summaries.

The repository's historical evidence is summarized and catalogued under
`research_artifacts/`. The large raw-run tree remains in the separately
archived evidence package and is not duplicated in this GitHub source. No new
distributed campaign is required to build the publication package.

## Example configuration

The YAML examples under `experiments/` describe platform reliability requests.
They are configuration examples, not evidence that a live run has been
executed. Run them only after checking target ownership and resource limits.

## Research contracts

The consolidated results keep the following populations separate:

- 1,000,000 source records / 966,002 expected transformed occurrences.
- Frozen 10,000 source records / 9,647 expected occurrences.
- Repeated v2 20,000 source records / 19,294 expected occurrences.

The repeated fixture permits legitimate full-row multiplicities. A unique
transaction identifier is not a valid invariant for that fixture.
