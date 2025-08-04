import rclpy
import csv
from rosbag2_py import SequentialReader, StorageOptions, ConverterOptions
from rclpy.serialization import deserialize_message
from cdcl_umd_msgs.msg import Assessment
from extract_assessments_with_runstart import get_run_start_time

# Path to your bag file (adjust if needed)
bag_path = "../2025_07_29-11_55_45_0.db3"

# Get run start timestamp
run_start = get_run_start_time(bag_path)

# Open bag reader
reader = SequentialReader()
storage_options = StorageOptions(uri=bag_path, storage_id="sqlite3")
converter_options = ConverterOptions(input_serialization_format="cdr", output_serialization_format="cdr")
reader.open(storage_options, converter_options)

# Prepare output
fields = [
    "casualty_id", "seq", "timestamp_sec", "time_since_start_sec",
    "severe_hemorrhage", "trauma_head", "trauma_upper_ext", "trauma_lower_ext",
    "respiratory_distress", "hr_value", "data_source_ids"
]

rows = []
count = 0

# Read assessments
while reader.has_next():
    topic, data, t = reader.read_next()
    if topic != "/assessments":
        continue

    try:
        msg = deserialize_message(data, Assessment)

        timestamp_sec = t * 1e-9
        time_since_start = timestamp_sec - run_start

        rows.append({
            "casualty_id": msg.casualty_id,
            "seq": msg.seq,
            "timestamp_sec": timestamp_sec,
            "time_since_start_sec": time_since_start,
            "severe_hemorrhage": list(msg.severe_hemorrhage),
            "trauma_head": list(msg.trauma_head),
            "trauma_upper_ext": list(msg.trauma_upper_ext),
            "trauma_lower_ext": list(msg.trauma_lower_ext),
            "respiratory_distress": list(msg.respiratory_distress),
            "hr_value": msg.hr_value,
            "data_source_ids": list(msg.data_source_ids)
        })
        count += 1

    except Exception as e:
        print(f"[!] Skipping due to error: {e}")

# Save to CSV
out_file = "assessments_with_time.csv"
with open(out_file, "w", newline="") as f:
    writer = csv.DictWriter(f, fieldnames=fields)
    writer.writeheader()
    for row in rows:
        writer.writerow(row)

print(f"Saved {count} assessment messages to {out_file}")

