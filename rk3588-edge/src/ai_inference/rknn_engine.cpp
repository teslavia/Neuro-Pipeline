#include "neuro/inference/rknn_engine.hpp"

#include <cstring>
#include <fstream>
#include <iostream>
#include <vector>

#ifndef USE_MOCK_HAL

// ============================================================================
// Real RKNN implementation (Linux/RK3588 NPU)
// ============================================================================
#include <rknn_api.h>

namespace neuro::inference {

class RKNNEngine::Impl {
 public:
  explicit Impl(const Config& config) : config_(config), ctx_(0) {}

  ~Impl() { Release(); }

  bool Initialize() {
    // Read model file
    std::ifstream file(config_.model_path, std::ios::binary | std::ios::ate);
    if (!file.is_open()) {
      std::cerr << "[RKNN] Failed to open model: " << config_.model_path << std::endl;
      return false;
    }
    size_t model_size = file.tellg();
    file.seekg(0, std::ios::beg);
    std::vector<uint8_t> model_data(model_size);
    file.read(reinterpret_cast<char*>(model_data.data()), model_size);
    file.close();

    // Initialize RKNN context
    int ret = rknn_init(&ctx_, model_data.data(), model_size, 0, nullptr);
    if (ret < 0) {
      std::cerr << "[RKNN] rknn_init failed: " << ret << std::endl;
      return false;
    }

    // Query I/O tensor counts
    rknn_input_output_num io_num = {};
    ret = rknn_query(ctx_, RKNN_QUERY_IN_OUT_NUM, &io_num, sizeof(io_num));
    if (ret < 0) {
      std::cerr << "[RKNN] Query I/O num failed: " << ret << std::endl;
      return false;
    }
    n_input_ = io_num.n_input;
    n_output_ = io_num.n_output;

    // Query input attributes
    input_attrs_.resize(n_input_);
    for (uint32_t i = 0; i < n_input_; ++i) {
      input_attrs_[i].index = i;
      ret = rknn_query(ctx_, RKNN_QUERY_INPUT_ATTR, &input_attrs_[i],
                        sizeof(rknn_tensor_attr));
      if (ret < 0) {
        std::cerr << "[RKNN] Query input attr " << i << " failed" << std::endl;
        return false;
      }
    }

    // Query output attributes
    output_attrs_.resize(n_output_);
    for (uint32_t i = 0; i < n_output_; ++i) {
      output_attrs_[i].index = i;
      ret = rknn_query(ctx_, RKNN_QUERY_OUTPUT_ATTR, &output_attrs_[i],
                        sizeof(rknn_tensor_attr));
      if (ret < 0) {
        std::cerr << "[RKNN] Query output attr " << i << " failed" << std::endl;
        return false;
      }
    }

    // Extract input dimensions (assume NHWC format)
    if (input_attrs_[0].fmt == RKNN_TENSOR_NHWC) {
      input_height_ = input_attrs_[0].dims[1];
      input_width_ = input_attrs_[0].dims[2];
      input_channels_ = input_attrs_[0].dims[3];
    } else {  // NCHW
      input_channels_ = input_attrs_[0].dims[1];
      input_height_ = input_attrs_[0].dims[2];
      input_width_ = input_attrs_[0].dims[3];
    }

    // Set NPU core affinity
    if (config_.core_mask > 0) {
      rknn_core_mask mask = static_cast<rknn_core_mask>(config_.core_mask);
      rknn_set_core_mask(ctx_, mask);
    }

    std::cout << "[RKNN] Model loaded: " << config_.model_path
              << " input=" << input_width_ << "x" << input_height_
              << "x" << input_channels_
              << " outputs=" << n_output_ << std::endl;
    return true;
  }

  void SetCoreMask(int mask) {
    if (ctx_ && mask > 0) {
      rknn_core_mask m = static_cast<rknn_core_mask>(mask);
      rknn_set_core_mask(ctx_, m);
    }
  }

  bool Infer(std::shared_ptr<neuro::core::Buffer> input,
             std::vector<std::vector<float>>& outputs) {
    if (!ctx_ || !input) return false;

    // Set input
    rknn_input inputs[1] = {};
    inputs[0].index = 0;
    inputs[0].buf = input->Data();
    inputs[0].size = input->Size();
    inputs[0].pass_through = 0;
    inputs[0].type = RKNN_TENSOR_UINT8;
    inputs[0].fmt = RKNN_TENSOR_NHWC;

    int ret = rknn_inputs_set(ctx_, 1, inputs);
    if (ret < 0) {
      std::cerr << "[RKNN] rknn_inputs_set failed: " << ret << std::endl;
      return false;
    }

    // Run inference
    ret = rknn_run(ctx_, nullptr);
    if (ret < 0) {
      std::cerr << "[RKNN] rknn_run failed: " << ret << std::endl;
      return false;
    }

    // Get outputs (request float conversion)
    std::vector<rknn_output> rknn_outputs(n_output_);
    for (uint32_t i = 0; i < n_output_; ++i) {
      rknn_outputs[i].index = i;
      rknn_outputs[i].want_float = 1;
      rknn_outputs[i].is_prealloc = 0;
    }

    ret = rknn_outputs_get(ctx_, n_output_, rknn_outputs.data(), nullptr);
    if (ret < 0) {
      std::cerr << "[RKNN] rknn_outputs_get failed: " << ret << std::endl;
      return false;
    }

    // Copy output data
    outputs.resize(n_output_);
    for (uint32_t i = 0; i < n_output_; ++i) {
      size_t num_floats = rknn_outputs[i].size / sizeof(float);
      outputs[i].resize(num_floats);
      std::memcpy(outputs[i].data(), rknn_outputs[i].buf,
                   rknn_outputs[i].size);
    }

    rknn_outputs_release(ctx_, n_output_, rknn_outputs.data());
    return true;
  }

