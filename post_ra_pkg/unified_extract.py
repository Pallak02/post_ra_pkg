#!/usr/bin/env python3
"""
Unified extractor for multiple ROS 2 bags.

Outputs (under --outdir):
  json/observations.json
  json/observation_data_sources.json
  csv/assessments_with_time.csv     (header only if none)
  images/casualty_<stamp>.<fmt>     (if CasualtyImage present)

Run:
  python3 unified_extract.py --bag /path/to/bag_dir_or_db3 --outdir ../outputs
"""

import os, sys, json, yaml, argparse
from typing import Any, Dict, List, Optional
from array import array

# ---------- JSON helpers ----------
def jsonable(x: Any) -> Any:
    """Recursively convert arrays/bytes/numpy/etc. into JSON-friendly types."""
    if isinstance(x, (bytes, bytearray)):
        return list(x)
    if isinstance(x, array):
        return list(x)
    if hasattr(x, "tolist"):          # numpy arrays
        return x.tolist()
    if isinstance(x, dict):
        return {k: jsonable(v) for k, v in x.items()}
    if isinstance(x, (list, tuple)):
        return [jsonable(v) for v in x]
    return x

def bytes_to_int_list(b: bytes) -> List[int]:
    return list(b) if b else []

# ---------- run-start + metadata ----------
def normalize_bag_dir(path: str) -> str:
    return os.path.dirname(path) if path.endswith(".db3") else path

def read_metadata(bag_path: str) -> Dict[str, Any]:
    bag_dir = normalize_bag_dir(bag_path)
    meta = os.path.join(bag_dir, "metadata.yaml")
    if not os.path.exists(meta):
        raise FileNotFoundError(f"metadata.yaml not found in {bag_dir}")
    with open(meta, "r") as f:
        return yaml.safe_load(f)

def get_run_start_from_metadata(bag_path: str) -> Optional[float]:
    try:
        m = read_metadata(bag_path)
    except Exception:
        return None
    st = (m.get("rosbag2_bagfile_information", {}) or {}).get("starting_time", {}) or {}
    if "nanoseconds_since_epoch" in st:
        return st["nanoseconds_since_epoch"] / 1e9
    if "nanoseconds" in st:
        return st["nanoseconds"] / 1e9
    if "sec" in st and "nsec" in st:
        return st["sec"] + st["nsec"] / 1e9
    if "seconds_since_epoch" in st:
        return float(st["seconds_since_epoch"])
    return None

def find_topics_by_type(meta: Dict[str, Any], type_name: str) -> List[str]:
    section = (meta.get("rosbag2_bagfile_information", {}) or {}).get("topics_with_message_count", []) or []
    topics = []
    for t in section:
        tm = t.get("topic_metadata", {}) or {}
        if tm.get("type") == type_name:
            topics.append(tm.get("name"))
    return topics

# ---------- rosbag2 reading ----------
from rosbag2_py import SequentialReader, StorageOptions, ConverterOptions, StorageFilter
from rclpy.serialization import deserialize_message

# message imports (adjust if your package name differs)
from cdcl_umd_msgs.msg import Observation, ObservationDataSource, CasualtyImage

# Optional AudioData (skip cleanly if not installed)
try:
    from audio_common_msgs.msg import AudioData as RosAudioData
    HAVE_AUDIO_DATA = True
except Exception:
    HAVE_AUDIO_DATA = False

def iterate_messages(bag_path: str, topics: List[str], msg_cls, handler):
    """Open a fresh reader for a set of topics and pass each deserialized msg to handler(topic,msg,t)."""
    if not topics:
        return
    reader = SequentialReader()
    reader.open(
        StorageOptions(uri=normalize_bag_dir(bag_path), storage_id="sqlite3"),
        ConverterOptions(input_serialization_format="cdr", output_serialization_format="cdr"),
    )
    reader.set_filter(StorageFilter(topics=topics))
    while reader.has_next():
        topic, data, t = reader.read_next()
        try:
            msg = deserialize_message(data, msg_cls)
        except Exception:
            continue
        handler(topic, msg, t)

