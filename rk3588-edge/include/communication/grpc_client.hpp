#ifndef COMMUNICATION_GRPC_CLIENT_HPP_
#define COMMUNICATION_GRPC_CLIENT_HPP_

#include <atomic>
#include <memory>
#include <string>
#include <grpcpp/grpcpp.h>
#include "neuro_pipeline.grpc.pb.h"

namespace communication {

class GRPCClient {
 public:
  struct Config {
    std::string server_address = "192.168.1.100:50051";
    int keepalive_interval_ms = 30000;
    int keepalive_timeout_ms = 10000;
    int max_reconnect_attempts = 10;
    int initial_backoff_ms = 1000;
  };

  explicit GRPCClient(const Config& config);
  ~GRPCClient();

  bool Connect();
  void Disconnect();
  bool IsConnected() const { return connected_.load(); }

  bool StreamDetection(const neuro_pipeline::DetectionResult& result);
  bool HealthCheck();

 private:
  bool CreateChannel();
  int GetBackoffMs(int attempt);

  Config config_;
  std::atomic<bool> connected_{false};
  std::shared_ptr<grpc::Channel> channel_;
  std::unique_ptr<neuro_pipeline::NeuroPipelineService::Stub> stub_;
  int reconnect_attempts_ = 0;
};

}  // namespace communication

#endif  // COMMUNICATION_GRPC_CLIENT_HPP_
