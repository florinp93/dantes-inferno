// dantes_inferno_hooks.h - Mid-asm hook functions for the generated code.
//
// This header is included by the generated PCH via __has_include, so the
// generated recomp code can call these functions. They must be declared
// inline (or static inline) so they can be defined in a header.

#pragma once

#include <rex/ppc.h>
#include <rex/runtime.h>
#include <rex/logging/macros.h>
#include <cstdint>
#include <csetjmp>

// ============================================================================
// Fiber/longjmp support
//
// The game uses a setjmp/longjmp pair for the save system:
//   sub_82701240 = setjmp (saves guest context, returns 0)
//   sub_82700CE0 = longjmp (restores guest context, returns to setjmp with r3=val)
//
// In the recomp, the C++ call stack is used for function calls, so the guest
// longjmp can't work by just setting ctx.lr and doing `return` — the return
// goes to the C++ caller, not to the restored guest lr.
//
// Solution: use C setjmp/longjmp to unwind the C++ stack.
//   1. The save flow (sub_8267ACC8) calls C setjmp after sub_82701240 returns.
//   2. sub_82700CE0 (longjmp) calls C longjmp to unwind the C++ stack.
//   3. When C setjmp returns (via longjmp), FiberRestoreContext restores guest
//      registers from the saved context and sets r3 = the longjmp return value.
// ============================================================================

inline thread_local jmp_buf g_fiber_jmp_buf;
inline thread_local uint32_t g_setjmp_ctx_addr = 0;
inline thread_local uint32_t g_longjmp_return_value = 0;

// Called from sub_82701240 (guest setjmp) to save the C++ stack position.
// Saves the guest context buffer address for later restore.
// Returns 0 on first call, non-zero when returning from longjmp.
inline int FiberSetjmp(uint32_t ctx_addr) {
  g_setjmp_ctx_addr = ctx_addr;
  int ret = setjmp(g_fiber_jmp_buf);
  if (ret != 0) {
    REXLOG_INFO("FIBER: setjmp returning from longjmp (ret={})", ret);
  }
  return ret;
}

// Called by sub_82700CE0 (guest longjmp) to unwind the C++ stack.
// Saves the return value and calls C longjmp.
inline void FiberLongjmp(uint32_t return_value) {
  g_longjmp_return_value = return_value;
  REXLOG_INFO("FIBER: longjmp called with return_value={}", return_value);
  longjmp(g_fiber_jmp_buf, 1);
}

// Restore guest registers from the saved context after C longjmp returns.
// Called by the save flow after setjmp returns non-zero.
// Uses the same byte-swapping as REX_LOAD_U64/REX_LOAD_U32.
inline void FiberRestoreContext(PPCContext& ctx, uint8_t* base) {
  if (g_setjmp_ctx_addr == 0) return;
  uint32_t addr = g_setjmp_ctx_addr;
  uint32_t phys_offset = (addr >= 0xE0000000u) ? 0x1000u : 0u;
  uint8_t* ptr = base + addr + phys_offset;
  // Restore r1 from offset 144 (U64, big-endian)
  ctx.r1.u64 = __builtin_bswap64(*reinterpret_cast<uint64_t*>(ptr + 144));
  // Restore r31 from offset 296 (U64, big-endian)
  ctx.r31.u64 = __builtin_bswap64(*reinterpret_cast<uint64_t*>(ptr + 296));
  // Set r3 to the longjmp return value
  ctx.r3.u32 = g_longjmp_return_value;
  REXLOG_INFO("FIBER: restored r1=0x{:08X} r31=0x{:08X} r3={}",
              ctx.r1.u32, ctx.r31.u32, ctx.r3.s32);
}

// Force sub_82701240 (a setjmp-like context save) to take the normal
// context-save path instead of calling the fiber-switch callback.
inline void ZeroFiberSwitchCallback() {
  // No-op: the patch is now applied directly in sub_82701240's generated code.
}
