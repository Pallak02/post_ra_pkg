#!/usr/bin/env python3
"""
Extract images from a ROS 2 bag.

- Works with either:
    * cdcl_umd_msgs/msg/CasualtyImage  (uses .image inside), or
    * sensor_msgs/msg/Image            (uses the message itself)

- No SciPy/NumPy required. Uses Pillow (PIL) only.
  If Pillow isn't installed:  pip install pillow

Usage example:
  python3 extract_casualty_images.py \
    --bag /path/to/2025_08_07_10_29_53_0.db3 \
    --topic /apollo/casualty_image \
    --outdir ./outputs/images

Tip: make sure your workspace can import cdcl_umd_msgs if you use CasualtyImage:
  colcon build && source install/setup.bash
"""

import argparse
from pathlib import Path
from typing import Iterator, Tuple, Optional

from rosbag2_py import SequentialReader, StorageOptions, ConverterOptions, StorageFilter
from rclpy.serialization import deserialize_message
from rosidl_runtime_py.utilities import get_message

from PIL import Image as PILImage  # pip install pillow


# ------------------------- ROS bag iteration -------------------------

def iter_bag_messages(db3_path: Path,
                      topic_name: str) -> Iterator[Tuple[object, int, str]]:
    """
    Yield (msg, t, msg_type_str) for each message on `topic_name`.
    `t` is the bag timestamp (nanoseconds).
    """
    reader = SequentialReader()
    reader.open(
        StorageOptions(uri=str(db3_path), storage_id="sqlite3"),
        ConverterOptions(input_serialization_format="cdr",
                         output_serialization_format="cdr"),
    )

    # Determine the recorded type for the topic
    topic_types = {t.name: t.type for t in reader.get_all_topics_and_types()}
    msg_type_str = topic_types.get(topic_name)
    if not msg_type_str:
        raise RuntimeError(f"Topic {topic_name!r} not found in bag.")

    MsgType = get_message(msg_type_str)

    # Filter to just this topic
    reader.set_filter(StorageFilter(topics=[topic_name]))

    while reader.has_next():
        topic, data, t = reader.read_next()
        msg = deserialize_message(data, MsgType)
        yield msg, t, msg_type_str


# ------------------------- Image saving (no NumPy) -------------------------

def _stamp_from_header(msg) -> Optional[Tuple[int, int]]:
    """
    Return (sec, nanosec) from msg.header.stamp if present.
    """
    hdr = getattr(msg, "header", None)
    if not hdr:
        return None
    stamp = getattr(hdr, "stamp", None)
    if not stamp:
        return None
    return (int(getattr(stamp, "sec", 0)), int(getattr(stamp, "nanosec", 0)))


def save_sensor_image(img_msg, out_path: Path) -> None:
    """
    Save a sensor_msgs/Image to a JPEG (RGB or L) without NumPy/SciPy.
    Supports encodings: rgb8, bgr8, mono8 (8UC1).
    Falls back to treating bytes as RGB if unknown.
    """
    h = int(getattr(img_msg, "height"))
    w = int(getattr(img_msg, "width"))
    enc = (getattr(img_msg, "encoding", "") or "").lower()
    data_bytes = bytes(getattr(img_msg, "data"))

    # Known encodings
    if enc == "rgb8":
        # Raw bytes already in RGB
        img = PILImage.frombytes("RGB", (w, h), data_bytes)
    elif enc == "bgr8":
        # Tell PIL the raw data is BGR; it will convert to RGB for us
        img = PILImage.frombytes("RGB", (w, h), data_bytes, "raw", "BGR")
    elif enc in ("mono8", "8uc1"):
        img = PILImage.frombytes("L", (w, h), data_bytes)
    else:
        # Best-effort fallback: assume 3-channel interleaved
        # If this appears tinted, your encoding isn't supported above.
        img = PILImage.frombytes("RGB", (w, h), data_bytes)

    # Save as JPEG
    out_path.parent.mkdir(parents=True, exist_ok=True)
    img.save(out_path, format="JPEG", quality=92)


# ------------------------- Main extraction logic -------------------------

def extract_images(db3: Path, topic: str, outdir: Path, limit: int = 0, every_n: int = 1) -> int:
    """
    Extract images from `topic` to `outdir`.
    `limit`: stop after this many frames (0 = no limit).
    `every_n`: save every Nth frame (1 = save all).
    Returns number of images written.
    """
    outdir.mkdir(parents=True, exist_ok=True)

    count = 0
    saved = 0

    for msg, t_ns, msg_type_str in iter_bag_messages(db3, topic):
        # If message is CasualtyImage, unwrap .image
        if msg_type_str.endswith("cdcl_umd_msgs/msg/CasualtyImage"):
            img_msg = getattr(msg, "image", None)
            if img_msg is None:
                # Unexpected; skip
                continue
        else:
            # Assume it's already sensor_msgs/Image
            img_msg = msg

        # Downsample
        count += 1
        if every_n > 1 and (count - 1) % every_n != 0:
            continue

        # Build filename using header stamp if present, else bag time
        stamp = _stamp_from_header(img_msg) or (t_ns // 10**9, int(t_ns % 10**9))
        sec, nsec = stamp
        fname = f"frame_{sec}_{nsec:09d}.jpg"
        out_path = outdir / fname

        try:
            save_sensor_image(img_msg, out_path)
            saved += 1
        except Exception as e:
            # Skip corrupt/unsupported frames
            print(f"[warn] failed to save frame at {sec}.{nsec:09d}: {e}")

        if limit and saved >= limit:
            break

    print(f"[done] wrote {saved} image(s) to {outdir}")
    return saved


# ------------------------- CLI -------------------------

def main():
    ap = argparse.ArgumentParser(description="Extract images from a ROS 2 bag topic.")
    ap.add_argument("--bag", required=True, help="Path to .db3 bag file")
    ap.add_argument("--topic", default="/apollo/casualty_image", help="Image topic (CasualtyImage or sensor_msgs/Image)")
    ap.add_argument("--outdir", required=True, help="Folder to write JPEGs")
    ap.add_argument("--limit", type=int, default=0, help="Max images to write (0 = no limit)")
    ap.add_argument("--every_n", type=int, default=1, help="Write every Nth frame (1 = all)")
    args = ap.parse_args()

    db3 = Path(args.bag)
    outdir = Path(args.outdir)
    extract_images(db3, args.topic, outdir, limit=args.limit, every_n=args.every_n)


if __name__ == "__main__":
    main()