# ---------- main extraction ----------
def unified_extract(bag_path: str, outdir: str):
    os.makedirs(outdir, exist_ok=True)
    json_dir = os.path.join(outdir, "json")
    csv_dir  = os.path.join(outdir, "csv")
    img_dir  = os.path.join(outdir, "images")
    os.makedirs(json_dir, exist_ok=True)
    os.makedirs(csv_dir,  exist_ok=True)
    os.makedirs(img_dir,  exist_ok=True)

    meta = read_metadata(bag_path)

    obs_topics = find_topics_by_type(meta, "cdcl_umd_msgs/msg/Observation")
    ods_topics = find_topics_by_type(meta, "cdcl_umd_msgs/msg/ObservationDataSource")
    img_topics = find_topics_by_type(meta, "cdcl_umd_msgs/msg/CasualtyImage")
    aud_topics = find_topics_by_type(meta, "audio_common_msgs/msg/AudioData") if HAVE_AUDIO_DATA else []

    print(f"[topics] Observation: {obs_topics}")
    print(f"[topics] ObservationDataSource: {ods_topics}")
    print(f"[topics] CasualtyImage: {img_topics}")
    if HAVE_AUDIO_DATA:
        print(f"[topics] AudioData: {aud_topics}")

    run_start = get_run_start_from_metadata(bag_path)
    if run_start is not None:
        print(f"[run_start] {run_start:.3f} (from metadata.yaml)")
    else:
        print("[run_start] not found; time_since_start will equal raw stamp(sec)")

    observations: List[Dict[str, Any]] = []
    data_sources: List[Dict[str, Any]] = []

    # ---- handlers ----
    def handle_observation(topic: str, msg: Observation, t: int):
        obs_vals = getattr(msg, "observation", [])
        try:
            obs_vals = list(obs_vals)  # convert array('f')->list if needed
        except Exception:
            pass
        rec = {
            "topic": topic,
            "stamp": t,
            "time_since_start": (t/1e9 - run_start) if run_start is not None else t/1e9,
            "data_source_id": getattr(msg, "data_source_id", None),
            "platform_name":   getattr(msg, "platform_name", ""),
            "observation_module": getattr(msg, "observation_module", ""),
            "observation":     obs_vals,
        }
        observations.append(rec)

    def handle_ods(topic: str, msg: ObservationDataSource, t: int):
        ds = {
            "topic": topic,
            "stamp": t,
            "time_since_start": (t/1e9 - run_start) if run_start is not None else t/1e9,
            "data_source_id": getattr(msg, "data_source_id", None),
            "platform_name":   getattr(msg, "platform_name", ""),
            "audio_transcript": getattr(msg, "audio_transcript", "") or getattr(msg, "transcript", ""),
        }
        # raw_audio: list of ints if present
        try:
            raw = getattr(msg, "raw_audio", [])
            if isinstance(raw, (list, tuple, array)) and len(raw) > 0:
                ds["raw_audio"] = list(raw)
        except Exception:
            pass
        # embedded image (format + data as int list)
        try:
            img = getattr(msg, "image", None)
            if img and getattr(img, "data", None):
                fmt = (getattr(img, "format", "jpg") or "jpg").lower().replace(".", "")
                b = bytes(img.data)
                ds["image"] = {"format": fmt, "data": bytes_to_int_list(b)}
        except Exception:
            pass
        data_sources.append(ds)

    def handle_casualty_image(topic: str, msg: CasualtyImage, t: int):
        try:
            fmt = (getattr(msg, "format", "jpg") or "jpg").lower().replace(".", "")
        except Exception:
            fmt = "jpg"
        try:
            b = bytes(msg.data)
        except Exception:
            b = b""
        if not b:
            return
        fname = f"casualty_{t}.{fmt}"
        with open(os.path.join(img_dir, fname), "wb") as f:
            f.write(b)

    if HAVE_AUDIO_DATA:
        def handle_audio_data(topic: str, msg, t: int):  # no RosAudioData type hint
            b = bytes(getattr(msg, "data", b""))
            if not b:
                return
            aud_out = os.path.join(outdir, "audio")
            os.makedirs(aud_out, exist_ok=True)
            fname = f"audio_chunk_{t}.bin"
            with open(os.path.join(aud_out, fname), "wb") as f:
                f.write(b)

    # ---- read & collect ----
    iterate_messages(bag_path, obs_topics, Observation, handle_observation)
    iterate_messages(bag_path, ods_topics, ObservationDataSource, handle_ods)
    iterate_messages(bag_path, img_topics, CasualtyImage, handle_casualty_image)
    if HAVE_AUDIO_DATA and aud_topics:
        iterate_messages(bag_path, aud_topics, RosAudioData, handle_audio_data)

    # ---- write outputs ----
    with open(os.path.join(json_dir, "observations.json"), "w") as f:
        json.dump(jsonable(observations), f)

    with open(os.path.join(json_dir, "observation_data_sources.json"), "w") as f:
        json.dump(jsonable(data_sources), f)

    # always ensure the csv exists (even if empty) so downstream never breaks
    csv_path = os.path.join(csv_dir, "assessments_with_time.csv")
    if not os.path.exists(csv_path):
        os.makedirs(csv_dir, exist_ok=True)
        with open(csv_path, "w") as f:
            f.write("timestamp_sec,time_since_start,casualty_id,stage,value,data_source_ids\n")

    print(f"[done] observations: {len(observations)}, data_sources: {len(data_sources)}")
    print(f"[out] {os.path.join(json_dir,'observations.json')}")
    print(f"[out] {os.path.join(json_dir,'observation_data_sources.json')}")
    print(f"[out] images (if any) → {img_dir}")

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--bag", required=True, help="Path to bag directory OR .db3 file")
    ap.add_argument("--outdir", default="../outputs", help="Output directory root")
    args = ap.parse_args()
    unified_extract(args.bag, args.outdir)

if __name__ == "__main__":
    main()

