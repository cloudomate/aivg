cmake_minimum_required(VERSION 3.20)

# libaivg-sat — C++17 WebRTC satellite-client SDK (feature 020).
# One source tree, two build profiles behind one public API:
#   - POSIX tier (Linux/macOS/RPi Zero 2 W) — the project() build below.
#   - ESP32-S3 tier (ESP-IDF) — the ESP_PLATFORM branch (feature 005).
# Transport: libpeer (MIT). The gateway/wire contract (0.2.0) is unchanged.

# --- ESP32-S3 tier: register as an ESP-IDF component and stop ----------------
# When ESP-IDF's CMake processes this directory as a component, ESP_PLATFORM is
# defined. We register the ESP source set (esp_websocket_client WS client +
# control + voice planes) and return before the POSIX project() setup.
# Consumed by device firmware (aivg-devices/devices/respeaker-xvf3800-esp32s3)
# via a path dependency in its idf_component.yml.
if(ESP_PLATFORM)
  idf_component_register(
    SRCS
      src/state_machine.cpp
      src/reconnect.cpp
      src/proto/messages.cpp
      src/control_plane.cpp
      src/platform/ws_client_espidf.cpp
      src/signaling.cpp
      src/transport/opus_bridge.cpp
      src/transport/libpeer_transport.cpp
      src/voice_session.cpp
      src/satellite.cpp
    INCLUDE_DIRS include
    PRIV_INCLUDE_DIRS src third_party
    REQUIRES esp_websocket_client
    PRIV_REQUIRES libpeer opus)
  target_compile_features(${COMPONENT_LIB} PUBLIC cxx_std_17)
  target_compile_definitions(${COMPONENT_LIB} PRIVATE AIVG_SAT_ENABLE_VOICE=1)
  return()
endif()

project(aivg_sat LANGUAGES CXX VERSION 0.1.0)

option(AIVG_SAT_BUILD_EXAMPLES "Build the reference smoke samples" OFF)
option(AIVG_SAT_BUILD_TESTS "Build unit/compile-check tests" OFF)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)

# --- Public headers (the API contract; dependency-free, compile standalone) ---
add_library(aivg_sat_headers INTERFACE)
target_include_directories(aivg_sat_headers INTERFACE
  $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/include>
  $<INSTALL_INTERFACE:include>)
target_compile_features(aivg_sat_headers INTERFACE cxx_std_17)
add_library(aivg::sat_headers ALIAS aivg_sat_headers)

# --- Core library ------------------------------------------------------------
# NOTE (feature 020 status): the transport/control-plane .cpp sources below are
# stubs pending the libpeer + mbedTLS integration (tasks T012-T020). The pure
# sources (state_machine) are complete. FetchContent of libpeer/nlohmann_json
# is wired but commented until the integration tasks land, so the verifiable
# slice configures without a network fetch.
set(AIVG_SAT_CORE_SOURCES
  src/state_machine.cpp
  src/reconnect.cpp
)

# nlohmann/json: required for the control-plane proto layer. Provided by apt
# (nlohmann-json3-dev) in the rpi-builder container and on the Pi; on hosts
# without it, the proto layer + proto test are skipped (headers/FSM still build).
find_package(nlohmann_json QUIET)
if(nlohmann_json_FOUND)
  list(APPEND AIVG_SAT_CORE_SOURCES src/proto/messages.cpp)
endif()

# POSIX control-plane WS client (ws://) uses mbedTLS (sha1 + base64) for the
# handshake. mbedcrypto is provided by libmbedtls-dev (apt) and is also a
# libpeer dependency, so no new dependency is introduced.
find_library(MBEDCRYPTO_LIB mbedcrypto)
find_package(Threads QUIET)
set(AIVG_SAT_HAVE_POSIX_WS OFF)
if(MBEDCRYPTO_LIB AND Threads_FOUND AND NOT WIN32)
  list(APPEND AIVG_SAT_CORE_SOURCES src/platform/ws_client_posix.cpp)
  set(AIVG_SAT_HAVE_POSIX_WS ON)
endif()

# Control-plane manager needs the WS client + proto layer.
if(AIVG_SAT_HAVE_POSIX_WS AND nlohmann_json_FOUND)
  list(APPEND AIVG_SAT_CORE_SOURCES src/control_plane.cpp)
endif()

# Voice plane (libpeer WebRTC + Opus). OFF by default because it needs a
# built libpeer; enable with -DAIVG_SAT_ENABLE_VOICE=ON and point
# -DAIVG_SAT_LIBPEER_ROOT=<libpeer source dir with build/src/libpeer.a>.
# Sources are compile-verified against the real libpeer/Opus APIs; the live
# end-to-end turn is validated on-device (RPi Zero 2 W) — see HANDOFF.md.
option(AIVG_SAT_ENABLE_VOICE "Build the libpeer WebRTC voice plane" OFF)
set(AIVG_SAT_LIBPEER_ROOT "" CACHE PATH "Path to a built libpeer source tree")
if(AIVG_SAT_ENABLE_VOICE)
  find_library(OPUS_LIB opus)
  if(NOT (nlohmann_json_FOUND AND AIVG_SAT_HAVE_POSIX_WS AND OPUS_LIB AND AIVG_SAT_LIBPEER_ROOT))
    message(FATAL_ERROR "AIVG_SAT_ENABLE_VOICE needs nlohmann_json, opus, the POSIX WS client, and AIVG_SAT_LIBPEER_ROOT")
  endif()
  list(APPEND AIVG_SAT_CORE_SOURCES
    src/signaling.cpp
    src/transport/opus_bridge.cpp
    src/transport/libpeer_transport.cpp
    src/voice_session.cpp
    src/satellite.cpp)
