#include "communication/grpc_client.hpp"
#include <iostream>
#include <thread>
#include <chrono>

namespace communication {

GRPCClient::GRPCClient(const Config& config) : config_(config) {}

GRPCClient::~GRPCClient() {
  Disconnect();
}

bool GRPCClient::CreateChannel() {
  grpc::ChannelArguments args;
  args.SetInt(GRPC_ARG_KEEPALIVE_TIME_MS, config_.keepalive_interval_ms);
  args.SetInt(GRPC_ARG_KEEPALIVE_TIMEOUT_MS, config_.keepalive_timeout_ms);
  args.SetInt(GRPC_ARG_KEEPALIVE_PERMIT_WITHOUT_CALLS, 1);
  args.SetInt(GRPC_ARG_HTTP2_MAX_PINGS_WITHOUT_DATA, 0);
  args.SetInt(GRPC_ARG_MAX_RECONNECT_BACKOFF_MS, 30000);

  channel_ = grpc::CreateCustomChannel(
      config_.server_address,
      grpc::InsecureChannelCredentials(),
      args);

  if (!channel_) {
    std::cerr << "[GRPCClient] Failed to create channel" << std::endl;
    return false;
  }

  stub_ = neuro_pipeline::NeuroPipelineService::NewStub(channel_);
  return true;
}

int GRPCClient::GetBackoffMs(int attempt) {
  int backoff = config_.initial_backoff_ms * (1 << attempt);
  return std::min(backoff, 30000);
}

bool GRPCClient::Connect() {
  if (connected_.load()) {
    return true;
  }

  std::cout << "[GRPCClient] Connecting to " << config_.server_address << std::endl;

  if (!CreateChannel()) {
    return false;
  }

  // Wait for channel to be ready
  auto deadline = std::chrono::system_clock::now() + std::chrono::seconds(5);
  if (!channel_->WaitForConnected(deadline)) {
    std::cerr << "[GRPCClient] Connection timeout" << std::endl;
    return false;
  }

  // Verify with health check
  if (!HealthCheck()) {
    std::cerr << "[GRPCClient] Health check failed" << std::endl;
    return false;
  }

  connected_ = true;
  reconnect_attempts_ = 0;
  std::cout << "[GRPCClient] Connected successfully" << std::endl;
  return true;
}

void GRPCClient::Disconnect() {
  if (connected_.exchange(false)) {
    stub_.reset();
    channel_.reset();
    std::cout << "[GRPCClient] Disconnected" << std::endl;
  }
}

bool GRPCClient::HealthCheck() {
  if (!stub_) return false;

  neuro_pipeline::HealthCheckRequest request;
  request.set_client_id("edge_device");

  neuro_pipeline::HealthCheckResponse response;
  grpc::ClientContext context;
  context.set_deadline(std::chrono::system_clock::now() + std::chrono::seconds(2));

  grpc::Status status = stub_->HealthCheck(&context, request, &response);

  if (!status.ok()) {
    std::cerr << "[GRPCClient] Health check RPC failed: " << status.error_message() << std::endl;
    return false;
  }

  return response.status() == neuro_pipeline::HealthCheckResponse::SERVING;
}

bool GRPCClient::StreamDetection(const neuro_pipeline::DetectionResult& result) {
  if (!connected_.load()) {
    // Attempt reconnection
    if (reconnect_attempts_ < config_.max_reconnect_attempts) {
      int backoff = GetBackoffMs(reconnect_attempts_);
      std::cout << "[GRPCClient] Reconnecting in " << backoff << "ms (attempt "
                << reconnect_attempts_ + 1 << ")" << std::endl;
      std::this_thread::sleep_for(std::chrono::milliseconds(backoff));
      reconnect_attempts_++;

      if (!Connect()) {
        return false;
      }
    } else {
      std::cerr << "[GRPCClient] Max reconnect attempts reached" << std::endl;
      return false;
    }
  }

  if (!stub_) return false;

  grpc::ClientContext context;
  context.set_deadline(std::chrono::system_clock::now() + std::chrono::seconds(5));

  auto stream = stub_->StreamDetectionResults(&context);
  if (!stream) {
    std::cerr << "[GRPCClient] Failed to create stream" << std::endl;
    connected_ = false;
    return false;
  }

  if (!stream->Write(result)) {
    std::cerr << "[GRPCClient] Stream write failed" << std::endl;
    connected_ = false;
    return false;
  }

  neuro_pipeline::StreamResponse response;
  stream->WritesDone();
  grpc::Status status = stream->Finish();

  if (!status.ok()) {
    std::cerr << "[GRPCClient] Stream RPC failed: " << status.error_message() << std::endl;
    connected_ = false;
    return false;
  }

  return response.success();
}

}  // namespace communication
