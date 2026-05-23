# rpi_pipewire — reference RPi satellite: PipeWire (seeed audio) + openWakeWord-gated.
# Built as part of the SDK when -DAIVG_SAT_BUILD_EXAMPLES=ON AND the voice
# plane is enabled (-DAIVG_SAT_ENABLE_VOICE=ON ...). Needs libpipewire-0.3-dev.
find_package(PkgConfig REQUIRED)
pkg_check_modules(PIPEWIRE REQUIRED libpipewire-0.3)

add_executable(rpi_pipewire main.cpp)
target_include_directories(rpi_pipewire PRIVATE ${PIPEWIRE_INCLUDE_DIRS})
target_link_libraries(rpi_pipewire PRIVATE aivg::sat ${PIPEWIRE_LIBRARIES})
target_compile_options(rpi_pipewire PRIVATE ${PIPEWIRE_CFLAGS_OTHER})

# A static libpeer needs its transitive deps (mbedTLS ssl/x509, libsrtp2,
# usrsctp, cJSON) at the final link; group with libpeer.a to resolve the cycle.
if(AIVG_SAT_LIBPEER_ROOT)
  set(_ex_deps "")
  foreach(_l srtp2 mbedtls mbedx509 mbedcrypto usrsctp cjson)
    file(GLOB_RECURSE _h "${AIVG_SAT_LIBPEER_ROOT}/build/lib${_l}.a")
    if(_h)
      list(GET _h 0 _f)
      list(APPEND _ex_deps "${_f}")
    endif()
  endforeach()
  if(_ex_deps)
    target_link_libraries(rpi_pipewire PRIVATE -Wl,--start-group
      "${AIVG_SAT_LIBPEER_ROOT}/build/src/libpeer.a" ${_ex_deps} -Wl,--end-group)
  endif()
endif()

# openWakeWord: the example ships a placeholder energy gate. To use real
# openWakeWord, add onnxruntime + the wakeword/melspectrogram/embedding ONNX
# models and implement WakeWordDetector::detect() (see main.cpp).
