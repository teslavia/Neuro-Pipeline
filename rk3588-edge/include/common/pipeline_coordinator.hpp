#ifndef APP_PIPELINE_COORDINATOR_HPP_
#define APP_PIPELINE_COORDINATOR_HPP_

#include <atomic>
#include <memory>

namespace app {

/**
 * @brief Orchestrates the edge data pipeline:
 *        Camera → Preprocessing → Inference → Communication.
 */
class PipelineCoordinator {
 public:
  PipelineCoordinator();
  ~PipelineCoordinator();

  bool Initialize();
  void Start();
  void Stop();
  bool IsRunning() const { return running_.load(); }

 private:
  std::atomic<bool> running_{false};
  // TODO: Hold references to V4L2Camera, RGAProcessor, RKNNEngine, GRPCClient
};

}  // namespace app

#endif  // APP_PIPELINE_COORDINATOR_HPP_
