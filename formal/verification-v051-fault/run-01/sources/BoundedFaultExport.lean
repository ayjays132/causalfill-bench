import LeanExport.Basic
import CausalFill.BoundedFault

/- Export the bounded-fault roots and their complete dependency closure.
   This is separate from the unchanged v0.4 export and its root inventory. -/
open Lean Elab Command in
run_cmd do
  liftIO <| LeanExport.dumpEnv (← getEnv) (some [
    `CausalFill.BoundedFault.mismatches_append,
    `CausalFill.BoundedFault.mismatches_step,
    `CausalFill.BoundedFault.realizes_iff_mismatches,
    `CausalFill.BoundedFault.feasible_iff_realizes_within,
    `CausalFill.BoundedFault.capped_update_exact,
    `CausalFill.BoundedFault.capped_live_iff,
    `CausalFill.BoundedFault.capped_state_step,
    `CausalFill.BoundedFault.true_world_preserved,
    `CausalFill.BoundedFault.excluded_stays_excluded,
    `CausalFill.BoundedFault.badReadings_length,
    `CausalFill.BoundedFault.witness_count_le_mismatches,
    `CausalFill.BoundedFault.exclusion_witness_sound,
    `CausalFill.BoundedFault.witnesses_certify_action,
    `CausalFill.BoundedFault.safe_action_sound
  ])
