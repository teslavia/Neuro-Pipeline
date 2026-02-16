#ifndef AI_INFERENCE_MULTI_MODEL_SCHEDULER_HPP_
#define AI_INFERENCE_MULTI_MODEL_SCHEDULER_HPP_

#include <map>
#include <memory>
#include <mutex>
#include <string>
#include <vector>

#include "common/buffer.hpp"
#include "common/types.hpp"

namespace ai_inference {

class MultiModelManager;

class MultiModelScheduler {
 public:
  struct ModelBinding {
    std::string model_id;
    int npu_core;  // 0, 1, or 2
  };

  explicit MultiModelScheduler(MultiModelManager& manager);

  /// Bind a model to a specific NPU core.
  bool BindModelToCore(const std::string& model_id, int npu_core);

  /// Run all bound models in parallel on the same frame.
  /// Returns map of model_id -> detections.
  std::map<std::string, std::vector<common::DetectionBox>> InferParallel(
      const std::shared_ptr<common::Buffer>& frame,
      uint32_t original_width, uint32_t original_height);

  /// Get current bindings.
  const std::vector<ModelBinding>& GetBindings() const;

 private:
  MultiModelManager& manager_;
  std::vector<ModelBinding> bindings_;
  mutable std::mutex mutex_;
};

}  // namespace ai_inference

#endif  // AI_INFERENCE_MULTI_MODEL_SCHEDULER_HPP_
