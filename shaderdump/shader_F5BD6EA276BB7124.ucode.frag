/*    0.0 */       exec
/*    2   */          max r1._, r1, r1
              +       maxs r0.__z_, c0.xx
/*    3   */          setTexLOD r0.z
/*    4   */          tfetch2D r0.1w__, r0.xy, tf0, UseRegisterLOD=true
/*    0.1 */       alloc colors
/*    1.0 */       exece
/*    5   */          mul oC0, r0.xxxy, r1
/*    1.1 */       cnop
