#include "common/pipeline_coordinator.hpp"

#include <iostream>
#include <thread>

namespace app {

PipelineCoordinator::PipelineCoordinator() = default;
PipelineCoordinator::~PipelineCoordinator() { Stop(); }

bool PipelineCoordinator::Initialize() {
  // TODO: Initialize all subsystems
  // 1. Create and init V4L2Camera
  // 2. Create and init RGAProcessor
  // 3. Create and init RKNNEngine
  // 4. Create and init GRPCClient
  std::cout << "[PipelineCoordinator] Initialized (stub)" << std::endl;
  return true;
}

void PipelineCoordinator::Start() {
  running_ = true;
  std::cout << "[PipelineCoordinator] Pipeline started (stub)" << std::endl;

  // TODO: Main processing loop
  // while (running_) {
  //   auto frame = camera_->CaptureFrame();
  //   auto processed = rga_->Process(frame);
  //   engine_->Infer(processed);
  //   auto detections = postprocessor_->Process(engine_->GetOutputs(), ...);
  //   grpc_client_->StreamDetection(detections);
  //   camera_->ReleaseFrame(frame);
  // }
}

void PipelineCoordinator::Stop() {
  if (running_.exchange(false)) {
    std::cout << "[PipelineCoordinator] Pipeline stopped" << std::endl;
  }
}

}  // namespace app
