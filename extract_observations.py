# extract_observations_clean.py

import json
from rosbag2_py import SequentialReader, StorageOptions, ConverterOptions
from rclpy.serialization import deserialize_message
from cdcl_umd_msgs.msg import Observation

reader = SequentialReader()
storage_options = StorageOptions(
    uri="../2025_07_29-11_55_45_0.db3",  # adjust path if needed
    storage_id="sqlite3"
)
converter_options = ConverterOptions(
    input_serialization_format="cdr",
    output_serialization_format="cdr"
)
reader.open(storage_options, converter_options)

TOPIC_NAME = "/observations"
msg_type = Observation

observations = []

while reader.has_next():
    topic, data, t = reader.read_next()

    if topic != TOPIC_NAME:
        continue

    try:
        msg = deserialize_message(data, msg_type)

        # Build the dictionary
        obs_data = {
            "stamp_sec": msg.stamp.sec,
            "stamp_nanosec": msg.stamp.nanosec,
            "data_source_id": msg.data_source_id,
            "platform_name": msg.platform_name,
            "observation_module": msg.observation_module,
            "observation": list(msg.observation),
            "seq": msg.seq,
            "position": {
                "latitude": msg.position.latitude,
                "longitude": msg.position.longitude,
                "altitude": msg.position.altitude,
                "covariance": list(msg.position.position_covariance)
            }
        }

        observations.append(obs_data)

    except Exception as e:
        print(f"Skipping message due to error: {e}")

# Save as JSON
with open("observations.json", "w") as f:
    json.dump(observations, f, indent=2)

print(f" Extracted {len(observations)} observations to observations.json")