  void Release() {
    if (ctx_) {
      rknn_destroy(ctx_);
      ctx_ = 0;
    }
  }

  uint32_t NumOutputs() const { return n_output_; }

 private:
  Config config_;
  rknn_context ctx_;
  uint32_t n_input_ = 0;
  uint32_t n_output_ = 0;
  uint32_t input_width_ = 0;
  uint32_t input_height_ = 0;
  uint32_t input_channels_ = 0;
  std::vector<rknn_tensor_attr> input_attrs_;
  std::vector<rknn_tensor_attr> output_attrs_;
};

}  // namespace ai_inference

#else  // USE_MOCK_HAL

// ============================================================================
// Mock RKNN implementation (generates synthetic output tensors)
// ============================================================================
#include <cmath>
#include <random>

namespace neuro::inference {

class RKNNEngine::Impl {
 public:
  explicit Impl(const Config& config) : config_(config) {}
  ~Impl() = default;

  bool Initialize() {
    // Simulate YOLOv5s model: 3 output heads
    // P3/8:  1×255×80×80 = 1632000
    // P4/16: 1×255×40×40 = 408000
    // P5/32: 1×255×20×20 = 102000
    input_width_ = 640;
    input_height_ = 640;
    input_channels_ = 3;
    n_output_ = 3;  // Mock simulates YOLOv5s (3 output heads)

    std::cout << "[RKNN-Mock] Model loaded (simulated YOLOv5s)" << std::endl;
    return true;
  }

  bool Infer(std::shared_ptr<neuro::core::Buffer> input,
             std::vector<std::vector<float>>& outputs) {
    if (!input) return false;

    // Generate synthetic outputs matching RKNN YOLOv5 NCHW format
    // Each output: (3_anchors × 85_entries) × grid_h × grid_w
    const int grids[] = {80, 40, 20};
    const int prop_size = 85;  // 5 + 80 classes

    outputs.resize(3);
    std::mt19937 rng(42 + frame_count_);
    std::uniform_real_distribution<float> dist(0.0f, 0.1f);

    for (int s = 0; s < 3; ++s) {
      int grid_len = grids[s] * grids[s];
      int total = 3 * prop_size * grid_len;
      outputs[s].resize(total);

      // Fill with low values (post-sigmoid, so 0.0-0.1 = low confidence)
      for (int i = 0; i < total; ++i) {
        outputs[s][i] = dist(rng);
      }

      // Inject a "person" detection at grid center for testing
      if (s == 0 && frame_count_ % 5 == 0) {
        int cx = grids[s] / 2, cy = grids[s] / 2;
        int pos = cy * grids[s] + cx;
        int a = 0;  // anchor 0
        int base = a * prop_size * grid_len;
        // NCHW: output[base + channel * grid_len + pos]
        outputs[s][base + 0 * grid_len + pos] = 0.5f;  // bx (post-sigmoid)
        outputs[s][base + 1 * grid_len + pos] = 0.5f;  // by
        outputs[s][base + 2 * grid_len + pos] = 0.5f;  // bw
        outputs[s][base + 3 * grid_len + pos] = 0.5f;  // bh
        outputs[s][base + 4 * grid_len + pos] = 0.95f; // objectness
        outputs[s][base + 5 * grid_len + pos] = 0.9f;  // person class
      }
    }

    frame_count_++;
    return true;
  }

  void Release() {}

  void SetCoreMask(int /*mask*/) {
    // No-op in mock mode
  }

  uint32_t NumOutputs() const { return n_output_; }

 private:
  Config config_;
  uint32_t input_width_ = 0;
  uint32_t input_height_ = 0;
  uint32_t input_channels_ = 0;
  uint32_t n_output_ = 0;
  uint64_t frame_count_ = 0;
};

}  // namespace ai_inference

#endif  // USE_MOCK_HAL

namespace neuro::inference {

RKNNEngine::RKNNEngine(const Config& config)
    : impl_(std::make_unique<Impl>(config)), config_(config) {}

RKNNEngine::~RKNNEngine() = default;

bool RKNNEngine::Initialize() {
  if (!impl_->Initialize()) return false;
  n_outputs_ = impl_->NumOutputs();
  return true;
}

bool RKNNEngine::Infer(std::shared_ptr<neuro::core::Buffer> input) {
  return impl_->Infer(std::move(input), outputs_);
}

void RKNNEngine::Release() { impl_->Release(); }

void RKNNEngine::SetCoreMask(int mask) { impl_->SetCoreMask(mask); }

}  // namespace ai_inference
