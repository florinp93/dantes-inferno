/*    0.0 */       exec
/*    2   */          mul r2, r0.xyxy, c1
              +       maxs r0.__z_, c0.xx
/*    3   */          setTexLOD r0.z
/*    4   */          tfetch2D r4.x___, r2.xy, tf1, UseRegisterLOD=true
/*    5   */          tfetch2D r4._x__, r2.zw, tf2, UseRegisterLOD=true
/*    6   */          tfetch2D r4.__x_, r2.zw, tf3, UseRegisterLOD=true
/*    7   */          tfetch2D r2, r0.xy, tf0
/*    0.1 */       alloc colors
/*    1.0 */       exec
/*    8   */          mul r0, r4.zxyz, c254
              +       retain_prev r1._
/*    9   */          add r3.xyz_, r0.yzyy, c253.yzxx
              +       retain_prev r1._
/*   10   */          mad r3.__z_, r4.yyyy, c255.xxxx, r3.zzzz
              +       retain_prev r1._
/*   11   */          add r3.xy__, r3.xyyy, r0.xwww
              +       retain_prev r1._
/*   12   */          add r0.x___, r3.yyyy, r0.yyyy
              +       retain_prev r1._
/*   13   */          max r1._, r1, r1
              +       addsc r3.___w, c253.w, r0.x
/*    1.1 */       exece
/*   14   */          mul r0.xyz_, r3.xzww, r1.xzyy
              +       maxs r1._, r2.ww
/*   15   */          mul oC0.xyz_, r0.xzyy, r2.xyzz
              +       muls_prev oC0.___w, r1.w
