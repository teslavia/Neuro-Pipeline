#include <csignal>
#include <chrono>
#include <iostream>
#include <thread>

#include "common/pipeline_coordinator.hpp"

namespace {
volatile std::sig_atomic_t g_shutdown_requested = 0;

void SignalHandler(int signal) {
  std::cout << "\nReceived signal " << signal << ", shutting down..."
            << std::endl;
  g_shutdown_requested = 1;
}
}  // namespace

int main(int /*argc*/, char* /*argv*/[]) {
  std::cout << "============================================" << std::endl;
  std::cout << "  Neuro-Pipeline Edge v1.0.0" << std::endl;
  std::cout << "  RK3588 NPU Inference Engine" << std::endl;
  std::cout << "============================================" << std::endl;

  // Install signal handlers
  std::signal(SIGINT, SignalHandler);
  std::signal(SIGTERM, SignalHandler);

  try {
    // TODO: Parse command-line arguments (device, model, server, etc.)

    app::PipelineCoordinator coordinator;

    if (!coordinator.Initialize()) {
      std::cerr << "[FATAL] Failed to initialize pipeline" << std::endl;
      return 1;
    }

    coordinator.Start();

    // Main loop — wait for shutdown signal
    while (!g_shutdown_requested) {
      std::this_thread::sleep_for(std::chrono::milliseconds(100));
    }

    coordinator.Stop();

  } catch (const std::exception& e) {
    std::cerr << "[FATAL] " << e.what() << std::endl;
    return 1;
  }

  std::cout << "Shutdown complete." << std::endl;
  return 0;
}
