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
 * @file laser_scan_merger.hpp
 * @author Bruce Chan Jian Le (jianle001@e.ntu.edu.sg)
 * @brief Point cloud merger (up to 9 point cloud)
 * @version 1.0.0
 * @date 2025-05-29
 *
 */
#pragma once

// ROS2
#include "laser_geometry/laser_geometry.hpp"
#include "message_filters/subscriber.h"
#include "message_filters/sync_policies/approximate_time.h"
#include "message_filters/synchronizer.h"
#include "rclcpp/rclcpp.hpp"
#include "sensor_msgs/msg/laser_scan.hpp"
#include "sensor_msgs/msg/point_cloud2.hpp"
#include "tf2/exceptions.h"
#include "tf2_ros/buffer.h"
#include "tf2_ros/transform_listener.h"
#include "tf2_sensor_msgs/tf2_sensor_msgs.hpp"

// PCL
#include <pcl/point_types.h>
#include <pcl_conversions/pcl_conversions.h>

// STL
#include <algorithm>
#include <cmath>
#include <cstdint>
#include <execution>
#include <limits>
#include <memory>
#include <numeric>
#include <variant>
#include <vector>

namespace util {
class LaserScanMerger : public rclcpp::Node {
 public:
  typedef pcl::PointXYZI PointT;
  typedef pcl::PointCloud<PointT> pointCloudT;
  typedef sensor_msgs::msg::LaserScan laserScanMsgT;
  typedef sensor_msgs::msg::LaserScan::ConstSharedPtr laserScanCBMsgPtrT;

  typedef message_filters::NullType nullMsgT;
  typedef message_filters::sync_policies::ApproximateTime<
      laserScanMsgT, laserScanMsgT, laserScanMsgT, laserScanMsgT, laserScanMsgT,
      laserScanMsgT, laserScanMsgT, laserScanMsgT, laserScanMsgT>
      syncPolicyT9;
  typedef message_filters::sync_policies::ApproximateTime<
      laserScanMsgT, laserScanMsgT, laserScanMsgT, laserScanMsgT, laserScanMsgT,
      laserScanMsgT, laserScanMsgT, laserScanMsgT>
      syncPolicyT8;
  typedef message_filters::sync_policies::ApproximateTime<
      laserScanMsgT, laserScanMsgT, laserScanMsgT, laserScanMsgT, laserScanMsgT,
      laserScanMsgT, laserScanMsgT>
      syncPolicyT7;
  typedef message_filters::sync_policies::ApproximateTime<
      laserScanMsgT, laserScanMsgT, laserScanMsgT, laserScanMsgT, laserScanMsgT,
      laserScanMsgT>
      syncPolicyT6;
  typedef message_filters::sync_policies::ApproximateTime<
      laserScanMsgT, laserScanMsgT, laserScanMsgT, laserScanMsgT, laserScanMsgT>
      syncPolicyT5;
  typedef message_filters::sync_policies::ApproximateTime<
      laserScanMsgT, laserScanMsgT, laserScanMsgT, laserScanMsgT>
      syncPolicyT4;
  typedef message_filters::sync_policies::ApproximateTime<
      laserScanMsgT, laserScanMsgT, laserScanMsgT>
      syncPolicyT3;
  typedef message_filters::sync_policies::ApproximateTime<laserScanMsgT,
                                                          laserScanMsgT>
      syncPolicyT2;

  typedef const std::shared_ptr<const laserScanMsgT> laserScanCBMsgT;
  typedef const std::shared_ptr<const nullMsgT> nullCBMsgT;

