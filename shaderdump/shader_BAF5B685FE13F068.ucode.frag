/*    0.0 */       exec
/*    2   */          tfetch2D r0, r0.xy, tf0
/*    0.1 */       alloc colors
/*    1.0 */       exece
/*    3   */          mad_sat oC0, r0, c0.yyyy, c0.zzzz
/*    1.1 */       cnop
