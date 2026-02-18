#include "neuro/inference/multi_model_scheduler.hpp"

#include <chrono>
#include <future>

#include "neuro/core/logger.hpp"
#include "neuro/inference/multi_model_manager.hpp"
#include "neuro/inference/rknn_engine.hpp"
#include "neuro/inference/postprocessor_base.hpp"

namespace neuro::inference {

MultiModelScheduler::MultiModelScheduler(MultiModelManager& manager)
    : manager_(manager) {}

bool MultiModelScheduler::BindModelToCore(const std::string& model_id,
                                          int npu_core) {
  if (npu_core < 0 || npu_core > 2) {
    LOG_ERROR("MultiModelScheduler", "Invalid NPU core %d (must be 0-2)",
              npu_core);
    return false;
  }

  auto* slot = manager_.GetModel(model_id);
  if (!slot) {
    LOG_ERROR("MultiModelScheduler", "Model '%s' not found in manager",
              model_id.c_str());
    return false;
  }

  std::lock_guard<std::mutex> lock(mutex_);

  // Check for duplicate binding
  for (const auto& b : bindings_) {
    if (b.model_id == model_id) {
      LOG_ERROR("MultiModelScheduler", "Model '%s' already bound",
                model_id.c_str());
      return false;
    }
  }

  bindings_.push_back({model_id, npu_core});
  LOG_INFO("MultiModelScheduler", "Bound model '%s' to NPU core %d",
           model_id.c_str(), npu_core);
  return true;
}

std::map<std::string, std::vector<neuro::core::DetectionBox>>
MultiModelScheduler::InferParallel(
    const std::shared_ptr<neuro::core::Buffer>& frame,
    uint32_t original_width, uint32_t original_height) {
  std::map<std::string, std::vector<neuro::core::DetectionBox>> results;

  std::vector<ModelBinding> local_bindings;
  {
    std::lock_guard<std::mutex> lock(mutex_);
    local_bindings = bindings_;
  }

  if (local_bindings.empty()) {
    return results;
  }

  // Launch parallel inference for each binding
  using FutureResult =
      std::future<std::pair<std::string, std::vector<neuro::core::DetectionBox>>>;
  std::vector<FutureResult> futures;

  for (const auto& binding : local_bindings) {
    futures.push_back(std::async(
        std::launch::async,
        [this, &frame, original_width, original_height,
         binding]() -> std::pair<std::string, std::vector<neuro::core::DetectionBox>> {
          auto* slot = manager_.GetModel(binding.model_id);
          if (!slot || !slot->engine) {
            LOG_ERROR("MultiModelScheduler",
                      "Model '%s' unavailable for inference",
                      binding.model_id.c_str());
            return {binding.model_id, {}};
          }

          slot->engine->SetCoreMask(1 << binding.npu_core);

          if (!slot->engine->Infer(frame)) {
            LOG_ERROR("MultiModelScheduler",
                      "Inference failed for model '%s'",
                      binding.model_id.c_str());
            return {binding.model_id, {}};
          }

          std::vector<neuro::core::DetectionBox> detections;
          if (slot->postprocessor) {
            detections = slot->postprocessor->Process(
                slot->engine->GetOutputs(), original_width, original_height);
          }
          return {binding.model_id, std::move(detections)};
        }));
  }

  // Collect results
  for (auto& f : futures) {
    auto [model_id, detections] = f.get();
    results[model_id] = std::move(detections);
  }

  return results;
}

const std::vector<MultiModelScheduler::ModelBinding>&
MultiModelScheduler::GetBindings() const {
  return bindings_;
}

}  // namespace ai_inference
