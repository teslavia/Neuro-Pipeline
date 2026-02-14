#pragma once
#include "mpp_common.h"
static inline MPP_RET mpp_packet_init(MppPacket* p, void* data, size_t size) { (void)p;(void)data;(void)size; return 0; }
static inline MPP_RET mpp_packet_deinit(MppPacket* p) { (void)p; return 0; }
static inline void mpp_packet_set_pts(MppPacket p, int64_t pts) { (void)p;(void)pts; }
