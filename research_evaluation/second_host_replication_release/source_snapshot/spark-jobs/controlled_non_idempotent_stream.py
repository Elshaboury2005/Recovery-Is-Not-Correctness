"""Disposable controlled sink variant for the ChaosFlow counterexample experiment.

This file is deliberately separate from streaming_processing_job.py.  Every
completed micro-batch is written to the same append directory twice.  It is
therefore a non-idempotent sink control, not evidence about the original sink.
"""
from __future__ import annotations

import argparse
import json
import os
import signal
import sys
import threading
import time

from pyspark.sql import SparkSession
from pyspark.sql import functions as F
from pyspark.sql.types import DoubleType, StringType, StructField, StructType


KAFKA_PACKAGE = "org.apache.spark:spark-sql-kafka-0-10_2.12:3.5.0"


def schema_from_config(config: dict) -> StructType:
    fields = []
    for item in config["schema"]:
        kind = DoubleType() if item["type"] == "double" else StringType()
        fields.append(StructField(item["name"], kind, True))
    return StructType(fields)


def apply_operations(frame, operations):
    for operation in operations:
        kind = operation["type"]
        if kind == "remove_nulls":
            frame = frame.na.drop()
        elif kind == "filter":
            frame = frame.filter(operation["condition"])
        else:
            raise ValueError(f"Controlled variant does not support operation {kind!r}")
    return frame


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config-json", required=True)
    parser.add_argument("--output-path", required=True)
    parser.add_argument("--checkpoint-path", required=True)
    parser.add_argument("--stop-file", required=True)
    parser.add_argument("--max-runtime-seconds", type=float, default=900)
    args = parser.parse_args()
    config = json.loads(args.config_json)
    stop_event = threading.Event()

    def request_stop(signum, frame):
        del signum, frame
        stop_event.set()

    signal.signal(signal.SIGTERM, request_stop)
    signal.signal(signal.SIGINT, request_stop)
    spark = (
        SparkSession.builder.appName("ChaosFlowControlledNonIdempotentSink")
        .config("spark.jars.packages", KAFKA_PACKAGE)
        .config("spark.sql.session.timeZone", "UTC")
        .config("spark.cores.max", "1")
        .getOrCreate()
    )
    spark.sparkContext.setLogLevel("WARN")
    messaging = config["messaging"]
    streaming = config["streaming"]
    schema = schema_from_config(config)
    reader = (
        spark.readStream.format("kafka")
        .option("kafka.bootstrap.servers", messaging.get("bootstrap_servers", "kafka:9092"))
        .option("subscribe", messaging["topic"])
        .option("startingOffsets", streaming.get("starting_offsets", "earliest"))
        .option("failOnDataLoss", "true")
    )
    if streaming.get("max_offsets_per_trigger") is not None:
        reader = reader.option("maxOffsetsPerTrigger", int(streaming["max_offsets_per_trigger"]))
    parsed = reader.load().select(F.from_json(F.col("value").cast("string"), schema).alias("data")).select("data.*")
    processed = apply_operations(parsed, config.get("processing", {}).get("operations", []))
    batches = []
    batch_lock = threading.Lock()

    def write_non_idempotent(batch, batch_id: int) -> None:
        materialized = batch.persist()
        rows = materialized.count()
        if rows:
            # This is the intentional controlled defect: the same completed
            # batch is appended twice, creating duplicate occurrences.
            materialized.write.mode("append").parquet(args.output_path)
            materialized.write.mode("append").parquet(args.output_path)
        materialized.unpersist()
        with batch_lock:
            batches.append({"batch_id": int(batch_id), "rows": int(rows), "append_writes": 2 if rows else 0})
        print("DUPLICATE_SINK_BATCH:" + json.dumps(batches[-1], sort_keys=True), flush=True)

    query = (
        processed.writeStream.foreachBatch(write_non_idempotent)
        .option("checkpointLocation", args.checkpoint_path)
        .trigger(processingTime=f"{int(streaming.get('trigger_interval_seconds', 2))} seconds")
        .start()
    )
    print("STREAM_STARTED:" + json.dumps({"query_id": str(query.id), "run_id": str(query.runId)}), flush=True)
    started = time.monotonic()
    last_batch = -1
    total_input = 0
    try:
        while query.isActive and not stop_event.is_set():
            time.sleep(1)
            if os.path.exists(args.stop_file):
                stop_event.set()
            progress = list(query.recentProgress or [])
            for item in progress:
                batch_id = int(item.get("batchId", -1))
                if batch_id > last_batch:
                    last_batch = batch_id
                    source = (item.get("sources") or [{}])[0]
                    rows = int(item.get("numInputRows") or source.get("numInputRows") or 0)
                    total_input += rows
                    print("STREAM_PROGRESS:" + json.dumps({
                        "batchId": batch_id, "numInputRows": rows,
                        "totalInputRows": total_input,
                        "timestamp": item.get("timestamp"),
                    }, sort_keys=True), flush=True)
            if time.monotonic() - started > args.max_runtime_seconds:
                stop_event.set()
                print("CONTROLLED_VARIANT_TIMEOUT", flush=True)
        if stop_event.is_set() and query.isActive:
            query.stop()
        query.awaitTermination(60)
        failure = query.exception()
        output_rows = None
        if failure is None:
            output_rows = spark.read.parquet(args.output_path).count()
        result = {
            "status": "failed" if failure is not None else "success",
            "input_rows": total_input,
            "output_rows": output_rows,
            "batches": batches,
            "duplicate_sink": True,
            "error": None if failure is None else str(failure),
        }
        print("CONTROLLED_VARIANT_RESULT:" + json.dumps(result, sort_keys=True), flush=True)
        return 0 if failure is None else 1
    finally:
        spark.stop()


if __name__ == "__main__":
    raise SystemExit(main())
