# image_pointcloud_sync

Ground-truth reference package for description authoring.

## Intent

Create a ROS 2 C++ package that synchronizes image frames and point clouds, then
publishes paired sensor packets with matched timestamps.

## Source provenance

- Base pattern: [cam_sync_ros2](https://github.com/berndpfrommer/cam_sync_ros2)
  - Uses ROS 2 `message_filters::ApproximateTime` to align sensor streams
  - Original package synchronizes two camera image (+ camera_info) streams and
    republishes them with identical timestamps
- Extension in this package:
  - Synchronize `sensor_msgs/Image` with `sensor_msgs/PointCloud2`
  - Republish paired `/synced/image` and `/synced/points` with matched stamps

## Reference copies

Original cam_sync sources are vendored under `reference/cam_sync_ros2/` for inspection.
