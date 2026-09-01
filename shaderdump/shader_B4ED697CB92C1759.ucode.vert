/*    0.0 */       exec
/*    3   */          vfetch_full r1.xy01, r0.x, vf0, DataFormat=FMT_32_32_FLOAT, Stride=4, Signed=true, NumFormat=integer, PrefetchCount=4
/*    4   */          vfetch_mini r0.xy__, Offset=2, DataFormat=FMT_32_32_FLOAT, Signed=true, NumFormat=integer
/*    0.1 */       alloc position
/*    1.0 */       exec
/*    5   */          max oPos, r1, r1
/*    1.1 */       alloc interpolators
/*    2.0 */       exece
/*    6   */          max o0.xy__, r0.xyyy, r0.xyyy
/*    2.1 */       cnop
