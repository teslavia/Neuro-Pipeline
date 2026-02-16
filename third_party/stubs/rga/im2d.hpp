#pragma once
typedef int IM_STATUS;
#define IM_STATUS_SUCCESS 0
#define IM_YUV_TO_RGB_BT601_LIMIT 0
typedef struct { int width; int height; int wstride; int hstride; int format; void* vir_addr; int fd; } rga_buffer_t;
static inline IM_STATUS imcvtcolor(rga_buffer_t s, rga_buffer_t d, int sf, int df, int m) { (void)s;(void)d;(void)sf;(void)df;(void)m; return 0; }
static inline IM_STATUS imresize(rga_buffer_t s, rga_buffer_t d) { (void)s;(void)d; return 0; }
