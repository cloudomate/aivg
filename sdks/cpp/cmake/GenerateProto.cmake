# Feature 022 — regenerate the C++ gRPC/protobuf stubs for the satellite
# audio plane from the canonical schema at repo-root proto/.
#
# Output lands in sdks/cpp/src/grpc/_generated/ and is CHECKED INTO GIT, so a
# consumer build needs no protoc/grpc_cpp_plugin (mirrors feature 021's
# checked-in Python stubs). Run only after editing the .proto.
#
# Standalone use (inside the rpi-builder container):
#   cmake -P sdks/cpp/cmake/GenerateProto.cmake
# or invoke the same protoc line the CI/dev image provides.

# Resolve repo root relative to this file (sdks/cpp/cmake/ -> ../../.. ).
get_filename_component(_AIVG_REPO_ROOT "${CMAKE_CURRENT_LIST_DIR}/../../.." ABSOLUTE)
set(_PROTO_DIR "${_AIVG_REPO_ROOT}/proto")
set(_OUT "${_AIVG_REPO_ROOT}/sdks/cpp/src/grpc/_generated")

find_program(PROTOC protoc REQUIRED)
find_program(GRPC_CPP_PLUGIN grpc_cpp_plugin REQUIRED)

file(MAKE_DIRECTORY "${_OUT}")

execute_process(
  COMMAND "${PROTOC}"
    -I "${_PROTO_DIR}"
    --cpp_out=${_OUT}
    --grpc_out=${_OUT}
    --plugin=protoc-gen-grpc=${GRPC_CPP_PLUGIN}
    aivg/satellite/v1/audio.proto
  RESULT_VARIABLE _rc)

if(NOT _rc EQUAL 0)
  message(FATAL_ERROR "protoc codegen failed (rc=${_rc})")
endif()
message(STATUS "Generated C++ stubs under ${_OUT}/aivg/satellite/v1/")
