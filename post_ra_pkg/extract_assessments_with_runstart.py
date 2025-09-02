import os
import yaml

def get_run_start_time(bag_path):
    """
    Extract run start time from metadata.yaml next to the bag.
    Returns float seconds.
    """
    metadata_file = os.path.join(os.path.dirname(bag_path), "metadata.yaml")
    if not os.path.exists(metadata_file):
        raise RuntimeError(f"No metadata.yaml found in {os.path.dirname(bag_path)}")

    with open(metadata_file, "r") as f:
        metadata = yaml.safe_load(f)

    info = metadata.get("rosbag2_bagfile_information", {})
    start_time = info.get("starting_time", {})

    # Handle different possible formats
    if "nanoseconds" in start_time:
        return start_time["nanoseconds"] * 1e-9
    elif "nanoseconds_since_epoch" in start_time:
        return start_time["nanoseconds_since_epoch"] * 1e-9
    elif "sec" in start_time and "nsec" in start_time:
        return start_time["sec"] + start_time["nsec"] * 1e-9
    elif "seconds_since_epoch" in start_time:
        return float(start_time["seconds_since_epoch"])
    else:
        raise RuntimeError(f"Unknown starting_time format: {start_time}")


if __name__ == "__main__":
    bag_path = "../2025_08_07_10_29_53_0.db3"
    try:
        t = get_run_start_time(bag_path)
        print(f"Run start time: {t:.3f} seconds (from metadata.yaml)")
    except Exception as e:
        print(f"Failed to get run start time: {e}")

