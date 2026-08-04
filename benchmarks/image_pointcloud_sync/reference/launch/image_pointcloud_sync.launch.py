from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


def generate_launch_description():
    return LaunchDescription([
        DeclareLaunchArgument('image_topic', default_value='/camera/image_raw'),
        DeclareLaunchArgument('cloud_topic', default_value='/points'),
        DeclareLaunchArgument('synced_image_topic', default_value='/synced/image'),
        DeclareLaunchArgument('synced_cloud_topic', default_value='/synced/points'),
        DeclareLaunchArgument('queue_size', default_value='10'),
        DeclareLaunchArgument('slop', default_value='0.05'),
        Node(
            package='image_pointcloud_sync',
            executable='image_pointcloud_sync_node',
            name='image_pointcloud_sync',
            output='screen',
            parameters=[{
                'image_topic': LaunchConfiguration('image_topic'),
                'cloud_topic': LaunchConfiguration('cloud_topic'),
                'synced_image_topic': LaunchConfiguration('synced_image_topic'),
                'synced_cloud_topic': LaunchConfiguration('synced_cloud_topic'),
                'queue_size': LaunchConfiguration('queue_size'),
                'slop': LaunchConfiguration('slop'),
            }],
        ),
    ])
