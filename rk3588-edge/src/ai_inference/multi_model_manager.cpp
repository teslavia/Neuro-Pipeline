#include "neuro/inference/multi_model_manager.hpp"

#include <algorithm>

#include "neuro/core/logger.hpp"
#include "neuro/inference/postprocessor_base.hpp"
#include "neuro/inference/rknn_engine.hpp"

namespace neuro::inference {

MultiModelManager::MultiModelManager(size_t max_models)
    : max_models_(max_models) {}

bool MultiModelManager::LoadModel(const std::string& model_id,
                                  const std::string& model_path,
                                  int npu_core) {
  std::lock_guard<std::mutex> lock(mutex_);

  if (slots_.size() >= max_models_) {
    LOG_ERROR("MultiModelManager", "Max models reached (%zu), cannot load '%s'",
              max_models_, model_id.c_str());
    return false;
  }

  for (const auto& slot : slots_) {
    if (slot.model_id == model_id) {
      LOG_ERROR("MultiModelManager", "Model '%s' already loaded",
                model_id.c_str());
      return false;
    }
  }

  RKNNEngine::Config cfg;
  cfg.model_path = model_path;
  cfg.core_mask = (npu_core >= 0) ? (1 << npu_core) : 0x07;

  auto engine = std::make_unique<RKNNEngine>(cfg);
  if (!engine->Initialize()) {
    LOG_ERROR("MultiModelManager", "Failed to initialize engine for '%s'",
              model_id.c_str());
    return false;
  }

  ModelSlot slot;
  slot.model_id = model_id;
  slot.model_path = model_path;
  slot.npu_core = npu_core;
  slot.loaded = true;
  slot.engine = std::move(engine);
  slots_.push_back(std::move(slot));

  if (active_model_id_.empty()) {
    active_model_id_ = model_id;
  }

  LOG_INFO("MultiModelManager", "Loaded model '%s' on core %d (%zu/%zu slots)",
           model_id.c_str(), npu_core, slots_.size(), max_models_);
  return true;
}

bool MultiModelManager::UnloadModel(const std::string& model_id) {
  std::lock_guard<std::mutex> lock(mutex_);

  auto it = std::find_if(slots_.begin(), slots_.end(),
      [&](const ModelSlot& s) { return s.model_id == model_id; });

  if (it == slots_.end()) {
    LOG_ERROR("MultiModelManager", "Model '%s' not found", model_id.c_str());
    return false;
  }

  slots_.erase(it);

  if (active_model_id_ == model_id) {
    active_model_id_ = slots_.empty() ? "" : slots_.front().model_id;
  }

  LOG_INFO("MultiModelManager", "Unloaded model '%s'", model_id.c_str());
  return true;
}

ModelSlot* MultiModelManager::GetModel(const std::string& model_id) {
  std::lock_guard<std::mutex> lock(mutex_);

  for (auto& slot : slots_) {
    if (slot.model_id == model_id) return &slot;
  }
  return nullptr;
}

ModelSlot* MultiModelManager::GetActiveModel() {
  std::lock_guard<std::mutex> lock(mutex_);

  for (auto& slot : slots_) {
    if (slot.model_id == active_model_id_) return &slot;
  }
  return nullptr;
}

bool MultiModelManager::SwitchActiveModel(const std::string& model_id) {
  std::lock_guard<std::mutex> lock(mutex_);

  for (const auto& slot : slots_) {
    if (slot.model_id == model_id && slot.loaded) {
      active_model_id_ = model_id;
      LOG_INFO("MultiModelManager", "Switched active model to '%s'",
               model_id.c_str());
      return true;
    }
  }

  LOG_ERROR("MultiModelManager", "Cannot switch to '%s': not found or not loaded",
            model_id.c_str());
  return false;
}

std::vector<std::string> MultiModelManager::ListModels() const {
  std::lock_guard<std::mutex> lock(mutex_);

  std::vector<std::string> ids;
  ids.reserve(slots_.size());
  for (const auto& slot : slots_) {
    ids.push_back(slot.model_id);
  }
  return ids;
}

size_t MultiModelManager::ModelCount() const {
  std::lock_guard<std::mutex> lock(mutex_);
  return slots_.size();
}

}  // namespace ai_inference
