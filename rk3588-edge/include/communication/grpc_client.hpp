#ifndef COMMUNICATION_GRPC_CLIENT_HPP_
#define COMMUNICATION_GRPC_CLIENT_HPP_

#include <atomic>
#include <memory>
#include <mutex>
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

  // Non-copyable, non-movable (owns gRPC resources)
  GRPCClient(const GRPCClient&) = delete;
  GRPCClient& operator=(const GRPCClient&) = delete;

  bool Connect();
  void Disconnect();
  bool IsConnected() const { return connected_.load(); }

  // Persistent stream: write a single detection into the open stream.
  // Opens the stream on first call; re-opens on failure.
  bool StreamDetection(const neuro_pipeline::DetectionResult& result);

  // Flush and close the current stream, collecting the server response.
  bool FlushStream();

  bool HealthCheck();

  // Exposed for testing only
  int GetBackoffMs(int attempt);

 private:
  bool CreateChannel();
  bool HealthCheckLocked();  // mu_ must be held
  bool OpenStream();   // Open persistent client-streaming RPC
  void CloseStream();  // Tear down stream without waiting for response

  Config config_;
  std::atomic<bool> connected_{false};
  mutable std::mutex mu_;  // Protects channel_, stub_, stream state

  std::shared_ptr<grpc::Channel> channel_;
  std::unique_ptr<neuro_pipeline::NeuroPipelineService::Stub> stub_;
  int reconnect_attempts_ = 0;

  // Persistent stream state (protected by mu_)
  std::unique_ptr<grpc::ClientContext> stream_context_;
  std::unique_ptr<grpc::ClientWriter<neuro_pipeline::DetectionResult>> stream_;
  neuro_pipeline::StreamResponse stream_response_;
  bool stream_open_ = false;
};

}  // namespace communication

#endif  // COMMUNICATION_GRPC_CLIENT_HPP_
