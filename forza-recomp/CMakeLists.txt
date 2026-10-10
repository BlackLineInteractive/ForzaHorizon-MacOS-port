# forza - ReXGlue Recompiled Project (Forza Horizon, 4D5309C9)
#
# SDK boilerplate lives in generated/rexglue.cmake. The codegen-on-first-configure,
# cross-build and patched-GPU-plugin blocks are adapted from RecompiledHaloReach.

cmake_minimum_required(VERSION 3.25)
project(forza LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 23)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

# Builds handed a finished generated/ (CI building from the private copy of the codegen
# output) have no default.xex to run codegen on.
option(FORZA_SKIP_CODEGEN "Compile generated/ as it is, never run codegen" OFF)
if(FORZA_SKIP_CODEGEN AND NOT EXISTS "${CMAKE_CURRENT_SOURCE_DIR}/generated/default/sources.cmake")
    message(FATAL_ERROR "FORZA_SKIP_CODEGEN is on but generated/default has no codegen output")
endif()

# generated/rexglue.cmake lists the generated sources at configure time, so on a fresh
# checkout (no generated/default yet) codegen runs here once; otherwise the first build
# would run it but compile none of its output.
if(NOT CMAKE_CROSSCOMPILING AND NOT REXSDK_DIR AND
   NOT EXISTS "${CMAKE_CURRENT_SOURCE_DIR}/generated/default/sources.cmake")
    find_package(rexglue 0.10.0 REQUIRED CONFIG)
    get_target_property(_rexglue rex::rexglue LOCATION)
    message(STATUS "First configure: running codegen (${_rexglue}), this takes a while")
    execute_process(
        COMMAND "${_rexglue}" codegen "${CMAKE_CURRENT_SOURCE_DIR}/forza_manifest.toml"
        WORKING_DIRECTORY "${CMAKE_CURRENT_SOURCE_DIR}"
        COMMAND_ERROR_IS_FATAL ANY)
endif()

include(generated/rexglue.cmake)

# A cross build compiles the generated code the native build made; it must not run
# codegen itself (the SDK's rexglue for the target cannot run here, and regenerating
# would rewrite generated/ under the native build). The build-time codegen step stays
# (rexglue.cmake orders the generated sources after it) but runs true instead.
if((CMAKE_CROSSCOMPILING OR FORZA_SKIP_CODEGEN) AND TARGET rex::rexglue)
    set_target_properties(rex::rexglue PROPERTIES
        IMPORTED_LOCATION /usr/bin/true IMPORTED_LOCATION_RELEASE /usr/bin/true)
    message(STATUS "Codegen is skipped: compiling generated/ as it is")
endif()

# Sources
set(FORZA_SOURCES
    src/main.cpp
    src/debug/audio_level.cpp
    src/debug/cpu_profile.cpp
    src/debug/fault_guard.cpp
    src/debug/fiber_trace.cpp
    src/debug/frame_stats.cpp
    src/debug/thread_trace.cpp
    src/debug/frame_dump.cpp
    src/hooks/gjk_dot_overflow.cpp
    src/hooks/physics_loader_check.cpp
    src/kernel/critical_section.cpp
    src/kernel/file_delete_on_close.cpp
    src/kernel/file_size_refresh.cpp
    src/kernel/input_autopress.cpp
    src/kernel/identity.cpp
    src/kernel/live_lsp.cpp
    src/kernel/live_tcp.cpp
    src/kernel/live_xmsg.cpp
    src/kernel/net.cpp
    src/kernel/xam_enumerate.cpp
    src/kernel/xam_nui.cpp
    src/kernel/xam_signin.cpp
    src/kernel/xecrypt_rsa.cpp
    src/kernel/xekeys.cpp
    src/platform/achievement_toast.cpp
    src/platform/sdk_import.cpp
    src/platform/socket.cpp
    src/platform/vulkan_hooks.cpp
)

if(WIN32)
    add_executable(forza WIN32 ${FORZA_SOURCES})
    target_compile_definitions(forza PRIVATE _CRT_SECURE_NO_WARNINGS)
    target_link_libraries(forza PRIVATE ws2_32)
else()
    add_executable(forza ${FORZA_SOURCES})
endif()

rexglue_setup_target(forza GPU_PLUGINS xenos)

# src/platform/vulkan_hooks.cpp (and the app header) include the SDK's Vulkan headers,
# which include <renderdoc_app.h> from this interface target and the X11/Wayland client
# headers (stand-ins in src/platform/wsi_stubs, so no window-system packages are needed).
# From RecompiledHaloReach.
if(TARGET rex::renderdoc)
    target_link_libraries(forza PRIVATE rex::renderdoc)
endif()
if(UNIX AND NOT APPLE)
    set_source_files_properties(src/platform/vulkan_hooks.cpp PROPERTIES
        INCLUDE_DIRECTORIES "${CMAKE_CURRENT_SOURCE_DIR}/src/platform/wsi_stubs")
endif()

# The stock SDK Xenos plugin has rendering bugs (e.g. it reads the texture-fetch
# exponent bias from the wrong fetch-constant word, which darkens textures 256x).
# tools/build_rexglue_sdk.sh builds a patched plugin; this copies it over the SDK
# one that rexglue_setup_target() stages next to the binary.
# This project's overlay first; RecompiledHaloReach's (same patch set so far) otherwise.
set(_forza_plugin "$ENV{HOME}/rexglue-sdk-patched-forza/0.10.0.24/linux-amd64/lib/librexgpu-xenos.so")
if(NOT EXISTS "${_forza_plugin}")
    set(_forza_plugin "$ENV{HOME}/rexglue-sdk-patched/0.10.0.24/linux-amd64/lib/librexgpu-xenos.so")
endif()
set(FORZA_XENOS_PLUGIN "${_forza_plugin}"
    CACHE FILEPATH "Patched librexgpu-xenos.so to ship instead of the SDK's")
if(UNIX AND NOT APPLE)
    if(EXISTS "${FORZA_XENOS_PLUGIN}")
        add_custom_command(TARGET forza POST_BUILD
            COMMAND ${CMAKE_COMMAND} -E copy_if_different
                "${FORZA_XENOS_PLUGIN}" "$<TARGET_FILE_DIR:forza>/librexgpu-xenos.so"
            VERBATIM)
    else()
        message(WARNING "Patched GPU plugin not found at ${FORZA_XENOS_PLUGIN}; "
                        "textures will render dark. Run tools/build_rexglue_sdk.sh.")
    endif()
endif()

# The SDK runtime dlopen()s guest-DLL modules by bare target name on Linux
# (no "lib" prefix, no ".so" suffix), so emit the libraries under that name.
if(UNIX AND NOT APPLE)
    foreach(_module forza_XMediaFacade_default forza_SpeechFacade_default)
        if(TARGET ${_module})
            set_target_properties(${_module} PROPERTIES PREFIX "" SUFFIX "")
        endif()
    endforeach()
endif()
