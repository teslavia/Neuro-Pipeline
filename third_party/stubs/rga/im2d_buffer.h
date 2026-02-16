#pragma once
#include "im2d.hpp"
#define RK_FORMAT_YCbCr_420_SP 0
#define RK_FORMAT_RGB_888 1
#define RK_FORMAT_BGR_888 2
static inline rga_buffer_t wrapbuffer_fd_t(int fd, int w, int h, int ws, int hs, int fmt) { rga_buffer_t b={0}; b.fd=fd; b.width=w; b.height=h; b.wstride=ws; b.hstride=hs; b.format=fmt; return b; }
static inline rga_buffer_t wrapbuffer_virtualaddr_t(void* va, int w, int h, int ws, int hs, int fmt) { rga_buffer_t b={0}; b.vir_addr=va; b.width=w; b.height=h; b.wstride=ws; b.hstride=hs; b.format=fmt; return b; }
