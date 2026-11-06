# Visual stimulus QA

This evaluator-only export contains **336 observation PNGs**: 288 captures from 144 paired benchmark episodes and 48 sensor diagnostic fixtures. The 21 contact sheets are separate annotated composites.

Pillow independently decoded every image and matched the benchmark decoder byte-for-byte. The manifest separately records noise support, visibility, calibration error, pixel-reference behavior, pair equivalence, and partial/offscreen diagnostics. Passing generation does not mean a human inspected every sheet; any human review must be recorded separately.

Automated gate: **PASS**. See `manifest.json` for source hashes and exact counts.

Partial-object fixtures intentionally demonstrate centroid bias. They are outside the scored family's fully-visible inspection distribution and are not counted as task successes. All observation PNGs contain only RGB pixels; evaluator annotations appear only in contact sheets and the private manifest.
