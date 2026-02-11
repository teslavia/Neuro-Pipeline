#include "common/rknn_engine.hpp"

namespace ai_inference {

class RKNNEngine::Impl {
 public:
  explicit Impl(const Config& config) : config_(config) {}

  ~Impl() { Release(); }

  bool Initialize() {
    // TODO: Implement RKNN model loading
    // 1. Read .rknn model file into memory
    // 2. rknn_init(&ctx_, model_data, model_size, 0, nullptr)
    // 3. rknn_query(ctx_, RKNN_QUERY_IN_OUT_NUM, ...) -> get I/O tensor count
    // 4. rknn_query(ctx_, RKNN_QUERY_INPUT_ATTR, ...) -> get input dims
    // 5. rknn_query(ctx_, RKNN_QUERY_OUTPUT_ATTR, ...) -> get output dims
    // 6. If zero_copy: rknn_create_mem(ctx_, ...) for input/output
    // 7. Set core affinity: rknn_set_core_mask(ctx_, config_.core_mask)
    return false;
  }

  bool Infer(std::shared_ptr<common::Buffer> /*input*/) {
    // TODO: Implement NPU inference
    // 1. If zero_copy: copy/map input data to RKNN input mem
    //    (or pass DMA-BUF fd directly via rknn_create_mem_from_fd)
    // 2. rknn_inputs_set(ctx_, ...) [non-zero-copy path]
    // 3. rknn_run(ctx_, nullptr)
    // 4. rknn_outputs_get(ctx_, ...) [non-zero-copy path]
    // 5. Parse output tensors into outputs_
    return false;
  }

  void Release() {
    // TODO: rknn_destroy(ctx_)
  }

 private:
  Config config_;
  // TODO: rknn_context ctx_ = 0;
};

RKNNEngine::RKNNEngine(const Config& config)
    : impl_(std::make_unique<Impl>(config)), config_(config) {}

RKNNEngine::~RKNNEngine() = default;

bool RKNNEngine::Initialize() { return impl_->Initialize(); }

bool RKNNEngine::Infer(std::shared_ptr<common::Buffer> input) {
  return impl_->Infer(std::move(input));
}

void RKNNEngine::Release() { impl_->Release(); }

}  // namespace ai_inference
