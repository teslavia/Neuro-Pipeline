#ifndef COMMON_LOGGER_HPP_
#define COMMON_LOGGER_HPP_

#include <cstdio>
#include <cstdarg>
#include <string>

namespace common {

/// Lightweight structured logger.
/// Uses spdlog when available (via CMake), otherwise falls back to fprintf.
class Logger {
 public:
  enum class Level { kDebug, kInfo, kWarn, kError };

  static void Init(const std::string& level = "info") {
    if (level == "debug") min_level_ = Level::kDebug;
    else if (level == "warn") min_level_ = Level::kWarn;
    else if (level == "error") min_level_ = Level::kError;
    else min_level_ = Level::kInfo;
  }

  static void Log(Level level, const char* component, const char* fmt, ...) {
    if (level < min_level_) return;
    const char* tag = LevelTag(level);
    std::fprintf(stderr, "[%s] [%s] ", tag, component);
    va_list args;
    va_start(args, fmt);
    std::vfprintf(stderr, fmt, args);
    va_end(args);
    std::fprintf(stderr, "\n");
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
};

}  // namespace common

#define LOG_DEBUG(comp, ...) common::Logger::Log(common::Logger::Level::kDebug, comp, __VA_ARGS__)
#define LOG_INFO(comp, ...)  common::Logger::Log(common::Logger::Level::kInfo, comp, __VA_ARGS__)
#define LOG_WARN(comp, ...)  common::Logger::Log(common::Logger::Level::kWarn, comp, __VA_ARGS__)
#define LOG_ERROR(comp, ...) common::Logger::Log(common::Logger::Level::kError, comp, __VA_ARGS__)

#endif  // COMMON_LOGGER_HPP_
