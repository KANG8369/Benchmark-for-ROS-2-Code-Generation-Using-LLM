/**
 * Copyright 2025 Bruce Chan Jian Le
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *     http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 *
 * @file laser_scan_merger.cpp
 * @author Bruce Chan Jian Le (jianle001@e.ntu.edu.sg)
 * @brief Laser scan merger (up to 9 laser scan)
 * @version 1.0.0
 * @date 2025-05-29
 *
 */
#include "laser_scan_merger/laser_scan_merger.hpp"

#include "rclcpp_components/register_node_macro.hpp"
RCLCPP_COMPONENTS_REGISTER_NODE(util::LaserScanMerger)

namespace util {
LaserScanMerger::LaserScanMerger(const rclcpp::NodeOptions& opts)
    : rclcpp::Node{"component_laser_scan_merger", opts},
      buffer_{std::make_unique<tf2_ros::Buffer>(get_clock())},
      tf_listener_{std::make_shared<tf2_ros::TransformListener>(*buffer_)},
      qos_prof_{5},
      debug_{false},
      first_callback_{true},
      moving_frames_{false},
      queue_size_{10} {
  // Load ROS params
  loadROSParams();
  // Start merger
  start();

  RCLCPP_INFO_STREAM(get_logger(), get_name()
                                       << ": Started point cloud merger node.");
}

void LaserScanMerger::loadROSParams() {
  // Declare params
  declare_parameter("scan_topics", std::vector<std::string>{});
  declare_parameter("scan_policies", std::vector<int_fast64_t>{});
  declare_parameter("merged_frame_id", "");
  declare_parameter("output_topic", "");
  declare_parameter("debug", false);
  declare_parameter("moving_frames", false);
  declare_parameter("queue_size", 20);
  declare_parameter("angle_min", -M_PI);
  declare_parameter("angle_max", M_PI);
  declare_parameter("angle_increment", M_PI / 180.0);  // 1 degree
  declare_parameter("range_min", 0.1);
  declare_parameter("range_max", std::numeric_limits<double>::max());
  declare_parameter("inf_epsilon", 1.0);
  declare_parameter("use_inf", true);
  declare_parameter("scan_time", 1.0 / 30.0);
  declare_parameter("min_height", std::numeric_limits<double>::min());
  declare_parameter("max_height", std::numeric_limits<double>::max());
  declare_parameter("tolerance", 0.01);

  // Obtain params value
  get_parameter("scan_topics", scan_topics_);
  get_parameter("scan_policies", scan_policies_);
  get_parameter("merged_frame_id", merged_frame_id_);
  get_parameter("output_topic", output_topic_);
  get_parameter("debug", debug_);
  get_parameter("moving_frames", moving_frames_);
  get_parameter("queue_size", queue_size_);
  get_parameter("angle_min", ang_min_);
  get_parameter("angle_max", ang_max_);
  get_parameter("angle_increment", ang_increment_);
  get_parameter("range_min", range_min_);
  get_parameter("range_max", range_max_);
  get_parameter("inf_epsilon", inf_eps_);
  get_parameter("use_inf", use_inf_);
  get_parameter("scan_time", scan_time_);
  get_parameter("min_height", min_height_);
  get_parameter("max_height", max_height_);
  get_parameter("tolerance", tolerance_);

  if (debug_) {
    std::string topics;
    for (const auto& topic : scan_topics_) {
      topics += topic + ", ";
    }
    topics.erase(topics.end() - 2, topics.end() - 1);

    RCLCPP_INFO_STREAM(get_logger(),
                       " (" << __func__ << ") Laser scan topics: " << topics);

    RCLCPP_INFO_STREAM(get_logger(), " (" << __func__
                                          << ") Laser scans are moving frame: "
                                          << moving_frames_);
  }

  // Sanity check
  if (output_topic_.empty()) {
    if (debug_)
      RCLCPP_INFO_STREAM(
          get_logger(), " ("
                            << __func__
                            << ") Merged scan output topic is empty, "
                               "it will be set to default name (merged_scan).");
    output_topic_ = "merged_scan";
  }

  if (scan_topics_.size() > 9) {
    RCLCPP_ERROR_STREAM(
        get_logger(),
        " (" << __func__
             << ") currently only support merging up to 9 laser scans.");
    return;
  } else if (scan_topics_.size() < 2) {
    RCLCPP_ERROR_STREAM(
        get_logger(), " (" << __func__ << ") input scan topic is less than 2.");
    return;
  }

  if (scan_policies_.size() < scan_topics_.size()) {
    // Auto fill if not filled
    RCLCPP_WARN_STREAM(
        get_logger(),
        " (" << __func__
             << ") policies and topics size mismatch or not found... "
                "auto filling QoS reliable...");
    scan_policies_.resize(scan_topics_.size(), 0);
  } else if (scan_policies_.size() > scan_topics_.size()) {
    RCLCPP_WARN_STREAM(
        get_logger(),
        " (" << __func__
             << ") policies > topics size, ignoring additional policies.");
  }

  // Create indexes
  indexes_.resize(scan_topics_.size());
  std::iota(indexes_.begin(), indexes_.end(), 0);
}

void LaserScanMerger::unloadROSParams() {
  undeclare_parameter("scan_topics");
  undeclare_parameter("scan_policies");
  undeclare_parameter("merged_frame_id");
  undeclare_parameter("output_topic");
  undeclare_parameter("debug");
  undeclare_parameter("moving_frames");
  undeclare_parameter("queue_size");
  undeclare_parameter("angle_min");
  undeclare_parameter("angle_max");
  undeclare_parameter("angle_increment");
  undeclare_parameter("range_min");
  undeclare_parameter("range_max");
  undeclare_parameter("inf_epsilon");
  undeclare_parameter("use_inf");
  undeclare_parameter("scan_time");
  undeclare_parameter("min_height");
  undeclare_parameter("max_height");
  undeclare_parameter("tolerance");
}

void LaserScanMerger::laserScanMergerCB(
    const std::vector<laserScanCBMsgPtrT>& msgs) {
  // Only execute when there is at least one subscriber
  if (merged_pub_->get_subscription_count() == 0) {
    RCLCPP_WARN_STREAM_ONCE(get_logger(),
                            " (" << __func__
                                 << "): merged scan will only be published "
                                    "when there is at least one subscriber.");
    return;
  }

  sensor_msgs::msg::PointCloud2::SharedPtr cloud_sources[9];
  merged_cloud_ = std::make_shared<pointCloudT>();

  if (first_callback_ || moving_frames_) {
    // Clean list for retry
    transforms_.clear();
    try {
      std::for_each(indexes_.begin(), indexes_.end(), [&, this](auto& index) {
        if (buffer_->canTransform(
                merged_frame_id_, msgs[index]->header.frame_id, rclcpp::Time(0),
                rclcpp::Duration::from_nanoseconds(tolerance_))) {
          transforms_.emplace_back(buffer_->lookupTransform(
              merged_frame_id_, msgs[index]->header.frame_id, rclcpp::Time(0),
              rclcpp::Duration::from_nanoseconds(tolerance_)));
        }
      });
    } catch (const tf2::TransformException& e) {
      RCLCPP_ERROR_STREAM(get_logger(),
                          " (" << __func__
                               << ") caught tf2 transformException while "
                                  "performing first transformation: "
                               << e.what());
      return;  // Retry
    }

    if (scan_topics_.size() == transforms_.size()) {
      first_callback_ = false;
    } else {
      return;  // Retry
    }
  }

  // Convert and merge scans
  try {
    std::for_each(indexes_.begin(), indexes_.end(), [&, this](auto& index) {
      // Init cloud place holder
      cloud_sources[index] = std::make_shared<sensor_msgs::msg::PointCloud2>();
      // Scan -> cloud
      projection_.projectLaser(*msgs[index], *cloud_sources[index]);
      // transform cloud
      tf2::doTransform(*cloud_sources[index], *cloud_sources[index],
                       transforms_[index]);
    });
  } catch (const tf2::TransformException& e) {
    RCLCPP_ERROR_STREAM(
        get_logger(),
        " (" << __func__
             << ") caught tf2 transformException while transformation scans: "
             << e.what());
    return;  // Retry
  }

  // Consolidate the clouds
  std::for_each(indexes_.begin(), indexes_.end(), [&, this](auto& index) {
    pointCloudT cloud;
    pcl::fromROSMsg(*cloud_sources[index], cloud);
    *merged_cloud_ += cloud;
  });

  // Convert merged cloud to merged scan
  auto scan_msg = std::make_unique<sensor_msgs::msg::LaserScan>();
  scan_msg->header = msgs.front()->header;
  scan_msg->header.frame_id = merged_frame_id_;

  scan_msg->angle_min = ang_min_;
  scan_msg->angle_max = ang_max_;
  scan_msg->angle_increment = ang_increment_;
  scan_msg->time_increment = 0.0;
  scan_msg->scan_time = scan_time_;
  scan_msg->range_min = range_min_;
  scan_msg->range_max = range_max_;

  // determine amount of rays to create
  uint32_t ranges_size = std::ceil((scan_msg->angle_max - scan_msg->angle_min) /
                                   scan_msg->angle_increment);

  // determine if laserscan rays with no obstacle data will evaluate to infinity
  // or max_range
  if (use_inf_) {
    scan_msg->ranges.assign(ranges_size,
                            std::numeric_limits<double>::infinity());
  } else {
    scan_msg->ranges.assign(ranges_size, scan_msg->range_max + inf_eps_);
  }

  // Iterate through pointcloud
  std::for_each(
      std::execution::par_unseq, merged_cloud_->points.begin(),
      merged_cloud_->points.end(), [this, &scan_msg](const auto& point) {
        if (std::isnan(point.x) || std::isnan(point.y) || std::isnan(point.z)) {
          RCLCPP_DEBUG(get_logger(), "rejected for nan in point(%f, %f, %f)\n",
                       point.x, point.y, point.z);
          return;
        }

        if (point.z > max_height_ || point.z < min_height_) {
          RCLCPP_DEBUG(get_logger(),
                       "rejected for height %f not in range (%f, %f)\n",
                       point.z, min_height_, max_height_);
          return;
        }

        double range = std::hypot(point.x, point.y);
        if (range < range_min_) {
          RCLCPP_DEBUG(get_logger(),
                       "rejected for range %f below minimum value %f. Point: "
                       "(%f, %f, %f)",
                       range, range_min_, point.x, point.y, point.z);
          return;
        }
        if (range > range_max_) {
          RCLCPP_DEBUG(get_logger(),
                       "rejected for range %f above maximum value %f. Point: "
                       "(%f, %f, %f)",
                       range, range_max_, point.x, point.y, point.z);
          return;
        }

        double angle = std::atan2(point.y, point.x);
        if (angle < scan_msg->angle_min || angle > scan_msg->angle_max) {
          RCLCPP_DEBUG(get_logger(),
                       "rejected for angle %f not in range (%f, %f)\n", angle,
                       scan_msg->angle_min, scan_msg->angle_max);
          return;
        }

        // overwrite range at laserscan ray if new range is smaller
        int index = (angle - scan_msg->angle_min) / scan_msg->angle_increment;
        if (range < scan_msg->ranges[index]) {
          scan_msg->ranges[index] = range;
        }
      });

  merged_pub_->publish(std::move(scan_msg));
}

template <typename... Args>
void LaserScanMerger::laserScanMergerPrep(Args&&... args) {
  laserScanMergerCB({std::forward<Args>(args)...});
}
// Initialize sync
template <uint8_t N>
void LaserScanMerger::initLaserSync() {}

template <>
void LaserScanMerger::initLaserSync<2u>() {
  scan_sync_ = std::make_unique<message_filters::Synchronizer<syncPolicyT2>>(
      syncPolicyT2(queue_size_), *scan_subs_[0], *scan_subs_[1]);
  if (auto v = std::get_if<
          std::unique_ptr<message_filters::Synchronizer<syncPolicyT2>>>(
          &scan_sync_)) {
    (*v)->registerCallback<cbT2>([this](auto& cloud0, auto& cloud1, ...) {
      laserScanMergerPrep(cloud0, cloud1);
    });
  }
}

template <>
void LaserScanMerger::initLaserSync<3u>() {
  scan_sync_ = std::make_unique<message_filters::Synchronizer<syncPolicyT3>>(
      syncPolicyT3(queue_size_), *scan_subs_[0], *scan_subs_[1],
      *scan_subs_[2]);
  if (auto v = std::get_if<
          std::unique_ptr<message_filters::Synchronizer<syncPolicyT3>>>(
          &scan_sync_)) {
    (*v)->registerCallback<cbT3>(
        [this](auto& cloud0, auto& cloud1, auto& cloud2, ...) {
          laserScanMergerPrep(cloud0, cloud1, cloud2);
        });
  }
}

template <>
void LaserScanMerger::initLaserSync<4u>() {
  scan_sync_ = std::make_unique<message_filters::Synchronizer<syncPolicyT4>>(
      syncPolicyT4(queue_size_), *scan_subs_[0], *scan_subs_[1], *scan_subs_[2],
      *scan_subs_[3]);
  if (auto v = std::get_if<
          std::unique_ptr<message_filters::Synchronizer<syncPolicyT4>>>(
          &scan_sync_)) {
    (*v)->registerCallback<cbT4>(
        [this](auto& cloud0, auto& cloud1, auto& cloud2, auto& cloud3, ...) {
          laserScanMergerPrep(cloud0, cloud1, cloud2, cloud3);
        });
  }
}

template <>
void LaserScanMerger::initLaserSync<5u>() {
  scan_sync_ = std::make_unique<message_filters::Synchronizer<syncPolicyT5>>(
      syncPolicyT5(queue_size_), *scan_subs_[0], *scan_subs_[1], *scan_subs_[2],
      *scan_subs_[3], *scan_subs_[4]);
  if (auto v = std::get_if<
          std::unique_ptr<message_filters::Synchronizer<syncPolicyT5>>>(
          &scan_sync_)) {
    (*v)->registerCallback<cbT5>([this](auto& cloud0, auto& cloud1,
                                        auto& cloud2, auto& cloud3,
                                        auto& cloud4, ...) {
      laserScanMergerPrep(cloud0, cloud1, cloud2, cloud3, cloud4);
    });
  }
}

template <>
void LaserScanMerger::initLaserSync<6u>() {
  scan_sync_ = std::make_unique<message_filters::Synchronizer<syncPolicyT6>>(
      syncPolicyT6(queue_size_), *scan_subs_[0], *scan_subs_[1], *scan_subs_[2],
      *scan_subs_[3], *scan_subs_[4], *scan_subs_[5]);
  if (auto v = std::get_if<
          std::unique_ptr<message_filters::Synchronizer<syncPolicyT6>>>(
          &scan_sync_)) {
    (*v)->registerCallback<cbT6>([this](auto& cloud0, auto& cloud1,
                                        auto& cloud2, auto& cloud3,
                                        auto& cloud4, auto& cloud5, ...) {
      laserScanMergerPrep(cloud0, cloud1, cloud2, cloud3, cloud4, cloud5);
    });
  }
}

template <>
void LaserScanMerger::initLaserSync<7u>() {
  scan_sync_ = std::make_unique<message_filters::Synchronizer<syncPolicyT7>>(
      syncPolicyT7(queue_size_), *scan_subs_[0], *scan_subs_[1], *scan_subs_[2],
      *scan_subs_[3], *scan_subs_[4], *scan_subs_[5], *scan_subs_[6]);
  if (auto v = std::get_if<
          std::unique_ptr<message_filters::Synchronizer<syncPolicyT7>>>(
          &scan_sync_)) {
    (*v)->registerCallback<cbT7>(
        [this](auto& cloud0, auto& cloud1, auto& cloud2, auto& cloud3,
               auto& cloud4, auto& cloud5, auto& cloud6, ...) {
          laserScanMergerPrep(cloud0, cloud1, cloud2, cloud3, cloud4, cloud5,
                              cloud6);
        });
  }
}

template <>
void LaserScanMerger::initLaserSync<8u>() {
  scan_sync_ = std::make_unique<message_filters::Synchronizer<syncPolicyT8>>(
      syncPolicyT8(queue_size_), *scan_subs_[0], *scan_subs_[1], *scan_subs_[2],
      *scan_subs_[3], *scan_subs_[4], *scan_subs_[5], *scan_subs_[6],
      *scan_subs_[7]);
  if (auto v = std::get_if<
          std::unique_ptr<message_filters::Synchronizer<syncPolicyT8>>>(
          &scan_sync_)) {
    (*v)->registerCallback<cbT8>(
        [this](auto& cloud0, auto& cloud1, auto& cloud2, auto& cloud3,
               auto& cloud4, auto& cloud5, auto& cloud6, auto& cloud7, ...) {
          laserScanMergerPrep(cloud0, cloud1, cloud2, cloud3, cloud4, cloud5,
                              cloud6, cloud7);
        });
  }
}

template <>
void LaserScanMerger::initLaserSync<9u>() {
  scan_sync_ = std::make_unique<message_filters::Synchronizer<syncPolicyT9>>(
      syncPolicyT9(queue_size_), *scan_subs_[0], *scan_subs_[1], *scan_subs_[2],
      *scan_subs_[3], *scan_subs_[4], *scan_subs_[5], *scan_subs_[6],
      *scan_subs_[7], *scan_subs_[8]);
  if (auto v = std::get_if<
          std::unique_ptr<message_filters::Synchronizer<syncPolicyT9>>>(
          &scan_sync_)) {
    (*v)->registerCallback<cbT9>(
        [this](auto& cloud0, auto& cloud1, auto& cloud2, auto& cloud3,
               auto& cloud4, auto& cloud5, auto& cloud6, auto& cloud7,
               auto& cloud8) {
          laserScanMergerPrep(cloud0, cloud1, cloud2, cloud3, cloud4, cloud5,
                              cloud6, cloud7, cloud8);
        });
  }
}

void LaserScanMerger::start() {
  // Initialize merged laser scan
  merged_cloud_ = std::make_shared<pointCloudT>();

  std::for_each(indexes_.begin(), indexes_.end(), [this](auto& index) {
    if (scan_policies_[index] == 0) {
      // reliable
      qos_prof_.reliable();
    } else {
      // best effort
      qos_prof_.best_effort();
    }

    // Create subscriber for each given scan topic
    scan_subs_.emplace_back(
        std::make_shared<message_filters::Subscriber<laserScanMsgT>>(
            this, scan_topics_[index], qos_prof_.get_rmw_qos_profile()));
  });

  switch (scan_subs_.size()) {
    case 2:
      initLaserSync<2u>();
      break;

    case 3:
      initLaserSync<3u>();
      break;

    case 4:
      initLaserSync<4u>();
      break;

    case 5:
      initLaserSync<5u>();
      break;

    case 6:
      initLaserSync<6u>();
      break;

    case 7:
      initLaserSync<7u>();
      break;

    case 8:
      initLaserSync<8u>();
      break;

    case 9:
      initLaserSync<9u>();
      break;

    default:
      RCLCPP_ERROR_STREAM(get_logger(),
                          "(" << __func__ << ") Failed to init scan sync.");
      return;
  }

  // Initialize merged publisher
  merged_pub_ = create_publisher<sensor_msgs::msg::LaserScan>(output_topic_, 1);
  // Prepare local transformation list
  transforms_.reserve(scan_topics_.size());
}
}  // namespace util
