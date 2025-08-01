# post_ra_pkg

ROS 2 package for **Post-Run Analysis** of casualty assessments from a ROS bag file, including injury classification plots, observation inspection, and data source tracking.

## 📁 Package Structure

post_ra_ws/
└── src/
└── post_ra_pkg/
├── assessments_with_time.csv
├── observations.json
├── observation_data_sources.json
├── extract_assessments.py
├── extract_assessments_with_runstart.py
├── extract_observations.py
├── extract_observation_data_sources.py
├── plot_every_field_by_casualty_time.py
└── smart_field_plots_time/
└── [auto-generated plots by field and casualty]

---

## How to Run the Pipeline

1. Extract Assessment Messages
```bash
python3 extract_assessments_with_runstart.py
Input: .db3 bag path is hardcoded in the script
Output: assessments_with_time.csv

2. Extract Observations
python3 extract_observations.py
Output: observations.json

3. Extract Observation Data Sources
python3 extract_observation_data_sources.py
Output: observation_data_sources.json

4. Plot Injury Field Data by Casualty Over Time
python3 plot_every_field_by_casualty_time.py
Output:
Plots stored inside:
smart_field_plots_time/
├── severe_hemorrhage/
├── trauma_head/
├── trauma_upper_ext/
├── trauma_lower_ext/
└── respiratory_distress/
