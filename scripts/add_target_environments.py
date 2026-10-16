"""Add reviewed target-environment statements to applicable descriptions."""

from __future__ import annotations

import argparse
from pathlib import Path

import yaml


TARGET_ENVIRONMENTS = {
    "apriltag_ros": "A calibrated monocular camera system observing AprilTags.",
    "depthimage_to_pointcloud2": (
        "An RGB-D camera system providing aligned depth and color images with "
        "depth-camera calibration."
    ),
    "dummy_robot_bringup": "A ROS 2 demonstration environment using the single-RRBot model.",
    "dummy_sensors": "A test or simulation environment using the single-RRBot model.",
    "human_detector": (
        "A calibrated RGB-D camera system providing aligned RGB and depth images."
    ),
    "image_pointcloud_sync": "A camera-and-lidar sensor-fusion system.",
    "image_proc": "A calibrated monocular-camera image-processing pipeline.",
    "laser_scan_merger": (
        "A robot equipped with two to nine 2D laser scanners whose frames are "
        "connected through TF."
    ),
    "nav2_waypoint_follower": "A Nav2-enabled mobile robot.",
    "stereo_image_proc": "A calibrated stereo-camera processing system.",
    "turtlebot3_aruco_tracker": (
        "A TurtleBot3 mobile robot equipped with a calibrated RGB camera and "
        "observing ArUco markers."
    ),
    "turtlebot3_automatic_parking": (
        "A TurtleBot3 mobile robot equipped with a supported 2D lidar and odometry "
        "in a reflective-marker parking environment."
    ),
    "turtlebot3_follower": "A multi-robot system using TurtleBot3 mobile robots.",
    "turtlebot3_yolo_object_detection": (
        "A TurtleBot3 mobile robot equipped with an RGB camera and a compatible "
        "YOLO model."
    ),
    "wall_follower_ros2": (
        "A differential-drive mobile robot equipped with a 2D lidar."
    ),
}

INTENTIONALLY_OMITTED = {"dummy_map_server", "image_tools"}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("repository", type=Path)
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()

    benchmark_root = args.repository.resolve() / "benchmarks"
    case_ids = {
        path.name
        for path in benchmark_root.iterdir()
        if path.is_dir() and (path / "description.yaml").is_file()
    }
    if case_ids != set(TARGET_ENVIRONMENTS) | INTENTIONALLY_OMITTED:
        raise ValueError("target-environment review does not cover the complete case set")

    for case_id in sorted(case_ids):
        path = benchmark_root / case_id / "description.yaml"
        description = yaml.safe_load(path.read_text(encoding="utf-8"))
        if not isinstance(description, dict):
            raise ValueError(f"description must be a mapping: {path}")

        if case_id in INTENTIONALLY_OMITTED:
            if "target_environment" in description:
                raise ValueError(f"target_environment should be omitted: {case_id}")
            print(f"{case_id}: intentionally omitted")
            continue

        expected = TARGET_ENVIRONMENTS[case_id]
        current = description.get("target_environment")
        if current is not None and current != expected:
            raise ValueError(f"unexpected existing target_environment: {case_id}")
        if current == expected:
            print(f"{case_id}: already present")
            continue

        updated = path.read_text(encoding="utf-8").rstrip()
        updated += f"\n\ntarget_environment: >-\n  {expected}\n"
        parsed = yaml.safe_load(updated)
        if parsed.get("target_environment") != expected:
            raise ValueError(f"target_environment write validation failed: {case_id}")
        if args.write:
            path.write_text(updated, encoding="utf-8")
        print(f"{case_id}: {'written' if args.write else 'ready'}")


if __name__ == "__main__":
    main()
