#pragma once
#include "mpp_common.h"
static inline MPP_RET mpp_frame_deinit(MppFrame* f) { (void)f; return 0; }
static inline MppBuffer mpp_frame_get_buffer(MppFrame f) { (void)f; return NULL; }
static inline RK_U32 mpp_frame_get_errinfo(MppFrame f) { (void)f; return 0; }
static inline RK_U32 mpp_frame_get_discard(MppFrame f) { (void)f; return 0; }
static inline RK_U32 mpp_frame_get_width(MppFrame f) { (void)f; return 0; }
static inline RK_U32 mpp_frame_get_height(MppFrame f) { (void)f; return 0; }
static inline RK_U32 mpp_frame_get_hor_stride(MppFrame f) { (void)f; return 0; }
static inline RK_U32 mpp_frame_get_ver_stride(MppFrame f) { (void)f; return 0; }
