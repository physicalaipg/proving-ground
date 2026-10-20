set(srcs "main.c" "drive.c" "sensors.c")
# 自检钩子（内部治理仓 内部工单）：缺省关。只许编在单独的构建目录里，生产构建目录 build/ 出不了自检固件：
#   idf.py -B build-selftest -D YB_SELFTEST=1 build
if(YB_SELFTEST)
    if(NOT CMAKE_BINARY_DIR MATCHES "build-selftest$")
        message(FATAL_ERROR "自检固件只许编在 build-selftest 目录：idf.py -B build-selftest -D YB_SELFTEST=1 build")
    endif()
    list(APPEND srcs "selftest.c")
endif()
idf_component_register(SRCS ${srcs}
                       INCLUDE_DIRS "."
                       REQUIRES bootloader_support driver esp_adc esp_timer proto)
if(YB_SELFTEST)
    target_compile_definitions(${COMPONENT_LIB} PRIVATE YB_SELFTEST=1)
endif()
