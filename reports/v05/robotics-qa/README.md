# Robot observation QA

This export contains **288 exact public PNGs**, captured through Session in 144 fresh task instances and organized into 72 paired scenes. The 18 annotated contact sheets are separate composites.

Each sequence reads the contract, captures overview, moves to inspection, and captures again. It costs9 synthetic Session units,3 simulated time units, and1 energy unit; wear remains0. These are capture-only QA sequences, not completed delivery/controller trials.

Every PNG is independently decoded with Pillow and compared byte-for-byte with the benchmark decoder. The manifest checks noise support, measured gate visibility, calibrated lane classification, exact complete public-response pair equivalence, resource ledgers, trace integrity, and source stability. The stored PNG plus its public response/envelope metadata reconstructs each hashed capture response exactly.

Gate twins have identical overview responses and different inspection responses. Friction twins have identical responses in both views: their friction difference is deliberately not visible. Private labels exist only in this manifest and the contact-sheet margins.

Automated gate: **PASS**. Inspection maximum-coordinate error range: 0.06127028 to0.26107047 world units; declared allowance1.0.

Generated contact sheets are not automatically visually reviewed. A separate review record must identify the inspected sheets, hashes, method, findings, and reviewer. No human study or model result is implied.
