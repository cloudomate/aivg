# rpi_pipewire — reference RPi satellite: PipeWire (seeed audio) + openWakeWord-gated.
# Built as part of the SDK when -DAIVG_SAT_BUILD_EXAMPLES=ON AND the voice
# plane is enabled (-DAIVG_SAT_ENABLE_VOICE=ON ...). Needs libpipewire-0.3-dev.
find_package(PkgConfig REQUIRED)
pkg_check_modules(PIPEWIRE REQUIRED libpipewire-0.3)

add_executable(rpi_pipewire main.cpp)
target_include_directories(rpi_pipewire PRIVATE ${PIPEWIRE_INCLUDE_DIRS})
target_link_libraries(rpi_pipewire PRIVATE aivg::sat ${PIPEWIRE_LIBRARIES})
target_compile_options(rpi_pipewire PRIVATE ${PIPEWIRE_CFLAGS_OTHER})

# openWakeWord: the example ships a placeholder energy gate. To use real
# openWakeWord, add onnxruntime + the wakeword/melspectrogram/embedding ONNX
# models and implement WakeWordDetector::detect() (see main.cpp).
