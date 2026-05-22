// libaivg-sat — POSIX control-plane WebSocket client (feature 020, T012).
//
// Minimal RFC 6455 client over plaintext TCP (ws://). Sufficient for the
// always-on control plane on the Linux tier (RPi Zero 2 W). TLS (wss://)
// is a later addition; localhost/LAN gateways use ws:// today.
//
// The Sec-WebSocket-Key/Accept handshake uses mbedTLS (already a libpeer
// dependency) for SHA-1 + base64, so no extra dependency is introduced.
#include <netdb.h>
#include <sys/socket.h>
#include <unistd.h>

#include <atomic>
#include <cstring>
#include <mutex>
#include <random>
#include <string>
#include <thread>
#include <vector>

#include <mbedtls/base64.h>
#include <mbedtls/sha1.h>

#include "platform/ws_client.hpp"

namespace aivg::sat::detail {
namespace {

constexpr const char* kWsGuid = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11";

struct ParsedUrl {
  std::string host;
  std::string port = "80";
  std::string path = "/";
  bool ok = false;
};

ParsedUrl parse_ws_url(const std::string& url) {
  ParsedUrl p;
  const std::string scheme = "ws://";
  if (url.rfind(scheme, 0) != 0) return p;  // wss:// not yet supported here
  std::string rest = url.substr(scheme.size());
  auto slash = rest.find('/');
  std::string authority = slash == std::string::npos ? rest : rest.substr(0, slash);
  p.path = slash == std::string::npos ? "/" : rest.substr(slash);
  auto colon = authority.find(':');
  if (colon == std::string::npos) {
    p.host = authority;
  } else {
    p.host = authority.substr(0, colon);
    p.port = authority.substr(colon + 1);
  }
  p.ok = !p.host.empty();
  return p;
}

std::string b64(const unsigned char* data, size_t len) {
  size_t olen = 0;
  std::vector<unsigned char> out(((len + 2) / 3) * 4 + 4);
  mbedtls_base64_encode(out.data(), out.size(), &olen, data, len);
  return std::string(reinterpret_cast<char*>(out.data()), olen);
}

std::string sec_accept(const std::string& key) {
  std::string concat = key + kWsGuid;
  unsigned char digest[20];
  mbedtls_sha1(reinterpret_cast<const unsigned char*>(concat.data()), concat.size(), digest);
  return b64(digest, sizeof(digest));
}

}  // namespace

class PosixWsClient final : public WsClient {
 public:
  ~PosixWsClient() override { close(); }

  void set_on_message(OnMessage cb) override { on_msg_ = std::move(cb); }
  void set_on_open(OnOpen cb) override { on_open_ = std::move(cb); }
  void set_on_close(OnClose cb) override { on_close_ = std::move(cb); }

  void connect(const std::string& url) override {
    ParsedUrl u = parse_ws_url(url);
    if (!u.ok) {
      fail(1002, "bad ws url");
      return;
    }
    addrinfo hints{};
    hints.ai_family = AF_UNSPEC;
    hints.ai_socktype = SOCK_STREAM;
    addrinfo* res = nullptr;
    if (getaddrinfo(u.host.c_str(), u.port.c_str(), &hints, &res) != 0 || res == nullptr) {
      fail(1006, "dns/getaddrinfo failed");
      return;
    }
    int fd = -1;
    for (addrinfo* ai = res; ai != nullptr; ai = ai->ai_next) {
      fd = ::socket(ai->ai_family, ai->ai_socktype, ai->ai_protocol);
      if (fd < 0) continue;
      if (::connect(fd, ai->ai_addr, ai->ai_addrlen) == 0) break;
      ::close(fd);
      fd = -1;
    }
    freeaddrinfo(res);
    if (fd < 0) {
      fail(1006, "tcp connect failed");
      return;
    }
    fd_ = fd;

    // --- Upgrade handshake ---
    unsigned char nonce[16];
    std::random_device rd;
    for (unsigned char& b : nonce) b = static_cast<unsigned char>(rd());
    std::string key = b64(nonce, sizeof(nonce));
    std::string req = "GET " + u.path + " HTTP/1.1\r\n" + "Host: " + u.host + ":" + u.port +
                      "\r\n" + "Upgrade: websocket\r\n" + "Connection: Upgrade\r\n" +
                      "Sec-WebSocket-Key: " + key + "\r\n" + "Sec-WebSocket-Version: 13\r\n\r\n";
    if (!write_all(req.data(), req.size())) {
      fail(1006, "handshake write failed");
      return;
    }
    std::string resp = read_http_response();
    if (resp.find(" 101 ") == std::string::npos ||
        resp.find(sec_accept(key)) == std::string::npos) {
      fail(1002, "handshake rejected: " + resp.substr(0, 80));
      return;
    }
    open_.store(true);
    if (on_open_) on_open_();
    reader_ = std::thread([this] { read_loop(); });
  }

