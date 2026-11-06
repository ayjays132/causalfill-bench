import CausalFill.ReleaseOpenLoopMarket
set_option maxRecDepth 200000
set_option maxHeartbeats 0

namespace CausalFill.Binding.ReleaseOpenLoopMarket
open CausalFill.Information

def expectedArena : FiniteArena 40 :=
  ⟨⟨#[
    ⟨false, 0, none, []⟩,
    ⟨false, 0, none, []⟩,
    ⟨false, 8, none, []⟩,
    ⟨false, 8, none, []⟩,
    ⟨false, 8, none, []⟩,
    ⟨false, 8, none, []⟩,
    ⟨false, 9, none, []⟩,
    ⟨false, 9, none, []⟩,
    ⟨false, 9, none, []⟩,
    ⟨false, 9, none, []⟩,
    ⟨false, 12, none, [⟨"settle", 1, [⟨2, by decide⟩]⟩]⟩,
    ⟨false, 12, none, [⟨"settle", 1, [⟨3, by decide⟩]⟩]⟩,
    ⟨false, 12, none, [⟨"settle", 1, [⟨4, by decide⟩]⟩]⟩,
    ⟨false, 12, none, [⟨"settle", 1, [⟨5, by decide⟩]⟩]⟩,
    ⟨false, 12, none, [⟨"settle", 1, [⟨2, by decide⟩]⟩]⟩,
    ⟨false, 12, none, [⟨"settle", 1, [⟨3, by decide⟩]⟩]⟩,
    ⟨false, 12, none, [⟨"settle", 1, [⟨4, by decide⟩]⟩]⟩,
    ⟨false, 12, none, [⟨"settle", 1, [⟨5, by decide⟩]⟩]⟩,
    ⟨false, 13, none, [⟨"order:0:standard", 2, [⟨10, by decide⟩]⟩, ⟨"order:0:express", 2, [⟨11, by decide⟩]⟩, ⟨"order:1:standard", 2, [⟨12, by decide⟩]⟩, ⟨"order:1:express", 2, [⟨13, by decide⟩]⟩, ⟨"settle", 1, [⟨1, by decide⟩]⟩]⟩,
    ⟨false, 13, none, [⟨"order:0:standard", 2, [⟨14, by decide⟩]⟩, ⟨"order:0:express", 2, [⟨15, by decide⟩]⟩, ⟨"order:1:standard", 2, [⟨16, by decide⟩]⟩, ⟨"order:1:express", 2, [⟨17, by decide⟩]⟩, ⟨"settle", 1, [⟨1, by decide⟩]⟩]⟩,
    ⟨false, 13, none, [⟨"settle", 1, [⟨2, by decide⟩]⟩]⟩,
    ⟨false, 13, none, [⟨"settle", 1, [⟨3, by decide⟩]⟩]⟩,
    ⟨false, 13, none, [⟨"settle", 1, [⟨4, by decide⟩]⟩]⟩,
    ⟨false, 13, none, [⟨"settle", 1, [⟨5, by decide⟩]⟩]⟩,
    ⟨false, 13, none, [⟨"settle", 1, [⟨6, by decide⟩]⟩]⟩,
    ⟨false, 13, none, [⟨"settle", 1, [⟨7, by decide⟩]⟩]⟩,
    ⟨false, 13, none, [⟨"settle", 1, [⟨8, by decide⟩]⟩]⟩,
    ⟨false, 13, none, [⟨"settle", 1, [⟨9, by decide⟩]⟩]⟩,
    ⟨false, 13, none, [⟨"settle", 1, [⟨6, by decide⟩]⟩]⟩,
    ⟨false, 13, none, [⟨"settle", 1, [⟨7, by decide⟩]⟩]⟩,
    ⟨false, 13, none, [⟨"settle", 1, [⟨8, by decide⟩]⟩]⟩,
    ⟨false, 13, none, [⟨"settle", 1, [⟨9, by decide⟩]⟩]⟩,
    ⟨false, 14, none, [⟨"forecast", 1, [⟨18, by decide⟩]⟩, ⟨"assay", 2, [⟨19, by decide⟩]⟩, ⟨"order:0:standard", 2, [⟨20, by decide⟩]⟩, ⟨"order:0:express", 2, [⟨21, by decide⟩]⟩, ⟨"order:1:standard", 2, [⟨22, by decide⟩]⟩, ⟨"order:1:express", 2, [⟨23, by decide⟩]⟩, ⟨"settle", 1, [⟨1, by decide⟩]⟩]⟩,
    ⟨false, 14, none, [⟨"calibrate", 1, [⟨18, by decide⟩]⟩, ⟨"order:0:standard", 2, [⟨24, by decide⟩]⟩, ⟨"order:0:express", 2, [⟨25, by decide⟩]⟩, ⟨"order:1:standard", 2, [⟨26, by decide⟩]⟩, ⟨"order:1:express", 2, [⟨27, by decide⟩]⟩, ⟨"settle", 1, [⟨0, by decide⟩]⟩]⟩,
    ⟨false, 14, none, [⟨"calibrate", 1, [⟨19, by decide⟩]⟩, ⟨"order:0:standard", 2, [⟨28, by decide⟩]⟩, ⟨"order:0:express", 2, [⟨29, by decide⟩]⟩, ⟨"order:1:standard", 2, [⟨30, by decide⟩]⟩, ⟨"order:1:express", 2, [⟨31, by decide⟩]⟩, ⟨"settle", 1, [⟨0, by decide⟩]⟩]⟩,
    ⟨false, 14, none, [⟨"settle", 1, [⟨6, by decide⟩]⟩]⟩,
    ⟨false, 14, none, [⟨"settle", 1, [⟨7, by decide⟩]⟩]⟩,
    ⟨false, 14, none, [⟨"settle", 1, [⟨8, by decide⟩]⟩]⟩,
    ⟨false, 14, none, [⟨"settle", 1, [⟨9, by decide⟩]⟩]⟩,
    ⟨false, 15, none, [⟨"calibrate", 1, [⟨32, by decide⟩]⟩, ⟨"forecast", 1, [⟨33, by decide⟩]⟩, ⟨"assay", 2, [⟨34, by decide⟩]⟩, ⟨"order:0:standard", 2, [⟨35, by decide⟩]⟩, ⟨"order:0:express", 2, [⟨36, by decide⟩]⟩, ⟨"order:1:standard", 2, [⟨37, by decide⟩]⟩, ⟨"order:1:express", 2, [⟨38, by decide⟩]⟩, ⟨"settle", 1, [⟨0, by decide⟩]⟩]⟩
  ], by rfl⟩, ⟨39, by decide⟩⟩

theorem arenaCorrespondence : CausalFill.Exported.ReleaseOpenLoopMarket.arena = expectedArena := by rfl

theorem boundProfile : CausalFill.Exported.ReleaseOpenLoopMarket.arena = expectedArena ∧
    (expectedArena.checkShape = true ∧
      (∀ budget, ¬ CanWin expectedArena.game expectedArena.root budget)) := by
  constructor
  · exact arenaCorrespondence
  · rw [← arenaCorrespondence]
    exact CausalFill.Exported.ReleaseOpenLoopMarket.certifiedProfile
#print axioms boundProfile
end CausalFill.Binding.ReleaseOpenLoopMarket
