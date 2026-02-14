#ifndef COMMON_ERROR_CODES_HPP_
#define COMMON_ERROR_CODES_HPP_

#include <string>
#include <variant>

namespace common {

enum class ErrorCode {
  kOk = 0,
  kConfigError,
  kInitFailed,
  kDeviceNotFound,
  kModelLoadFailed,
  kInferenceFailed,
  kGrpcConnectionFailed,
  kGrpcStreamFailed,
  kBufferExhausted,
  kTimeout,
  kInvalidArgument,
  kUnknown,
};

inline const char* ErrorCodeToString(ErrorCode code) {
  switch (code) {
    case ErrorCode::kOk: return "OK";
    case ErrorCode::kConfigError: return "CONFIG_ERROR";
    case ErrorCode::kInitFailed: return "INIT_FAILED";
    case ErrorCode::kDeviceNotFound: return "DEVICE_NOT_FOUND";
    case ErrorCode::kModelLoadFailed: return "MODEL_LOAD_FAILED";
    case ErrorCode::kInferenceFailed: return "INFERENCE_FAILED";
    case ErrorCode::kGrpcConnectionFailed: return "GRPC_CONNECTION_FAILED";
    case ErrorCode::kGrpcStreamFailed: return "GRPC_STREAM_FAILED";
    case ErrorCode::kBufferExhausted: return "BUFFER_EXHAUSTED";
    case ErrorCode::kTimeout: return "TIMEOUT";
    case ErrorCode::kInvalidArgument: return "INVALID_ARGUMENT";
    case ErrorCode::kUnknown: return "UNKNOWN";
  }
  return "UNKNOWN";
}

/// Lightweight result type: holds either a value or an error code.
template <typename T>
class Result {
 public:
  static Result Ok(T value) { return Result(std::move(value)); }
  static Result Err(ErrorCode code) { return Result(code); }

  bool ok() const { return std::holds_alternative<T>(data_); }
  ErrorCode error() const { return std::get<ErrorCode>(data_); }
  const T& value() const { return std::get<T>(data_); }
  T& value() { return std::get<T>(data_); }

 private:
  explicit Result(T value) : data_(std::move(value)) {}
  explicit Result(ErrorCode code) : data_(code) {}
  std::variant<T, ErrorCode> data_;
};

}  // namespace common

#endif  // COMMON_ERROR_CODES_HPP_
