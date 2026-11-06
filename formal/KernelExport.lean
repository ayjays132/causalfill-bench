import LeanExport.Basic
import CausalFill.Information
import CausalFill.FiniteArena
import CausalFill.ReleaseAdaptiveMarket
import CausalFill.ReleaseNoObserveMarket
import CausalFill.ReleaseOpenLoopMarket
import CausalFill.ReleaseOpenLoopNoObserveMarket
import CausalFill.BindingReleaseAdaptiveMarket
import CausalFill.BindingReleaseNoObserveMarket
import CausalFill.BindingReleaseOpenLoopMarket
import CausalFill.BindingReleaseOpenLoopNoObserveMarket

/- Export the fixed theorem inventory and its dependency closure as NDJSON.
   Independent checkers consume data without loading project .olean files. -/
open Lean Elab Command in
run_cmd do
  liftIO <| LeanExport.dumpEnv (← getEnv) (some [
    `CausalFill.Information.equal_observation_equal_choice,
    `CausalFill.Information.incompatible_same_observation,
    `CausalFill.Information.guaranteed_pair_requires_distinguishing_observations,
    `CausalFill.Information.successCount_zero,
    `CausalFill.Information.successCount_congr,
    `CausalFill.Information.successCount_le_one,
    `CausalFill.Information.observation_class_success_le_one,
    `CausalFill.Information.successCount_le_completionCapacity,
    `CausalFill.Information.observation_class_capacity_bound,
    `CausalFill.Information.canWin_mono,
    `CausalFill.Information.worstBound_meets,
    `CausalFill.Information.member_meets_worstBound,
    `CausalFill.Information.boundLE_finite,
    `CausalFill.Information.lower_certificate_sound,
    `CausalFill.Information.infinite_value_unwinnable,
    `CausalFill.Information.upper_certificate_sound,
    `CausalFill.Information.certified_exact_budget,
    `CausalFill.Information.FiniteArena.lower_of_check,
    `CausalFill.Information.FiniteArena.upper_of_check,
    `CausalFill.Information.FiniteArena.exact_budget_of_checks,
    `CausalFill.Information.FiniteArena.unwinnable_of_check,
    `CausalFill.Exported.ReleaseAdaptiveMarket.certifiedProfile,
    `CausalFill.Exported.ReleaseNoObserveMarket.certifiedProfile,
    `CausalFill.Exported.ReleaseOpenLoopMarket.certifiedProfile,
    `CausalFill.Exported.ReleaseOpenLoopNoObserveMarket.certifiedProfile,
    `CausalFill.Binding.ReleaseAdaptiveMarket.boundProfile,
    `CausalFill.Binding.ReleaseNoObserveMarket.boundProfile,
    `CausalFill.Binding.ReleaseOpenLoopMarket.boundProfile,
    `CausalFill.Binding.ReleaseOpenLoopNoObserveMarket.boundProfile
  ])
