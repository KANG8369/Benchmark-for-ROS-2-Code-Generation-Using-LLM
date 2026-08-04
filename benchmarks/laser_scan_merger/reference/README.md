# A ROS2 Laser Scan Merger
![License](https://img.shields.io/badge/license-Apache%202.0-blue)

> A multithreaded laser scan merger, aims to be blazingly fast.
> This package merges up to 9 laser scans with approximate time filter.

![Image](https://github.com/user-attachments/assets/f521140c-4b02-4bea-b2de-64526983cb3d)

## Parameters

| Parameter Name | Type | Default Value | Description |
| --- | --- | --- | --- |
| `scan_topics` | `std::vector<std::string>` | `[]` | List of input laser scan topics to merge. [2 <= scan_topics <= 9] |
| `scan_policies` | `std::vector<int64_t>` | `[]` | Sync policies for each scan topic [0 - reliable, 1 - best effort] |
| `merged_frame_id` | `std::string` | `"base_link"` | Frame ID for the merged laser scan output. |
| `output_topic` | `std::string` | `"merged_scan"` | Topic name to publish the merged laser scan. |
| `debug` | `bool` | `false` | Enables debug output/logging. |
| `moving_frames` | `bool` | `false` | Indicates if scan frames are moving, otherwise transformation will only be calculated once. |
| `queue_size` | `int` | `20` | How many sets of messages it should store from each input filter (by timestamp) while waiting for messages to arrive and complete their "set". Refer to `message_filters` package. |
| `angle_min` | `double` | `-π` | Minimum angle of the merged scan in radians. Defines the start of the angular range. [rad] |
| `angle_max` | `double` | `π` | Maximum angle of the merged scan in radians. Defines the end of the angular range. [rad] |
| `angle_increment` | `double` | `π / 180` | Angular resolution of the merged scan in radians. Smaller values provide higher resolution but larger message sizes. [rad] |
| `range_min` | `double` | `0.1` | Minimum valid range value in meters. Points closer than this distance will be ignored. [m] |
| `range_max` | `double` | `std::numeric_limits<double>::max()` | Maximum valid range value in meters. Points farther than this distance will be ignored. [m] |
| `inf_epsilon` | `double` | `1.0` | Epsilon value for handling infinite range readings. Used to determine when a range should be considered infinite. [m] |
| `use_inf` | `bool` | `true` | Enable reporting of infinite ranges as `+inf` instead of `range_max + inf_epsilon`. |
| `scan_time` | `double` | `1.0 / 30.0` | Expected time between scan rays in seconds. Used for time-based interpolation and synchronization. [s] |
| `min_height` | `double` | `std::numeric_limits<double>::min()` | Minimum height from `merged_frame_id` in which a point is considered. [m] |
| `max_height` | `double` | `std::numeric_limits<double>::max()` | Maximum height from `merged_frame_id` in which a point is considered. [m] |
| `tolerance` | `double` | `0.01` | TF lookup tolerance for transform timing. |

## Build

1. Create workspace
```bash
mkdir ls_ws/src -p
cd ls_ws/src
git clone https://github.com/BruceChanJianLe/laser_scan_merger.git --recurse-submodules
```

2. Install dependencies
```bash
cd ls_ws
rosdep install --from-paths src --ignore-src -r -y
colcon build --symlink-install
source install/setup.bash
```

## Usage

1. Run demo
```bash
ros2 launch laser_scan_merger start_demo.launch.py
```

2. Use your own robot config file
```bash
cd ls_ws/src/laser_scan_merger/config
mkdir your_robot_config
cp example/param.yaml your_robot_config/param.yaml
# Now you may update your param.yaml based on your own requirement
```

3. Launch your own robot config
```bash
ros2 launch laser_scan_merger start.launch.py robotname:=your_robot_config
```
## Code Formatting

This project uses [clang-format](https://clang.llvm.org/docs/ClangFormat.html) for code style.
To format all C++ files:

```bash
find . -name "*.cpp" -o -name "*.hpp" | xargs clang-format -i
```
