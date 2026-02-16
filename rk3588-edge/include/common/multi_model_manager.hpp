#ifndef AI_INFERENCE_MULTI_MODEL_MANAGER_HPP_
#define AI_INFERENCE_MULTI_MODEL_MANAGER_HPP_

#include <memory>
#include <mutex>
#include <string>
#include <vector>

namespace ai_inference {

class RKNNEngine;
class PostProcessorBase;

struct ModelSlot {
  std::string model_id;
  std::string model_path;
  int npu_core;  // 0, 1, 2, or -1 for auto
  bool loaded = false;
  std::unique_ptr<RKNNEngine> engine;
  std::unique_ptr<PostProcessorBase> postprocessor;
};

class MultiModelManager {
 public:
  explicit MultiModelManager(size_t max_models = 3);

  bool LoadModel(const std::string& model_id, const std::string& model_path,
                 int npu_core = -1);
  bool UnloadModel(const std::string& model_id);
  ModelSlot* GetModel(const std::string& model_id);
  ModelSlot* GetActiveModel();
  bool SwitchActiveModel(const std::string& model_id);
  std::vector<std::string> ListModels() const;
  size_t ModelCount() const;

 private:
  mutable std::mutex mutex_;
  std::vector<ModelSlot> slots_;
  std::string active_model_id_;
  size_t max_models_;
};

}  // namespace ai_inference

#endif  // AI_INFERENCE_MULTI_MODEL_MANAGER_HPP_
