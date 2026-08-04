from launch import LaunchDescription, LaunchContext
from launch_ros.actions import ComposableNodeContainer, Node
from launch_ros.descriptions import ComposableNode
from ament_index_python.packages import get_package_share_directory
from launch.actions import ExecuteProcess, DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration, PathJoinSubstitution
from os import path

ARGUMENTS = [
    DeclareLaunchArgument(
        'robotname',
        default_value='example',
        description='Pass robotname to select configuration for merger',
    )
]

def generate_launch_description():

    container = ComposableNodeContainer(
        package="rclcpp_components",
        executable="component_container",
        name="component_manager_node",
        namespace="",
        composable_node_descriptions=[
            ComposableNode(
                package="laser_scan_merger",
                plugin="util::LaserScanMerger",
                name="laser_scan_merger_node",
                parameters=[PathJoinSubstitution([
                    get_package_share_directory('laser_scan_merger'),
                    'config',
                    LaunchConfiguration('robotname'),
                    'param.yaml'
                ])]
            )
        ],
        output="screen"
    )

    start_rviz2 = Node(
        package="rviz2",
        executable="rviz2",
        output="screen",
        arguments=[
            "-d", path.join(get_package_share_directory("laser_scan_merger"),
            "rviz", "demo.rviz")
        ],
    )

    play_rosbag = ExecuteProcess(
        cmd=[
            "ros2", "bag", "play", "-l",
            path.join(get_package_share_directory("laser_scan_merger"),
            "test", "demo_scan_rosbag", "demo_scan"
        )],
        shell=True,
        output="screen"
    )

    ld = LaunchDescription(ARGUMENTS)
    ld.add_action(container)
    ld.add_action(start_rviz2)
    ld.add_action(play_rosbag)

    return ld