  typedef std::function<void(
      laserScanCBMsgT&, laserScanCBMsgT&, laserScanCBMsgT&, laserScanCBMsgT&,
      laserScanCBMsgT&, laserScanCBMsgT&, laserScanCBMsgT&, laserScanCBMsgT&,
      laserScanCBMsgT&)>
      cbT9;
  typedef std::function<void(laserScanCBMsgT&, laserScanCBMsgT&,
                             laserScanCBMsgT&, laserScanCBMsgT&,
                             laserScanCBMsgT&, laserScanCBMsgT&,
                             laserScanCBMsgT&, laserScanCBMsgT&, nullCBMsgT&)>
      cbT8;
  typedef std::function<void(laserScanCBMsgT&, laserScanCBMsgT&,
                             laserScanCBMsgT&, laserScanCBMsgT&,
                             laserScanCBMsgT&, laserScanCBMsgT&,
                             laserScanCBMsgT&, nullCBMsgT&, nullCBMsgT&)>
      cbT7;
  typedef std::function<void(laserScanCBMsgT&, laserScanCBMsgT&,
                             laserScanCBMsgT&, laserScanCBMsgT&,
                             laserScanCBMsgT&, laserScanCBMsgT&, nullCBMsgT&,
                             nullCBMsgT&, nullCBMsgT&)>
      cbT6;
  typedef std::function<void(
      laserScanCBMsgT&, laserScanCBMsgT&, laserScanCBMsgT&, laserScanCBMsgT&,
      laserScanCBMsgT&, nullCBMsgT&, nullCBMsgT&, nullCBMsgT&, nullCBMsgT&)>
      cbT5;
  typedef std::function<void(
      laserScanCBMsgT&, laserScanCBMsgT&, laserScanCBMsgT&, laserScanCBMsgT&,
      nullCBMsgT&, nullCBMsgT&, nullCBMsgT&, nullCBMsgT&, nullCBMsgT&)>
      cbT4;
  typedef std::function<void(
      laserScanCBMsgT&, laserScanCBMsgT&, laserScanCBMsgT&, nullCBMsgT&,
      nullCBMsgT&, nullCBMsgT&, nullCBMsgT&, nullCBMsgT&, nullCBMsgT&)>
      cbT3;
  typedef std::function<void(laserScanCBMsgT&, laserScanCBMsgT&, nullCBMsgT&,
                             nullCBMsgT&, nullCBMsgT&, nullCBMsgT&, nullCBMsgT&,
                             nullCBMsgT&, nullCBMsgT&)>
      cbT2;

  /**
   * \brief Construct a new laser scan merger object
   *
   * \param options ros2 node options
   */
  explicit LaserScanMerger(const rclcpp::NodeOptions& opt);
  ~LaserScanMerger() = default;

 private:
  std::vector<std::shared_ptr<message_filters::Subscriber<laserScanMsgT>>>
      scan_subs_;
  std::variant<std::monostate,
               std::unique_ptr<message_filters::Synchronizer<syncPolicyT2>>,
               std::unique_ptr<message_filters::Synchronizer<syncPolicyT3>>,
               std::unique_ptr<message_filters::Synchronizer<syncPolicyT4>>,
               std::unique_ptr<message_filters::Synchronizer<syncPolicyT5>>,
               std::unique_ptr<message_filters::Synchronizer<syncPolicyT6>>,
               std::unique_ptr<message_filters::Synchronizer<syncPolicyT7>>,
               std::unique_ptr<message_filters::Synchronizer<syncPolicyT8>>,
               std::unique_ptr<message_filters::Synchronizer<syncPolicyT9>>>
      scan_sync_;

  std::unique_ptr<tf2_ros::Buffer> buffer_;
  std::shared_ptr<tf2_ros::TransformListener> tf_listener_;
  rclcpp::Publisher<laserScanMsgT>::SharedPtr merged_pub_;
  rclcpp::QoS qos_prof_;
  std::vector<geometry_msgs::msg::TransformStamped> transforms_;
  std::shared_ptr<pointCloudT> merged_cloud_;
  std::vector<std::size_t> indexes_;
  laser_geometry::LaserProjection projection_;

  // Params
  std::vector<std::string> scan_topics_;
  std::vector<int_fast64_t> scan_policies_;
  std::string merged_frame_id_;
  std::string output_topic_;
  bool debug_, first_callback_, moving_frames_, use_inf_;
  int queue_size_;
  double ang_min_;
  double ang_max_;
  double ang_increment_;
  double range_min_;
  double range_max_;
  double inf_eps_;
  double scan_time_;
  double min_height_;
  double max_height_;
  double tolerance_;

  /// @brief Declare parameters
  void loadROSParams();

  /// @brief Undeclare parameters
  void unloadROSParams();

  /// @brief Point Cloud Merger Callback
  void laserScanMergerCB(const std::vector<laserScanCBMsgPtrT>& msgs);

  template <typename... Args>
  void laserScanMergerPrep(Args&&... args);

  template <uint8_t N>
  void initLaserSync();

  /// @brief Start the merging
  void start();
};
}  // namespace util
