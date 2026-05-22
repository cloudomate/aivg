// libaivg-sat — WebRTC signaling client (feature 020, T016).
#include "signaling.hpp"

#include <netdb.h>
#include <sys/socket.h>
#include <unistd.h>

#include <cstdio>
#include <cstring>
#include <random>
#include <string>

#include <nlohmann/json.hpp>

namespace aivg::sat::detail {
namespace {

using nlohmann::json;

struct HostPortPath {
  std::string host;
  std::string port = "80";
  std::string path = "/";
  bool ok = false;
};

HostPortPath parse_http(const std::string& base, const std::string& endpoint) {
  HostPortPath r;
  const std::string scheme = "http://";
  if (base.rfind(scheme, 0) != 0) return r;
  std::string rest = base.substr(scheme.size());
  auto slash = rest.find('/');
  std::string authority = slash == std::string::npos ? rest : rest.substr(0, slash);
  auto colon = authority.find(':');
  if (colon == std::string::npos) {
    r.host = authority;
  } else {
    r.host = authority.substr(0, colon);
    r.port = authority.substr(colon + 1);
  }
  r.path = endpoint;  // e.g. "/webrtc/offer"
  r.ok = !r.host.empty();
  return r;
}

std::string fabricate_session_id() {
  static std::mt19937_64 rng(std::random_device{}());
  char buf[17];
  std::snprintf(buf, sizeof(buf), "%016llx", static_cast<unsigned long long>(rng()));
  return std::string("local-") + buf;
}

int tcp_connect(const std::string& host, const std::string& port) {
  addrinfo hints{};
  hints.ai_family = AF_UNSPEC;
  hints.ai_socktype = SOCK_STREAM;
  addrinfo* res = nullptr;
  if (getaddrinfo(host.c_str(), port.c_str(), &hints, &res) != 0 || res == nullptr) return -1;
  int fd = -1;
  for (addrinfo* ai = res; ai != nullptr; ai = ai->ai_next) {
    fd = ::socket(ai->ai_family, ai->ai_socktype, ai->ai_protocol);
    if (fd < 0) continue;
    if (::connect(fd, ai->ai_addr, ai->ai_addrlen) == 0) break;
    ::close(fd);
    fd = -1;
  }
  freeaddrinfo(res);
  return fd;
}

bool write_all(int fd, const char* data, size_t len) {
  size_t sent = 0;
  while (sent < len) {
    ssize_t n = ::send(fd, data + sent, len - sent, 0);
    if (n <= 0) return false;
    sent += static_cast<size_t>(n);
  }
  return true;
}

std::string read_all(int fd) {
  std::string out;
  char buf[4096];
  ssize_t n;
  while ((n = ::recv(fd, buf, sizeof(buf), 0)) > 0) out.append(buf, static_cast<size_t>(n));
  return out;
}

}  // namespace

OfferResult post_offer(const std::string& signaling_base, const std::string& device_id,
                       const std::string& offer_sdp) {
  OfferResult r;
  HostPortPath hp = parse_http(signaling_base, "/webrtc/offer");
  if (!hp.ok) {
    r.error = "bad signaling url (http:// required)";
    return r;
  }
  std::string body = json{{"device_id", device_id}, {"sdp", offer_sdp}, {"type", "offer"}}.dump();
  std::string req = "POST " + hp.path + " HTTP/1.1\r\n" + "Host: " + hp.host + ":" + hp.port +
                    "\r\n" + "Content-Type: application/json\r\n" +
                    "Content-Length: " + std::to_string(body.size()) + "\r\n" +
                    "Connection: close\r\n\r\n" + body;

  int fd = tcp_connect(hp.host, hp.port);
  if (fd < 0) {
    r.error = "tcp connect failed";
    return r;
  }
  bool wrote = write_all(fd, req.data(), req.size());
  std::string resp = wrote ? read_all(fd) : std::string();
  ::close(fd);
  if (!wrote) {
    r.error = "request write failed";
    return r;
  }

  auto sep = resp.find("\r\n\r\n");
  if (sep == std::string::npos) {
    r.error = "no http body";
    return r;
  }
  std::string status_line = resp.substr(0, resp.find("\r\n"));
  if (status_line.find(" 200 ") == std::string::npos &&
      status_line.find(" 201 ") == std::string::npos) {
    r.error = "gateway: " + status_line;
    return r;
  }
  std::string body_text = resp.substr(sep + 4);
  json j = json::parse(body_text, nullptr, /*allow_exceptions=*/false);
  if (j.is_discarded() || !j.is_object() || !j.contains("sdp")) {
    r.error = "answer parse failed";
    return r;
  }
  r.sdp = j["sdp"].get<std::string>();
  r.session_id = j.contains("session_id") && j["session_id"].is_string()
                     ? j["session_id"].get<std::string>()
                     : fabricate_session_id();  // FR-011
  r.ok = true;
  return r;
}

}  // namespace aivg::sat::detail
