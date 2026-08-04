cmake_minimum_required(VERSION 3.8)
project(image_pointcloud_sync)

if(CMAKE_COMPILER_IS_GNUCXX OR CMAKE_CXX_COMPILER_ID MATCHES "Clang")
  add_compile_options(-Wall -Wextra -Wpedantic)
endif()

find_package(ament_cmake REQUIRED)
find_package(message_filters REQUIRED)
find_package(rclcpp REQUIRED)
find_package(rclcpp_components REQUIRED)
find_package(sensor_msgs REQUIRED)

add_library(${PROJECT_NAME}_node SHARED
  src/image_pointcloud_sync.cpp)

target_include_directories(${PROJECT_NAME}_node PUBLIC
  $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/include>
  $<INSTALL_INTERFACE:include>)

ament_target_dependencies(${PROJECT_NAME}_node
  message_filters
  rclcpp
  rclcpp_components
  sensor_msgs)

rclcpp_components_register_node(${PROJECT_NAME}_node
  PLUGIN "image_pointcloud_sync::ImagePointCloudSync"
  EXECUTABLE image_pointcloud_sync_node)

install(TARGETS ${PROJECT_NAME}_node
  ARCHIVE DESTINATION lib
  LIBRARY DESTINATION lib
  RUNTIME DESTINATION bin)

install(DIRECTORY include/
  DESTINATION include)

install(DIRECTORY launch reference
  DESTINATION share/${PROJECT_NAME})

ament_package()
