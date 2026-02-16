#pragma once
/*
 * Minimal RKNN API stub for CI cross-compilation (link-time only).
 * Provides type definitions and no-op inline function stubs so that
 * rknn_engine.cpp compiles when USE_MOCK_HAL=OFF without the real SDK.
 * The real rknn_api.h ships with the Rockchip RKNN SDK.
 */
#include <stdint.h>
#include <stddef.h>

/* ── Types ─────────────────────────────────────────────────────── */
typedef uint64_t rknn_context;

typedef enum {
    RKNN_QUERY_IN_OUT_NUM = 0,
    RKNN_QUERY_INPUT_ATTR,
    RKNN_QUERY_OUTPUT_ATTR,
} rknn_query_cmd;

typedef enum {
    RKNN_TENSOR_NHWC = 0,
    RKNN_TENSOR_NCHW,
} rknn_tensor_format;

typedef enum {
    RKNN_TENSOR_UINT8 = 0,
    RKNN_TENSOR_FLOAT16,
    RKNN_TENSOR_FLOAT32,
    RKNN_TENSOR_INT8,
} rknn_tensor_type;

typedef enum {
    RKNN_NPU_CORE_0 = 1,
    RKNN_NPU_CORE_1 = 2,
    RKNN_NPU_CORE_2 = 4,
    RKNN_NPU_CORE_0_1 = 3,
    RKNN_NPU_CORE_0_1_2 = 7,
    RKNN_NPU_CORE_AUTO = 0,
} rknn_core_mask;

typedef struct {
    uint32_t n_input;
    uint32_t n_output;
} rknn_input_output_num;

typedef struct {
    uint32_t index;
    uint32_t dims[16];
    uint32_t n_dims;
    uint32_t n_elems;
    uint32_t size;
    rknn_tensor_format fmt;
    rknn_tensor_type type;
} rknn_tensor_attr;

typedef struct {
    uint32_t index;
    void*    buf;
    uint32_t size;
    uint8_t  pass_through;
    rknn_tensor_type type;
    rknn_tensor_format fmt;
} rknn_input;

typedef struct {
    uint32_t index;
    uint8_t  want_float;
    uint8_t  is_prealloc;
    void*    buf;
    uint32_t size;
} rknn_output;

/* ── Function stubs (no-op, link-time only) ────────────────────── */
static inline int rknn_init(rknn_context* ctx, void* model, uint32_t size, uint32_t flag, void* extend) {
    (void)ctx;(void)model;(void)size;(void)flag;(void)extend; return 0;
}
static inline int rknn_query(rknn_context ctx, rknn_query_cmd cmd, void* info, uint32_t size) {
    (void)ctx;(void)cmd;(void)info;(void)size; return 0;
}
static inline int rknn_inputs_set(rknn_context ctx, uint32_t n, rknn_input* inputs) {
    (void)ctx;(void)n;(void)inputs; return 0;
}
static inline int rknn_run(rknn_context ctx, void* extend) {
    (void)ctx;(void)extend; return 0;
}
static inline int rknn_outputs_get(rknn_context ctx, uint32_t n, rknn_output* outputs, void* extend) {
    (void)ctx;(void)n;(void)outputs;(void)extend; return 0;
}
static inline int rknn_outputs_release(rknn_context ctx, uint32_t n, rknn_output* outputs) {
    (void)ctx;(void)n;(void)outputs; return 0;
}
static inline int rknn_set_core_mask(rknn_context ctx, rknn_core_mask mask) {
    (void)ctx;(void)mask; return 0;
}
static inline int rknn_destroy(rknn_context ctx) {
    (void)ctx; return 0;
}
