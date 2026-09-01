/*    0.0 */       exec
/*    3   */          vfetch_full r1.xyz1, r0.x, vf95, DataFormat=FMT_32_32_32_FLOAT, Stride=7, Signed=true, NumFormat=integer, PrefetchCount=7
/*    4   */          vfetch_mini r0, Offset=3, DataFormat=FMT_32_32_32_32_FLOAT, Signed=true, NumFormat=integer
/*    0.1 */       alloc interpolators
/*    1.0 */       exec
/*    5   */          max o0, r0, r0
/*    1.1 */       alloc position
/*    2.0 */       exec
/*    6   */          max oPos, r1, r1
/*    2.1 */       exece
/*    7   */          nop
