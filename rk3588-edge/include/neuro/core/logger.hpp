#ifndef NEURO_CORE_LOGGER_HPP_
#define NEURO_CORE_LOGGER_HPP_

#include <cstdio>
#include <cstdarg>
#include <ctime>
#include <string>

namespace neuro::core {

/// Lightweight structured logger.
/// Supports text (default) and JSON output formats.
class Logger {
 public:
  enum class Level { kDebug, kInfo, kWarn, kError };
  enum class Format { kText, kJson };

  static void Init(const std::string& level = "info",
                   const std::string& format = "text") {
    if (level == "debug") min_level_ = Level::kDebug;
    else if (level == "warn") min_level_ = Level::kWarn;
    else if (level == "error") min_level_ = Level::kError;
    else min_level_ = Level::kInfo;

    if (format == "json") format_ = Format::kJson;
    else format_ = Format::kText;
  }

  static void SetDeviceId(const std::string& id) { device_id_ = id; }

  static void Log(Level level, const char* component, const char* fmt, ...) {
    if (level < min_level_) return;

    // Format the message
    char msg_buf[1024];
    va_list args;
    va_start(args, fmt);
    std::vsnprintf(msg_buf, sizeof(msg_buf), fmt, args);
    va_end(args);

    if (format_ == Format::kJson) {
      // JSON structured output — unified fields: ts, level, component, device_id, msg
      time_t now = std::time(nullptr);
      std::fprintf(stderr,
          "{\"ts\":%ld,\"level\":\"%s\",\"component\":\"%s\",\"device_id\":\"%s\",\"msg\":\"%s\"}\n",
          static_cast<long>(now), LevelTag(level), component,
          device_id_.c_str(), msg_buf);
    } else {
      // Text output (original format)
      std::fprintf(stderr, "[%s] [%s] %s\n", LevelTag(level), component, msg_buf);
    }
  }

 private:
  static const char* LevelTag(Level l) {
    switch (l) {
      case Level::kDebug: return "DEBUG";
      case Level::kInfo:  return "INFO";
      case Level::kWarn:  return "WARN";
      case Level::kError: return "ERROR";
    }
    return "INFO";
  }

  static inline Level min_level_ = Level::kInfo;
  static inline Format format_ = Format::kText;
  static inline std::string device_id_;
};

}  // namespace neuro::core

#define LOG_DEBUG(comp, ...) neuro::core::Logger::Log(neuro::core::Logger::Level::kDebug, comp, __VA_ARGS__)
#define LOG_INFO(comp, ...)  neuro::core::Logger::Log(neuro::core::Logger::Level::kInfo, comp, __VA_ARGS__)
#define LOG_WARN(comp, ...)  neuro::core::Logger::Log(neuro::core::Logger::Level::kWarn, comp, __VA_ARGS__)
#define LOG_ERROR(comp, ...) neuro::core::Logger::Log(neuro::core::Logger::Level::kError, comp, __VA_ARGS__)

#endif  // NEURO_CORE_LOGGER_HPP_
