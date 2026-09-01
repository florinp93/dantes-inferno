/*    0.0 */       exec
/*    3   */          vfetch_full r3.xyz1, r0.x, vf0, DataFormat=FMT_32_32_32_FLOAT, Stride=6, Signed=true, NumFormat=integer, PrefetchCount=6
/*    4   */          vfetch_mini r1.wzyx, Offset=3, DataFormat=FMT_8_8_8_8
/*    5   */          vfetch_mini r0.xy__, Offset=4, DataFormat=FMT_32_32_FLOAT, Signed=true, NumFormat=integer
/*    0.1 */       alloc position
/*    1.0 */       exec
/*    6   */          mul r2, r3.wwww, c3.xwzy
/*    7   */          mad r2, r3.zzzz, c2.xwzy, r2
/*    8   */          mad r2, r3.yyyy, c1.xzyw, r2.xzwy
/*    9   */          mad oPos, r3.xxxx, c0, r2.xzyw
/*    1.1 */       alloc interpolators
/*    2.0 */       exece
/*   10   */          max o0.xy__, r0.xyyy, r0.xyyy
/*   11   */          max o1, r1, r1
/*    2.1 */       cnop
