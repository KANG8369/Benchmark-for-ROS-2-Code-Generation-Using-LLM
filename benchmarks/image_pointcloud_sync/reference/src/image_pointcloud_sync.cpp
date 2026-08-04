// Adapted from cam_sync_ros2 ApproximateTimeSynchronizer pattern:
// https://github.com/berndpfrommer/cam_sync_ros2
//
// Synchronizes Image frames and PointCloud2 messages, then publishes paired
// sensor packets with matched timestamps.

#include "image_pointcloud_sync/image_pointcloud_sync.hpp"

#include <functional>
#include <rclcpp_components/register_node_macro.hpp>

using namespace std::placeholders;

namespace image_pointcloud_sync
{

ImagePointCloudSync::ImagePointCloudSync(const rclcpp::NodeOptions & options)
: Node("image_pointcloud_sync", options)
{
  this->declare_parameter<std::string>("image_topic", "/camera/image_raw");
  this->declare_parameter<std::string>("cloud_topic", "/points");
  this->declare_parameter<std::string>("synced_image_topic", "/synced/image");
  this->declare_parameter<std::string>("synced_cloud_topic", "/synced/points");
  this->declare_parameter<int>("queue_size", 10);
  this->declare_parameter<double>("slop", 0.05);

  image_topic_ = this->get_parameter("image_topic").as_string();
  cloud_topic_ = this->get_parameter("cloud_topic").as_string();
  synced_image_topic_ = this->get_parameter("synced_image_topic").as_string();
  synced_cloud_topic_ = this->get_parameter("synced_cloud_topic").as_string();
  queue_size_ = this->get_parameter("queue_size").as_int();
  const double slop = this->get_parameter("slop").as_double();

  const auto qos = rmw_qos_profile_sensor_data;
  image_sub_ = std::make_shared<message_filters::Subscriber<Image>>(
    this, image_topic_, qos);
  cloud_sub_ = std::make_shared<message_filters::Subscriber<PointCloud2>>(
    this, cloud_topic_, qos);

  synced_image_pub_ = this->create_publisher<Image>(synced_image_topic_, rclcpp::SensorDataQoS());
  synced_cloud_pub_ = this->create_publisher<PointCloud2>(
    synced_cloud_topic_, rclcpp::SensorDataQoS());

  sync_ = std::make_shared<Sync>(SyncPolicy(queue_size_), *image_sub_, *cloud_sub_);
  sync_->setMaxIntervalDuration(rclcpp::Duration::from_seconds(slop));
  sync_->registerCallback(std::bind(&ImagePointCloudSync::syncCallback, this, _1, _2));

  RCLCPP_INFO(
    this->get_logger(),
    "Synchronizing %s with %s -> %s, %s (queue=%d, slop=%.3f)",
    image_topic_.c_str(), cloud_topic_.c_str(),
    synced_image_topic_.c_str(), synced_cloud_topic_.c_str(),
    queue_size_, slop);
}

void ImagePointCloudSync::syncCallback(
  const Image::ConstSharedPtr & image_in,
  const PointCloud2::ConstSharedPtr & cloud_in)
{
  // Align both messages to a common stamp (earlier of the two), following the
  // cam_sync_ros2 approach of emitting paired messages with matched headers.
  const rclcpp::Time t_image(image_in->header.stamp);
  const rclcpp::Time t_cloud(cloud_in->header.stamp);
  const rclcpp::Time matched = (t_cloud < t_image) ? t_cloud : t_image;

  auto image_out = std::make_shared<Image>(*image_in);
  auto cloud_out = std::make_shared<PointCloud2>(*cloud_in);
  image_out->header.stamp = matched;
  cloud_out->header.stamp = matched;

  synced_image_pub_->publish(*image_out);
  synced_cloud_pub_->publish(*cloud_out);
}

}  // namespace image_pointcloud_sync

RCLCPP_COMPONENTS_REGISTER_NODE(image_pointcloud_sync::ImagePointCloudSync)
