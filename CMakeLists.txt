cmake_minimum_required(VERSION 3.10)
project(aws_crt_python C)

set(CMAKE_C_STANDARD 11)

include_directories(source)

add_executable(aws_crt_python
        source/io.c
        source/io.h
        source/module.c
        source/module.h
        source/mqtt_client.c
        source/mqtt_client.h
        source/mqtt_client_connection.c
        source/mqtt_client_connection.h)