endif()

add_library(aivg_sat ${AIVG_SAT_CORE_SOURCES})
add_library(aivg::sat ALIAS aivg_sat)
target_link_libraries(aivg_sat PUBLIC aivg_sat_headers)
target_include_directories(aivg_sat PRIVATE ${CMAKE_CURRENT_SOURCE_DIR}/src)
if(nlohmann_json_FOUND)
  target_link_libraries(aivg_sat PRIVATE nlohmann_json::nlohmann_json)
endif()
if(AIVG_SAT_HAVE_POSIX_WS)
  target_link_libraries(aivg_sat PRIVATE ${MBEDCRYPTO_LIB} Threads::Threads)
endif()
if(AIVG_SAT_ENABLE_VOICE)
  target_include_directories(aivg_sat PRIVATE ${AIVG_SAT_LIBPEER_ROOT}/include)
  target_link_libraries(aivg_sat PRIVATE
    ${AIVG_SAT_LIBPEER_ROOT}/build/src/libpeer.a ${OPUS_LIB} ${MBEDCRYPTO_LIB})
endif()

# --- Dependencies (enabled as integration tasks T012-T020 land) --------------
# include(FetchContent)
# FetchContent_Declare(libpeer GIT_REPOSITORY https://github.com/sepfy/libpeer.git GIT_TAG <pin>)
# FetchContent_Declare(nlohmann_json URL https://github.com/nlohmann/json/releases/download/v3.11.3/json.hpp)
# FetchContent_MakeAvailable(libpeer nlohmann_json)
# target_link_libraries(aivg_sat PRIVATE libpeer nlohmann_json::nlohmann_json)

if(AIVG_SAT_BUILD_TESTS)
  enable_testing()
  add_executable(aivg_sat_compile_check tests/compile_check.cpp)
  target_link_libraries(aivg_sat_compile_check PRIVATE aivg_sat)
  target_include_directories(aivg_sat_compile_check PRIVATE ${CMAKE_CURRENT_SOURCE_DIR}/src)
  add_test(NAME compile_check COMMAND aivg_sat_compile_check)

  add_executable(aivg_sat_test_logic tests/test_logic.cpp)
  target_link_libraries(aivg_sat_test_logic PRIVATE aivg_sat)
  target_include_directories(aivg_sat_test_logic PRIVATE ${CMAKE_CURRENT_SOURCE_DIR}/src)
  add_test(NAME test_logic COMMAND aivg_sat_test_logic)

  if(nlohmann_json_FOUND)
    add_executable(aivg_sat_test_proto tests/test_proto.cpp)
    target_link_libraries(aivg_sat_test_proto PRIVATE aivg_sat nlohmann_json::nlohmann_json)
    target_include_directories(aivg_sat_test_proto PRIVATE ${CMAKE_CURRENT_SOURCE_DIR}/src)
    add_test(NAME test_proto COMMAND aivg_sat_test_proto)
  endif()

  # Live control-plane smoke (needs a running gateway; not registered as a
  # ctest). Built only when the POSIX WS client + proto layer are available.
  if(AIVG_SAT_HAVE_POSIX_WS AND nlohmann_json_FOUND)
    add_executable(ws_register_smoke tests/ws_register_smoke.cpp)
    target_link_libraries(ws_register_smoke PRIVATE aivg_sat nlohmann_json::nlohmann_json)
    target_include_directories(ws_register_smoke PRIVATE ${CMAKE_CURRENT_SOURCE_DIR}/src)

    add_executable(control_plane_smoke tests/control_plane_smoke.cpp)
    target_link_libraries(control_plane_smoke PRIVATE aivg_sat nlohmann_json::nlohmann_json)
    target_include_directories(control_plane_smoke PRIVATE ${CMAKE_CURRENT_SOURCE_DIR}/src)
  endif()
endif()

if(AIVG_SAT_BUILD_EXAMPLES)
  # The RPi reference satellite (PipeWire + openWakeWord) needs the voice
  # plane + libpipewire-0.3. Built only when both are present.
  if(AIVG_SAT_ENABLE_VOICE)
    find_package(PkgConfig QUIET)
    if(PkgConfig_FOUND)
      pkg_check_modules(PIPEWIRE QUIET libpipewire-0.3)
    endif()
    if(PIPEWIRE_FOUND)
      add_subdirectory(examples/rpi_pipewire)
    else()
      message(STATUS "rpi_pipewire example skipped: libpipewire-0.3 not found")
    endif()
  endif()
endif()
