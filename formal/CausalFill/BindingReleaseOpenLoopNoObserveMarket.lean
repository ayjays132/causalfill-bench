import CausalFill.ReleaseOpenLoopNoObserveMarket
set_option maxRecDepth 200000
set_option maxHeartbeats 0

namespace CausalFill.Binding.ReleaseOpenLoopNoObserveMarket
open CausalFill.Information

def expectedArena : FiniteArena 10 :=
  ⟨⟨#[
    ⟨false, 0, none, []⟩,
    ⟨false, 9, none, []⟩,
    ⟨false, 9, none, []⟩,
    ⟨false, 9, none, []⟩,
    ⟨false, 9, none, []⟩,
    ⟨false, 14, none, [⟨"settle", 1, [⟨1, by decide⟩]⟩]⟩,
    ⟨false, 14, none, [⟨"settle", 1, [⟨2, by decide⟩]⟩]⟩,
    ⟨false, 14, none, [⟨"settle", 1, [⟨3, by decide⟩]⟩]⟩,
    ⟨false, 14, none, [⟨"settle", 1, [⟨4, by decide⟩]⟩]⟩,
    ⟨false, 15, none, [⟨"order:0:standard", 2, [⟨5, by decide⟩]⟩, ⟨"order:0:express", 2, [⟨6, by decide⟩]⟩, ⟨"order:1:standard", 2, [⟨7, by decide⟩]⟩, ⟨"order:1:express", 2, [⟨8, by decide⟩]⟩, ⟨"settle", 1, [⟨0, by decide⟩]⟩]⟩
  ], by rfl⟩, ⟨9, by decide⟩⟩

theorem arenaCorrespondence : CausalFill.Exported.ReleaseOpenLoopNoObserveMarket.arena = expectedArena := by rfl

theorem boundProfile : CausalFill.Exported.ReleaseOpenLoopNoObserveMarket.arena = expectedArena ∧
    (expectedArena.checkShape = true ∧
      (∀ budget, ¬ CanWin expectedArena.game expectedArena.root budget)) := by
  constructor
  · exact arenaCorrespondence
  · rw [← arenaCorrespondence]
    exact CausalFill.Exported.ReleaseOpenLoopNoObserveMarket.certifiedProfile
#print axioms boundProfile
end CausalFill.Binding.ReleaseOpenLoopNoObserveMarket
