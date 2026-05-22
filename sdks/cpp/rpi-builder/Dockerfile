# rpi-builder — arm64 Debian Bookworm build container for libaivg-sat (feature 020).
#
# Matches rpi2w02's OS (Debian Bookworm aarch64) exactly, so apt provides
# libpeer's deps and the produced binary's ABI lines up with the Pi 1:1.
# Built/run on the Mac via buildx + QEMU (linux/arm64); the resulting
# binary is scp'd to the Pi and run against the gateway.
#
# Reference pattern: geerlingguy/raspberry-pi-pcie-devices extras/cross-compile
# (docker-compose build env), adapted to a native-arm64 container so the
# C++ third-party deps resolve via apt instead of a cross sysroot.
FROM --platform=linux/arm64 debian:bookworm

ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update && apt-get install -y --no-install-recommends \
      build-essential \
      cmake \
      git \
      ca-certificates \
      pkg-config \
      libmbedtls-dev \
      libsrtp2-dev \
      libopus-dev \
      nlohmann-json3-dev \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /workspace/sdks/cpp
