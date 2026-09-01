/*    0.0 */       exec
/*    3   */          vfetch_full r0.xy01, r0.x, vf0, DataFormat=FMT_32_32_FLOAT, Stride=2, Signed=true, NumFormat=integer
/*    0.1 */       alloc position
/*    1.0 */       exec
/*    4   */          mul r1, r0.wwww, c3.xwzy
/*    5   */          mad r1, r0.zzzz, c2.xwzy, r1
/*    6   */          mad r1, r0.yyyy, c1.xzyw, r1.xzwy
/*    7   */          mad oPos, r0.xxxx, c0, r1.xzyw
/*    1.1 */       alloc interpolators
/*    2.0 */       exece
/*    8   */          dp2add o0.x___, r0.xyyy, c4.xyyy, c4.zzzz
/*    9   */          dp2add o0._y__, r0.xyyy, c5.xyyy, c5.zzzz
/*   10   */          max o1, c6, c6
/*   11   */          max o2, c7, c7
/*    2.1 */       cnop
