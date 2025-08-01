# post_ra_pkg

This ROS 2 package processes and visualizes casualty assessment and observation data extracted from a `.db3` rosbag. It generates CSV, JSON, and interactive Plotly HTML plots per field and casualty ID.

---

## Directory Structure

```
post_ra_ws/
├── src/
│   ├── assessments_with_time.csv
│   ├── observations.json
│   ├── observation_data_sources.json
│   ├── extract_assessments.py
│   ├── extract_assessments_with_runstart.py
│   ├── extract_observations.py
│   ├── extract_observation_data_sources.py
│   ├── plot_every_field_by_casualty_time.py
│   └── smart_field_plots_time/
│       ├── respiratory_distress/
│       ├── severe_hemorrhage/
│       ├── trauma_head/
│       ├── trauma_lower_ext/
│       └── trauma_upper_ext/
└── 2025_07_29-11_55_45_0.db3
```

---

## Step-by-Step Usage

### 1. **Extract Assessments**

Extracts assessment messages and adds run start time.

```bash
python3 extract_assessments_with_runstart.py
```

- **Input**: `2025_07_29-11_55_45_0.db3`
- **Output**: `assessments_with_time.csv`

---

### 2. **Extract Observations**

```bash
python3 extract_observations.py
```

- **Output**: `observations.json`

---

### 3. **Extract Observation Data Sources**

```bash
python3 extract_observation_data_sources.py
```

- **Output**: `observation_data_sources.json`

---

### 4. **Generate Plots**

This script creates a directory of interactive HTML plots categorized by field and casualty.

```bash
python3 plot_every_field_by_casualty_time.py
```

- **Input**:
  - `assessments_with_time.csv`
  - `observations.json`
  - `observation_data_sources.json`
- **Output Folder**: `smart_field_plots_time/`

Each subfolder (e.g. `trauma_head`, `respiratory_distress`) contains HTML files per casualty like:

```bash
smart_field_plots_time/trauma_head/casualty_1.html
```

---

## Notes

- Plots are over a 30-minute (1800s) mission timeline.
- Each injury field is plotted as multiple softmax stage probabilities (summing to 1).
- Hover displays source `platform`, `module`, and `observation`.

---

## Maintainer

Palak Wadhwa — [cdcl-lab]
