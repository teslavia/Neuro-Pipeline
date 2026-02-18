#ifndef NEURO_COMM_GRPC_CLIENT_HPP_
#define NEURO_COMM_GRPC_CLIENT_HPP_

#include <atomic>
#include <functional>
#include <memory>
#include <mutex>
#include <string>
#include <thread>
#include <grpcpp/grpcpp.h>
#include "neuro_pipeline.grpc.pb.h"

namespace neuro::comm {

class GRPCClient {
 public:
  struct Config {
    std::string server_address = "192.168.1.100:50051";
    int keepalive_interval_ms = 30000;
    int keepalive_timeout_ms = 10000;
    int max_reconnect_attempts = 10;
    int initial_backoff_ms = 1000;
    bool compression = true;  // Enable gzip compression
    // TLS (empty = insecure)
    std::string ca_cert_path;
    std::string client_cert_path;
    std::string client_key_path;
  };

  using CommandCallback = std::function<void(const neuro_pipeline::ControlCommand&)>;

  explicit GRPCClient(const Config& config);
  ~GRPCClient();

  GRPCClient(const GRPCClient&) = delete;
  GRPCClient& operator=(const GRPCClient&) = delete;

  bool Connect();
  void Disconnect();
  bool IsConnected() const { return connected_.load(); }

  // Client-streaming: persistent detection stream
  bool StreamDetection(const neuro_pipeline::DetectionResult& result);
  bool FlushStream();

  bool HealthCheck();

  // Bidirectional event stream
  bool StartEventStream(CommandCallback callback);
  bool SendEdgeEvent(const neuro_pipeline::EdgeEvent& event);
  void StopEventStream();

  int GetBackoffMs(int attempt);

 private:
  bool CreateChannel();
  bool HealthCheckLocked();
  bool OpenStream();
  void CloseStream();

  Config config_;
  std::atomic<bool> connected_{false};
  mutable std::mutex mu_;

  std::shared_ptr<grpc::Channel> channel_;
  std::unique_ptr<neuro_pipeline::NeuroPipelineService::Stub> stub_;
  int reconnect_attempts_ = 0;

  // Persistent detection stream state
  std::unique_ptr<grpc::ClientContext> stream_context_;
  std::unique_ptr<grpc::ClientWriter<neuro_pipeline::DetectionResult>> stream_;
  neuro_pipeline::StreamResponse stream_response_;
  bool stream_open_ = false;

  // Bidirectional event stream state
  std::unique_ptr<grpc::ClientContext> event_context_;
  std::unique_ptr<grpc::ClientReaderWriter<
      neuro_pipeline::EdgeEvent, neuro_pipeline::CentralEvent>> event_stream_;
  std::thread event_reader_thread_;
  std::atomic<bool> event_stream_active_{false};
  CommandCallback command_callback_;
};

}  // namespace neuro::comm

#endif  // NEURO_COMM_GRPC_CLIENT_HPP_