  void send(const std::string& text) override {
    if (!open_.load()) return;
    std::vector<unsigned char> frame;
    frame.push_back(0x81);  // FIN + text
    unsigned char mask[4];
    std::random_device rd;
    for (unsigned char& m : mask) m = static_cast<unsigned char>(rd());
    const size_t n = text.size();
    if (n < 126) {
      frame.push_back(static_cast<unsigned char>(0x80 | n));
    } else if (n < 65536) {
      frame.push_back(0x80 | 126);
      frame.push_back(static_cast<unsigned char>((n >> 8) & 0xFF));
      frame.push_back(static_cast<unsigned char>(n & 0xFF));
    } else {
      frame.push_back(0x80 | 127);
      for (int i = 7; i >= 0; --i)
        frame.push_back(static_cast<unsigned char>((static_cast<uint64_t>(n) >> (i * 8)) & 0xFF));
    }
    frame.insert(frame.end(), mask, mask + 4);
    for (size_t i = 0; i < n; ++i)
      frame.push_back(static_cast<unsigned char>(text[i]) ^ mask[i % 4]);
    std::lock_guard<std::mutex> lk(write_mu_);
    write_all(reinterpret_cast<const char*>(frame.data()), frame.size());
  }

  void close() override {
    bool was = open_.exchange(false);
    if (fd_ >= 0) {
      ::shutdown(fd_, SHUT_RDWR);
    }
    if (reader_.joinable() && std::this_thread::get_id() != reader_.get_id()) reader_.join();
    if (fd_ >= 0) {
      ::close(fd_);
      fd_ = -1;
    }
    if (was && on_close_) on_close_(1000, "closed");
  }

 private:
  void fail(int code, const std::string& reason) {
    if (on_close_) on_close_(code, reason);
  }

  bool write_all(const char* data, size_t len) {
    size_t sent = 0;
    while (sent < len) {
      ssize_t n = ::send(fd_, data + sent, len - sent, 0);
      if (n <= 0) return false;
      sent += static_cast<size_t>(n);
    }
    return true;
  }

  std::string read_http_response() {
    std::string buf;
    char c = 0;
    while (buf.find("\r\n\r\n") == std::string::npos && buf.size() < 8192) {
      ssize_t n = ::recv(fd_, &c, 1, 0);
      if (n <= 0) break;
      buf.push_back(c);
    }
    return buf;
  }

  bool read_n(unsigned char* out, size_t n) {
    size_t got = 0;
    while (got < n) {
      ssize_t r = ::recv(fd_, out + got, n - got, 0);
      if (r <= 0) return false;
      got += static_cast<size_t>(r);
    }
    return true;
  }

  void read_loop() {
    while (open_.load()) {
      unsigned char hdr[2];
      if (!read_n(hdr, 2)) break;
      const bool fin = (hdr[0] & 0x80) != 0;
      const int opcode = hdr[0] & 0x0F;
      uint64_t len = hdr[1] & 0x7F;
      if (len == 126) {
        unsigned char ext[2];
        if (!read_n(ext, 2)) break;
        len = (static_cast<uint64_t>(ext[0]) << 8) | ext[1];
      } else if (len == 127) {
        unsigned char ext[8];
        if (!read_n(ext, 8)) break;
        len = 0;
        for (unsigned char b : ext) len = (len << 8) | b;
      }
      std::vector<unsigned char> payload(static_cast<size_t>(len));
      if (len > 0 && !read_n(payload.data(), payload.size())) break;
      // Server frames are not masked.
      if (opcode == 0x8) {  // close
        break;
      } else if (opcode == 0x9) {  // ping -> pong
        send_control(0x8A, payload);
      } else if (opcode == 0x1 || opcode == 0x0) {  // text / continuation
        frag_.append(reinterpret_cast<char*>(payload.data()), payload.size());
        if (fin) {
          if (on_msg_) on_msg_(frag_);
          frag_.clear();
        }
      }
    }
    if (open_.exchange(false) && on_close_) on_close_(1006, "read loop ended");
  }

  void send_control(unsigned char b0, const std::vector<unsigned char>& data) {
    std::vector<unsigned char> frame;
    frame.push_back(b0);
    unsigned char mask[4];
    std::random_device rd;
    for (unsigned char& m : mask) m = static_cast<unsigned char>(rd());
    frame.push_back(static_cast<unsigned char>(0x80 | data.size()));  // control <=125
    frame.insert(frame.end(), mask, mask + 4);
    for (size_t i = 0; i < data.size(); ++i) frame.push_back(data[i] ^ mask[i % 4]);
    std::lock_guard<std::mutex> lk(write_mu_);
    write_all(reinterpret_cast<const char*>(frame.data()), frame.size());
  }

  int fd_ = -1;
  std::atomic<bool> open_{false};
  std::thread reader_;
  std::mutex write_mu_;
  std::string frag_;
  OnMessage on_msg_;
  OnOpen on_open_;
  OnClose on_close_;
};

std::unique_ptr<WsClient> make_ws_client() { return std::make_unique<PosixWsClient>(); }

}  // namespace aivg::sat::detail
