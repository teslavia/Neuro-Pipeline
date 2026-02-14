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
  // mu_ must be held by caller
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
  int backoff = config_.initial_backoff_ms * (1 << std::min(attempt, 15));
  return std::min(backoff, 30000);
}

bool GRPCClient::Connect() {
  std::lock_guard<std::mutex> lock(mu_);

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

  // Verify with health check (HealthCheckLocked expects mu_ held)
  if (!HealthCheckLocked()) {
    std::cerr << "[GRPCClient] Health check failed" << std::endl;
    return false;
  }

  connected_ = true;
  reconnect_attempts_ = 0;
  std::cout << "[GRPCClient] Connected successfully" << std::endl;
  return true;
}

void GRPCClient::Disconnect() {
  std::lock_guard<std::mutex> lock(mu_);
  CloseStream();
  if (connected_.exchange(false)) {
    stub_.reset();
    channel_.reset();
    std::cout << "[GRPCClient] Disconnected" << std::endl;
  }
}

bool GRPCClient::HealthCheckLocked() {
  // mu_ must be held by caller
  if (!stub_) return false;

  neuro_pipeline::HealthCheckRequest request;
  request.set_client_id("edge_device");

  neuro_pipeline::HealthCheckResponse response;
  grpc::ClientContext context;
  context.set_deadline(std::chrono::system_clock::now() + std::chrono::seconds(2));

  grpc::Status status = stub_->HealthCheck(&context, request, &response);

  if (!status.ok()) {
    std::cerr << "[GRPCClient] Health check RPC failed: "
              << status.error_message() << std::endl;
    return false;
  }

  return response.status() == neuro_pipeline::HealthCheckResponse::SERVING;
}

bool GRPCClient::HealthCheck() {
  std::lock_guard<std::mutex> lock(mu_);
  return HealthCheckLocked();
}

// ---------------------------------------------------------------------------
// Persistent stream management
// ---------------------------------------------------------------------------

bool GRPCClient::OpenStream() {
  // mu_ must be held by caller
  if (stream_open_) return true;
  if (!stub_) return false;

  stream_context_ = std::make_unique<grpc::ClientContext>();
  stream_response_ = neuro_pipeline::StreamResponse();
  stream_ = stub_->StreamDetectionResults(stream_context_.get(), &stream_response_);

  if (!stream_) {
    std::cerr << "[GRPCClient] Failed to open stream" << std::endl;
    stream_context_.reset();
    return false;
  }

  stream_open_ = true;
  return true;
}

void GRPCClient::CloseStream() {
  // mu_ must be held by caller
  if (!stream_open_) return;

  if (stream_) {
    stream_->WritesDone();
    stream_->Finish();  // Collect response (best-effort)
    stream_.reset();
  }
  stream_context_.reset();
  stream_open_ = false;
}
bool GRPCClient::StreamDetection(const neuro_pipeline::DetectionResult& result) {
  std::unique_lock<std::mutex> lock(mu_);

  if (!connected_.load()) {
    // Attempt reconnection
    if (reconnect_attempts_ >= config_.max_reconnect_attempts) {
      std::cerr << "[GRPCClient] Max reconnect attempts reached" << std::endl;
      return false;
    }

    int backoff = GetBackoffMs(reconnect_attempts_);
    std::cout << "[GRPCClient] Reconnecting in " << backoff << "ms (attempt "
              << reconnect_attempts_ + 1 << ")" << std::endl;

    // Release lock during sleep to avoid blocking other threads
    lock.unlock();
    std::this_thread::sleep_for(std::chrono::milliseconds(backoff));
    lock.lock();

    reconnect_attempts_++;
    // Re-create channel (Connect logic inlined since we already hold mu_)
    if (!CreateChannel()) return false;
    auto deadline = std::chrono::system_clock::now() + std::chrono::seconds(5);
    if (!channel_->WaitForConnected(deadline)) return false;
    if (!HealthCheckLocked()) return false;
    connected_ = true;
    reconnect_attempts_ = 0;
  }

  // Lazily open persistent stream
  if (!stream_open_ && !OpenStream()) {
    connected_ = false;
    return false;
  }

  // Write into the persistent stream
  if (!stream_->Write(result)) {
    std::cerr << "[GRPCClient] Stream write failed, resetting stream" << std::endl;
    CloseStream();
    connected_ = false;
    return false;
  }

  return true;
}

bool GRPCClient::FlushStream() {
  std::lock_guard<std::mutex> lock(mu_);
  if (!stream_open_ || !stream_) return false;

  stream_->WritesDone();
  grpc::Status status = stream_->Finish();
  stream_.reset();
  stream_context_.reset();
  stream_open_ = false;

  if (!status.ok()) {
    std::cerr << "[GRPCClient] FlushStream RPC failed: "
              << status.error_message() << std::endl;
    connected_ = false;
    return false;
  }

  return stream_response_.success();
}

}  // namespace communication