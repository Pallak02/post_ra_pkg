#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Extract /assessments-like messages from a rosbag2 into a CSV with time_since_start_s.

Key features:
- Works with both 2-tuple and 3-tuple return styles of rosbag2_py.reader.read_next()
- Lets you pick the topic (default: /assessments); you can run it multiple times for other topics
- Computes time_since_start_s from the first seen timestamp on the selected topic
- Flattens nested ROS messages to columns using rosidl_runtime_py.message_to_ordereddict
- Optional JSONL debug dump of each raw message (already flattened)

Examples
--------
export BAG_A_DB="/home/cdcl/BagA/2025_07_29-11_55_45_0.db3"

python3 extract_assessments.py \
  --bag "$BAG_A_DB" \
  --outdir ./outputs/csv \
  --topic /assessments \
  --debug_jsonl ./outputs/csv/assessments_raw.jsonl
"""

import argparse
import csv
import os
from pathlib import Path
from typing import Dict, Any, Tuple

# ros2
from rosbag2_py import SequentialReader, StorageOptions, ConverterOptions
from rclpy.serialization import deserialize_message
from rosidl_runtime_py.utilities import get_message
from rosidl_runtime_py import message_to_ordereddict


def ensure_dir(p: Path):
    p.mkdir(parents=True, exist_ok=True)


def flatten(d: Dict[str, Any], parent_key: str = "", sep: str = ".") -> Dict[str, Any]:
    """
    Flatten a (possibly nested) dict coming from message_to_ordereddict.
    Arrays are kept as Python lists.
    """
    out: Dict[str, Any] = {}
    for k, v in d.items():
        key = f"{parent_key}{sep}{k}" if parent_key else k
        if isinstance(v, dict):
            out.update(flatten(v, key, sep=sep))
        else:
            out[key] = v
    return out


def pick_time_base(reader: SequentialReader, topic: str) -> int:
    """
    Find the first timestamp_ns for the given topic to use as t0.
    We do this by iterating once and remembering the first ts we see for that topic.
    Then we rewind by reopening the reader (cheapest reliable way).
    """
    t0 = None

    # Read once
    while reader.has_next():
        rec = reader.read_next()
        # 3-tuple (topic, raw, ts) OR 2-tuple (raw, ts)
        if isinstance(rec, tuple) and len(rec) == 3:
            topic_name, _, ts = rec
        elif isinstance(rec, tuple) and len(rec) == 2:
            topic_name = None  # unknown in 2-tuple mode
            _, ts = rec
        else:
            # Fallback to attribute access if rosbag2_py returns an object
            topic_name = getattr(rec, "topic_name", None)
            ts = getattr(rec, "timestamp", None)

        # If we have explicit topic_name, use it; otherwise we assume the reader
        # was filtered and treat every record as the target topic.
        is_target = (topic_name is None) or (topic_name == topic)
        if is_target:
            t0 = int(ts)
            break

    return t0 if t0 is not None else 0


def reopen_reader(bag_path: str, topic: str) -> SequentialReader:
    """
    Create a new reader restricted to a single topic (if possible).
    Some setups require reading all and filtering manually, but most support per-topic filtering.
    """
    reader = SequentialReader()
    storage = StorageOptions(uri=bag_path, storage_id="sqlite3")
    converter = ConverterOptions(input_serialization_format="cdr",
                                 output_serialization_format="cdr")
    reader.open(storage, converter)

    # Not all python bindings expose filters; reading all then filtering is fine.
    # To keep this script robust across distros, we *do not* apply a C++ filter here.
    return reader


def iterate_messages(reader: SequentialReader, topic: str) -> Tuple[bytes, int, str]:
    """
    Iterate messages, yielding (raw, ts, topic_name).
    Handles both 2-tuple and 3-tuple read_next styles.
    """
    while reader.has_next():
        rec = reader.read_next()
        if isinstance(rec, tuple) and len(rec) == 3:
            topic_name, raw, ts = rec
        elif isinstance(rec, tuple) and len(rec) == 2:
            raw, ts = rec
            topic_name = None  # unknown; assume caller filters
        else:
            topic_name = getattr(rec, "topic_name", None)
            raw = getattr(rec, "data", None)
            ts = getattr(rec, "timestamp", None)

        # If we know the topic_name, enforce match. Otherwise assume the sequence is filtered upstream.
        if (topic_name is None) or (topic_name == topic):
            yield raw, int(ts), (topic_name or topic)


def extract_assessments(bag_path: str,
                        out_csv: Path,
                        topic: str,
                        debug_jsonl: Path | None):
    """
    Read messages from `topic` in `bag_path` and write a CSV with time_since_start_s.
    Also (optionally) write a JSONL debug file with flattened messages and metadata.
    """
    # Peek for message type from metadata by opening a temporary reader and scanning connections.
    # If this is not available in your distro, you can hard-code the type (usually "cdcl_umd_msgs/msg/Assessment").
    # We’ll discover the type on-the-fly from the first message instead.

    # Open a reader to get t0
    reader = reopen_reader(bag_path, topic)
    t0 = pick_time_base(reader, topic)

    # Reopen to iterate from the start
    reader = reopen_reader(bag_path, topic)

    # Prepare output
    ensure_dir(out_csv.parent)
    debug_f = None
    if debug_jsonl:
        ensure_dir(Path(debug_jsonl).parent)
        debug_f = open(debug_jsonl, "w", encoding="utf-8")

    rows = []
    msg_type = None
    MsgType = None

    for raw, ts, topic_name in iterate_messages(reader, topic):
        if raw is None:
            continue

        # Lazy resolve the concrete message type using the connection info from the first record
        if MsgType is None:
            # Try to discover from the storage metadata: in many distros not available here easily.
            # So we brute-force: try known types, or let user tell us; but we can deserialize
            # once we know exact type name. Instead we can read type via metadata if bindings provide.
            #
            # More robust approach: try the most common type first, then fall back.
            candidate_types = [
                # common for this project
                "cdcl_umd_msgs/msg/Assessment",
                "cdcl_umd_msgs/msg/ScoredCasualtyReport",
                "cdcl_umd_msgs/msg/CasualtyAssignment",
                # generic fallback if user points to other topics
                # add more if needed
            ]
            deserialized = None
            for type_name in candidate_types:
                try:
                    T = get_message(type_name)
                    deserialized = deserialize_message(raw, T)
                    MsgType = T
                    msg_type = type_name
                    break
                except Exception:
                    deserialized = None

            if deserialized is None:
                raise RuntimeError(
                    "Could not infer message type automatically. "
                    "Edit candidate_types in this script (near MsgType discovery) "
                    "to include your message's type."
                )
        else:
            deserialized = deserialize_message(raw, MsgType)

        # Flatten to dict
        md = message_to_ordereddict(deserialized)
        flat = flatten(dict(md))

        # Compose row
        row = {
            "topic": topic_name,
            "timestamp_ns": ts,
            "time_since_start_s": (ts - t0) / 1e9 if t0 else 0.0,
        }
        row.update(flat)
        rows.append(row)

        # Optional JSONL debug
        if debug_f is not None:
            import json
            debug_f.write(json.dumps(row, ensure_ascii=False) + "\n")

    if debug_f is not None:
        debug_f.close()

    if not rows:
        print(f"[warn] No messages found on topic {topic!r} in bag {bag_path}")
        return

    # Determine CSV header (union of keys, stable order: metadata first)
    meta_keys = ["topic", "timestamp_ns", "time_since_start_s"]
    other_keys = sorted({k for r in rows for k in r.keys() if k not in meta_keys})
    header = meta_keys + other_keys

    # Write CSV
    with out_csv.open("w", newline="", encoding="utf-8") as f:
        wr = csv.DictWriter(f, fieldnames=header)
        wr.writeheader()
        wr.writerows(rows)

    print(f"[ok] wrote {len(rows)} rows to {out_csv.as_posix()}")
    if msg_type:
        print(f"[info] detected message type: {msg_type}")


def main():
    ap = argparse.ArgumentParser(
        description="Extract /assessments-like messages to CSV (with time_since_start_s)."
    )
    ap.add_argument("--bag", required=True, help="Path to rosbag2 .db3 file")
    ap.add_argument("--outdir", required=True, help="Output folder for CSV")
    ap.add_argument(
        "--topic",
        default="/assessments",
        help="Topic to extract (default: /assessments). "
             "Run again for other topics if needed.",
    )
    ap.add_argument(
        "--debug_jsonl",
        default="",
        help="Optional path to write JSONL of flattened rows (for debugging).",
    )
    args = ap.parse_args()

    bag_path = os.path.abspath(args.bag)
    outdir = Path(args.outdir).resolve()
    ensure_dir(outdir)

    topic_name = args.topic
    debug_jsonl = Path(args.debug_jsonl).resolve() if args.debug_jsonl else None

    # Choose file name based on topic (strip leading slash)
    safe_topic = topic_name.lstrip("/").replace("/", "_")
    out_csv = outdir / f"{safe_topic}_with_time.csv"

    extract_assessments(bag_path, out_csv, topic_name, debug_jsonl)


if __name__ == "__main__":
    main()

