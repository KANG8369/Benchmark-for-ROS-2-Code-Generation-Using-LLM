// Adapted from cam_sync_ros2 ApproximateTimeSynchronizer pattern:
// https://github.com/berndpfrommer/cam_sync_ros2
//
// Extends the stereo-image timestamp alignment approach to Image + PointCloud2
// and republishes a paired sensor packet with matched timestamps.

#ifndef IMAGE_POINTCLOUD_SYNC__IMAGE_POINTCLOUD_SYNC_HPP_
#define IMAGE_POINTCLOUD_SYNC__IMAGE_POINTCLOUD_SYNC_HPP_

#include <message_filters/subscriber.h>
#include <message_filters/sync_policies/approximate_time.h>
#include <message_filters/synchronizer.h>

#include <memory>
#include <rclcpp/rclcpp.hpp>
#include <sensor_msgs/msg/image.hpp>
#include <sensor_msgs/msg/point_cloud2.hpp>
#include <string>

namespace image_pointcloud_sync
{

class ImagePointCloudSync : public rclcpp::Node
{
public:
  using Image = sensor_msgs::msg::Image;
  using PointCloud2 = sensor_msgs::msg::PointCloud2;

  explicit ImagePointCloudSync(const rclcpp::NodeOptions & options = rclcpp::NodeOptions());

private:
  void syncCallback(
    const Image::ConstSharedPtr & image,
    const PointCloud2::ConstSharedPtr & cloud);

  using SyncPolicy = message_filters::sync_policies::ApproximateTime<Image, PointCloud2>;
  using Sync = message_filters::Synchronizer<SyncPolicy>;

  std::string image_topic_;
  std::string cloud_topic_;
  std::string synced_image_topic_;
  std::string synced_cloud_topic_;
  int queue_size_{10};

  std::shared_ptr<message_filters::Subscriber<Image>> image_sub_;
  std::shared_ptr<message_filters::Subscriber<PointCloud2>> cloud_sub_;
  std::shared_ptr<Sync> sync_;

  rclcpp::Publisher<Image>::SharedPtr synced_image_pub_;
  rclcpp::Publisher<PointCloud2>::SharedPtr synced_cloud_pub_;
};

}  // namespace image_pointcloud_sync

#endif  // IMAGE_POINTCLOUD_SYNC__IMAGE_POINTCLOUD_SYNC_HPP_
