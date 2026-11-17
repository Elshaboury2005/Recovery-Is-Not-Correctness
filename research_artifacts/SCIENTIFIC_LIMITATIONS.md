# Scientific limitations

- The primary and follow-up campaigns are single-host, container-scoped
  observations. They do not establish general distributed fault tolerance.
- The default topology has one Kafka broker, one Spark worker, and one HDFS
  DataNode. Replicated-HDFS conditions are separate owned topologies and are
  not equivalent to a production cluster.
- Physical durability is `NOT_OBSERVABLE`; no independently timed physical
  media commit witness was established.
- Independent-host reproduction is `NOT_EXECUTED_NO_SECOND_PHYSICAL_HOST`.
- Sink-only recovery and the expanded benchmark remain
  `SKIPPED_RESOURCE_CONSTRAINT` because the available host and shared services
  made another campaign unsafe.
- Invalid, incomplete, failed-closed, and unconfirmed observations remain in
  their original populations. They are not converted to successful recovery.
- N3 retains packet-drop counters and configured impairment; no measured
  packet-loss percentage is asserted.
- The repeated v2 fixture contains legitimate row multiplicities. A zero
  duplicate-transaction-ID rule would be scientifically invalid.
- The Native Spark comparison is descriptive; no performance superiority claim
  is supported.
- The correction regression tests replay preserved logs and fixtures. They do
  not establish a new live R2 fault rerun.
