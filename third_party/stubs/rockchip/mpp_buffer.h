#pragma once
#include "mpp_common.h"
static inline void* mpp_buffer_get_ptr(MppBuffer b) { (void)b; return NULL; }
static inline size_t mpp_buffer_get_size(MppBuffer b) { (void)b; return 0; }
static inline int mpp_buffer_get_fd(MppBuffer b) { (void)b; return -1; }
