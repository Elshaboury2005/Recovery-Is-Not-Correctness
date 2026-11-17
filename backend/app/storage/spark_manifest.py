"""Strict reader for Spark 3.5 append-file-sink v1 commit logs.

Only stable, stopped-query snapshots are supported. No fallback to directory
listing is allowed if a manifest is present but incomplete or unreadable.
"""
from __future__ import annotations

import json
import posixpath
import re
from typing import Callable
from urllib.parse import unquote, urlsplit


def committed_paths(root: str, names: list[str], read_text: Callable[[str], str]) -> list[str]:
    logs = {}
    for name in names:
        match = re.fullmatch(r"(0|[1-9][0-9]*)(\.compact)?", name)
        if match:
            batch = int(match[1])
            # A compact snapshot supersedes the same batch's incremental log.
            if batch not in logs or match[2]:
                logs[batch] = name
    if not logs:
        raise ValueError("Sink metadata has no committed batch logs")
    compact = [b for b, name in logs.items() if name.endswith(".compact")]
    first = max(compact) if compact else 0
    last = max(logs)
    if any(b not in logs for b in range(first, last + 1)):
        raise ValueError("Sink metadata has a gap between committed batches")
    paths: set[str] = set()
    prefix = posixpath.normpath(root).rstrip("/") + "/"
    for batch in range(first, last + 1):
        lines = read_text(logs[batch]).splitlines()
        if not lines or lines[0] != "v1":
            raise ValueError("Incomplete or unsupported Spark sink log version")
        for line in lines[1:]:
            entry = json.loads(line)
            uri = urlsplit(entry["path"])
            path = posixpath.normpath(unquote(uri.path))
            if uri.scheme not in ("", "hdfs") or not path.startswith(prefix):
                raise ValueError("Sink log references a file outside its output directory")
            if entry.get("isDir") is not False or not path.endswith(".parquet"):
                raise ValueError("Sink log does not describe a Parquet file")
            if entry.get("action") == "add":
                paths.add(path)
            else:
                # Spark 3.5 append sinks emit add only. Do not guess the
                # semantics of a future log version or unsupported action.
                raise ValueError("Unsupported sink log action")
    return sorted(paths)
