# CP10-P0.7 final freeze-candidate

Status: `PROVISIONAL FINAL FREEZE CANDIDATE`  
Implementation: `UNAUTHORIZED` · Execution: `UNAUTHORIZED` · CP10 verdict: `UNEARNED` · CP11: `GATED`.

P0.7 carries the complete P0.6 classical CP10 contract unchanged. Its sole correction is condition seed instantiation: every calibration condition uses exactly seeds 1–8; seed 0 is prohibited. Held-out seeds are 1001–1016, replays are 1001, 1008, and 1016, and bootstrap column \(j\) selects held-out position \(1001+j\), never a literal seed number.

The explicit manifest has B=24, C=120, D=32, E=48 scientific conditions; 224 unique total, 9 replay attempts, and 233 execution records. It contains no bootstrap binary and no solver result.
