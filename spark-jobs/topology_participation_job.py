"""Emit executor host evidence for the bounded T2 topology placement preflight."""
from __future__ import annotations

import json

from pyspark.sql import SparkSession


def probe(_: object):
    import socket
    from pyspark import TaskContext
    context = TaskContext.get()
    # PySpark's TaskContext does not expose executorId(). The executor
    # container hostname is the direct placement identity for this topology.
    return [(socket.gethostname(), context.stageId(), context.partitionId())]


if __name__ == "__main__":
    spark = SparkSession.builder.appName("Phase2T2PlacementProbe").getOrCreate()
    rows = spark.sparkContext.parallelize(range(64), 32).flatMap(probe).collect()
    hosts = sorted({row[0] for row in rows})
    print("TOPOLOGY_PARTICIPATION:" + json.dumps({"partitions": len(rows), "hosts": hosts,
                                                   "records": [list(row) for row in rows]}, sort_keys=True), flush=True)
    spark.stop()
