# Step 1: Extract run start timestamp from ROS 2 bag
import rclpy
from rosbag2_py import SequentialReader, StorageOptions, ConverterOptions, StorageFilter
from rclpy.serialization import deserialize_message
from builtin_interfaces.msg import Time

def get_run_start_time(bag_path):
    reader = SequentialReader()
    storage_options = StorageOptions(uri=bag_path, storage_id="sqlite3")
    converter_options = ConverterOptions(input_serialization_format="cdr", output_serialization_format="cdr")
    reader.open(storage_options, converter_options)

    # Filter for the /run/start topic
    filter = StorageFilter(topics=["/run/start"])
    reader.set_filter(filter)

    while reader.has_next():
        topic, data, t = reader.read_next()
        msg = deserialize_message(data, Time)
        return msg.sec + msg.nanosec * 1e-9  # Convert to float seconds

    raise RuntimeError("No /run/start message found in the bag.")
if __name__ == "__main__":
    bag_path = "../2025_07_29-11_55_45_0.db3"  # Adjust if your bag is elsewhere
    try:
        t = get_run_start_time(bag_path)
        print(f"Run start time: {t:.3f} seconds")
    except Exception as e:
        print(f"Failed to get run start time: {e}")

