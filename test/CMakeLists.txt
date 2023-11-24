cmake_minimum_required(VERSION 3.23)

project(ninja-dep)

set(CMAKE_EXPORT_COMPILE_COMMANDS ON)

add_library(calc "src/calculator.cpp")
target_include_directories(calc PUBLIC "used_inc")

add_executable(app "src/main.cpp")
target_include_directories(app PUBLIC "not_used_inc")

target_link_libraries(app calc)
