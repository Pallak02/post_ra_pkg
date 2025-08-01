import json
from rosbag2_py import SequentialReader, StorageOptions, ConverterOptions
from rclpy.serialization import deserialize_message
from cdcl_umd_msgs.msg import ObservationDataSource

reader = SequentialReader()
storage_options = StorageOptions(
    uri="../2025_07_29-11_55_45_0.db3",  # adjust path as needed
    storage_id="sqlite3"
)
converter_options = ConverterOptions(
    input_serialization_format="cdr",
    output_serialization_format="cdr"
)
reader.open(storage_options, converter_options)

TOPIC_NAME = "/observation_data_sources"
msg_type = ObservationDataSource
data_sources = []

while reader.has_next():
    topic, data, t = reader.read_next()
    if topic != TOPIC_NAME:
        continue
    try:
        msg = deserialize_message(data, msg_type)

        # Use getattr with default fallback to handle missing fields
        source_data = {
            "data_source_id": getattr(msg, "data_source_id", 0),
            "platform_name": getattr(msg, "platform_name", ""),
            "transcript": getattr(msg, "transcript", ""),
            "audio_transcript": getattr(msg, "audio_transcript", ""),
            "seq": getattr(msg, "seq", 0),
            "image_size": getattr(msg, "image_size", 0),
        }

        data_sources.append(source_data)

    except Exception as e:
        print(f"Skipping due to error: {e}")

with open("observation_data_sources.json", "w") as f:
    json.dump(data_sources, f, indent=2)

print(f"Extracted {len(data_sources)} data sources to observation_data_sources.json")

