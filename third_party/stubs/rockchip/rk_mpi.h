#pragma once
#include "mpp_common.h"
#include "mpp_frame.h"
#include "mpp_packet.h"
#include "mpp_buffer.h"

typedef int MppCodingType;
#define MPP_CTX_DEC 0
#define MPP_VIDEO_CodingAVC 7
#define MPP_VIDEO_CodingHEVC 8
#define MPP_DEC_SET_PARSER_SPLIT_MODE 0x100

typedef struct MppApi_t {
    MPP_RET (*control)(MppCtx ctx, int cmd, void* param);
    MPP_RET (*decode_put_packet)(MppCtx ctx, MppPacket pkt);
    MPP_RET (*decode_get_frame)(MppCtx ctx, MppFrame* frame);
    MPP_RET (*reset)(MppCtx ctx);
} MppApi;

static inline MPP_RET mpp_create(MppCtx* ctx, MppApi** api) { (void)ctx;(void)api; return 0; }
static inline MPP_RET mpp_init(MppCtx ctx, int type, MppCodingType coding) { (void)ctx;(void)type;(void)coding; return 0; }
static inline MPP_RET mpp_destroy(MppCtx ctx) { (void)ctx; return 0; }
