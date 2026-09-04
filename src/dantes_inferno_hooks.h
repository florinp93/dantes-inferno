#pragma once

#include <rex/ppc.h>
#include <rex/runtime.h>
#include <rex/logging/macros.h>
#include <cstdint>
#include <csetjmp>

inline thread_local jmp_buf g_fiber_jmp_buf;
inline thread_local uint32_t g_setjmp_ctx_addr = 0;
inline thread_local uint32_t g_longjmp_return_value = 0;

inline int FiberSetjmp(uint32_t ctx_addr) {
  g_setjmp_ctx_addr = ctx_addr;
  int ret = setjmp(g_fiber_jmp_buf);
  if (ret != 0) {
    REXLOG_INFO("FIBER: setjmp returning from longjmp (ret={})", ret);
  }
  return ret;
}

inline void FiberLongjmp(uint32_t return_value) {
  g_longjmp_return_value = return_value;
  REXLOG_INFO("FIBER: longjmp called with return_value={}", return_value);
  longjmp(g_fiber_jmp_buf, 1);
}

inline void FiberRestoreContext(PPCContext& ctx, uint8_t* base) {
  if (g_setjmp_ctx_addr == 0) return;
  uint32_t addr = g_setjmp_ctx_addr;
  uint32_t phys_offset = (addr >= 0xE0000000u) ? 0x1000u : 0u;
  uint8_t* ptr = base + addr + phys_offset;
  ctx.r1.u64 = __builtin_bswap64(*reinterpret_cast<uint64_t*>(ptr + 144));
  ctx.r31.u64 = __builtin_bswap64(*reinterpret_cast<uint64_t*>(ptr + 296));
  ctx.r3.u32 = g_longjmp_return_value;
  REXLOG_INFO("FIBER: restored r1=0x{:08X} r31=0x{:08X} r3={}",
              ctx.r1.u32, ctx.r31.u32, ctx.r3.s32);
}

inline float g_ultrawide_target_aspect = 0.0f;
inline bool g_ultrawide_hook_logged = false;

inline void UltrawideAspectHook(rex::ppc::Register& f29) {
  if (g_ultrawide_target_aspect > 0.0f) {
    if (!g_ultrawide_hook_logged) {
      REXLOG_INFO("ULTRAWIDE: hook firing, setting aspect from {:.4f} to {:.4f}",
                  f29.f32, g_ultrawide_target_aspect);
      g_ultrawide_hook_logged = true;
    }
    f29.f32 = g_ultrawide_target_aspect;
  }
}
