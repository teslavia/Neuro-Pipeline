#include "communication/grpc_client.hpp"
#include "common/logger.hpp"
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
    LOG_ERROR("GRPCClient", "Failed to create channel");
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

  LOG_INFO("GRPCClient", "Connecting to %s", config_.server_address.c_str());

  if (!CreateChannel()) {
    return false;
  }

  // Wait for channel to be ready
  auto deadline = std::chrono::system_clock::now() + std::chrono::seconds(5);
  if (!channel_->WaitForConnected(deadline)) {
    LOG_ERROR("GRPCClient", "Connection timeout");
    return false;
  }

  // Verify with health check (HealthCheckLocked expects mu_ held)
  if (!HealthCheckLocked()) {
    LOG_ERROR("GRPCClient", "Health check failed");
    return false;
  }

  connected_ = true;
  reconnect_attempts_ = 0;
  LOG_INFO("GRPCClient", "Connected successfully");
  return true;
}

void GRPCClient::Disconnect() {
  std::lock_guard<std::mutex> lock(mu_);
  CloseStream();
  if (connected_.exchange(false)) {
    stub_.reset();
    channel_.reset();
    LOG_INFO("GRPCClient", "Disconnected");
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
    LOG_ERROR("GRPCClient", "Health check RPC failed: %s", status.error_message().c_str());
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
    LOG_ERROR("GRPCClient", "Failed to open stream");
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
    LOG_ERROR("GRPCClient", "Max reconnect attempts reached");
      return false;
    }

    int backoff = GetBackoffMs(reconnect_attempts_);
    LOG_INFO("GRPCClient", "Reconnecting in %dms (attempt %d)", backoff, reconnect_attempts_ + 1);

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
    LOG_ERROR("GRPCClient", "Stream write failed, resetting stream");
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
    LOG_ERROR("GRPCClient", "FlushStream RPC failed: %s", status.error_message().c_str());
    connected_ = false;
    return false;
  }

  return stream_response_.success();
}

// ---------------------------------------------------------------------------
// Bidirectional event stream
// ---------------------------------------------------------------------------

bool GRPCClient::StartEventStream(CommandCallback callback) {
  std::lock_guard<std::mutex> lock(mu_);
  if (!connected_.load() || !stub_) return false;
  if (event_stream_active_.load()) return true;

  command_callback_ = std::move(callback);
  event_context_ = std::make_unique<grpc::ClientContext>();
  event_stream_ = stub_->BidirectionalEventStream(event_context_.get());

  if (!event_stream_) {
    LOG_ERROR("GRPCClient", "Failed to open event stream");
    event_context_.reset();
    return false;
  }

  event_stream_active_ = true;

  // Reader thread: receives CentralEvents and dispatches commands
  event_reader_thread_ = std::thread([this]() {
    neuro_pipeline::CentralEvent event;
    while (event_stream_active_.load() && event_stream_->Read(&event)) {
      if (event.type() == neuro_pipeline::CentralEvent::CONTROL_COMMAND
          && command_callback_) {
        command_callback_(event.command());
      }
    }
    event_stream_active_ = false;
  });

  LOG_INFO("GRPCClient", "Event stream started");
  return true;
}

bool GRPCClient::SendEdgeEvent(const neuro_pipeline::EdgeEvent& event) {
  std::lock_guard<std::mutex> lock(mu_);
  if (!event_stream_active_.load() || !event_stream_) return false;
  return event_stream_->Write(event);
}

void GRPCClient::StopEventStream() {
  event_stream_active_ = false;

  {
    std::lock_guard<std::mutex> lock(mu_);
    if (event_stream_) {
      event_stream_->WritesDone();
    }
  }

  if (event_reader_thread_.joinable()) {
    event_reader_thread_.join();
  }

  std::lock_guard<std::mutex> lock(mu_);
  event_stream_.reset();
  event_context_.reset();
  LOG_INFO("GRPCClient", "Event stream stopped");
}

}  // namespace communication