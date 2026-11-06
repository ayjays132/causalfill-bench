import CausalFill.ReleaseNoObserveMarket
set_option maxRecDepth 200000
set_option maxHeartbeats 0

namespace CausalFill.Binding.ReleaseNoObserveMarket
open CausalFill.Information

def expectedArena : FiniteArena 63 :=
  ⟨⟨#[
    ⟨false, 0, none, []⟩,
    ⟨false, 0, none, []⟩,
    ⟨false, 0, none, []⟩,
    ⟨false, 0, none, []⟩,
    ⟨false, 0, none, []⟩,
    ⟨false, 0, none, []⟩,
    ⟨false, 0, none, []⟩,
    ⟨false, 0, none, []⟩,
    ⟨false, 0, none, []⟩,
    ⟨false, 0, none, []⟩,
    ⟨false, 0, none, []⟩,
    ⟨false, 0, none, []⟩,
    ⟨false, 0, none, []⟩,
    ⟨false, 0, none, []⟩,
    ⟨true, 0, some 0, []⟩,
    ⟨true, 0, some 0, []⟩,
    ⟨false, 0, none, []⟩,
    ⟨false, 0, none, []⟩,
    ⟨false, 0, none, []⟩,
    ⟨false, 0, none, []⟩,
    ⟨false, 0, none, []⟩,
    ⟨false, 0, none, []⟩,
    ⟨true, 0, some 0, []⟩,
    ⟨true, 0, some 0, []⟩,
    ⟨false, 0, none, []⟩,
    ⟨false, 0, none, []⟩,
    ⟨false, 0, none, []⟩,
    ⟨false, 0, none, []⟩,
    ⟨true, 0, some 0, []⟩,
    ⟨true, 0, some 0, []⟩,
    ⟨false, 0, none, []⟩,
    ⟨false, 0, none, []⟩,
    ⟨true, 0, some 0, []⟩,
    ⟨true, 0, some 0, []⟩,
    ⟨false, 0, none, []⟩,
    ⟨false, 0, none, []⟩,
    ⟨false, 0, none, []⟩,
    ⟨false, 0, none, []⟩,
    ⟨false, 8, none, [⟨"settle", 1, [⟨20, by decide⟩, ⟨14, by decide⟩]⟩]⟩,
    ⟨false, 8, none, [⟨"settle", 1, [⟨21, by decide⟩, ⟨15, by decide⟩]⟩]⟩,
    ⟨false, 8, none, [⟨"settle", 1, [⟨16, by decide⟩, ⟨22, by decide⟩]⟩]⟩,
    ⟨false, 8, none, [⟨"settle", 1, [⟨17, by decide⟩, ⟨23, by decide⟩]⟩]⟩,
    ⟨false, 8, none, [⟨"settle", 1, [⟨21, by decide⟩, ⟨15, by decide⟩]⟩]⟩,
    ⟨false, 8, none, [⟨"settle", 1, [⟨18, by decide⟩, ⟨24, by decide⟩]⟩]⟩,
    ⟨false, 8, none, [⟨"settle", 1, [⟨17, by decide⟩, ⟨23, by decide⟩]⟩]⟩,
    ⟨false, 8, none, [⟨"settle", 1, [⟨25, by decide⟩, ⟨19, by decide⟩]⟩]⟩,
    ⟨false, 8, none, [⟨"settle", 1, [⟨26, by decide⟩, ⟨32, by decide⟩]⟩]⟩,
    ⟨false, 8, none, [⟨"settle", 1, [⟨27, by decide⟩, ⟨33, by decide⟩]⟩]⟩,
    ⟨false, 8, none, [⟨"settle", 1, [⟨34, by decide⟩, ⟨28, by decide⟩]⟩]⟩,
    ⟨false, 8, none, [⟨"settle", 1, [⟨35, by decide⟩, ⟨29, by decide⟩]⟩]⟩,
    ⟨false, 8, none, [⟨"settle", 1, [⟨27, by decide⟩, ⟨33, by decide⟩]⟩]⟩,
    ⟨false, 8, none, [⟨"settle", 1, [⟨36, by decide⟩, ⟨30, by decide⟩]⟩]⟩,
    ⟨false, 8, none, [⟨"settle", 1, [⟨35, by decide⟩, ⟨29, by decide⟩]⟩]⟩,
    ⟨false, 8, none, [⟨"settle", 1, [⟨31, by decide⟩, ⟨37, by decide⟩]⟩]⟩,
    ⟨false, 9, none, [⟨"order:0:standard", 2, [⟨38, by decide⟩]⟩, ⟨"order:0:express", 2, [⟨39, by decide⟩]⟩, ⟨"order:1:standard", 2, [⟨40, by decide⟩]⟩, ⟨"order:1:express", 2, [⟨41, by decide⟩]⟩, ⟨"settle", 1, [⟨6, by decide⟩, ⟨8, by decide⟩]⟩]⟩,
    ⟨false, 9, none, [⟨"order:0:standard", 2, [⟨42, by decide⟩]⟩, ⟨"order:0:express", 2, [⟨43, by decide⟩]⟩, ⟨"order:1:standard", 2, [⟨44, by decide⟩]⟩, ⟨"order:1:express", 2, [⟨45, by decide⟩]⟩, ⟨"settle", 1, [⟨7, by decide⟩, ⟨9, by decide⟩]⟩]⟩,
    ⟨false, 9, none, [⟨"order:0:standard", 2, [⟨46, by decide⟩]⟩, ⟨"order:0:express", 2, [⟨47, by decide⟩]⟩, ⟨"order:1:standard", 2, [⟨48, by decide⟩]⟩, ⟨"order:1:express", 2, [⟨49, by decide⟩]⟩, ⟨"settle", 1, [⟨12, by decide⟩, ⟨10, by decide⟩]⟩]⟩,
    ⟨false, 9, none, [⟨"order:0:standard", 2, [⟨50, by decide⟩]⟩, ⟨"order:0:express", 2, [⟨51, by decide⟩]⟩, ⟨"order:1:standard", 2, [⟨52, by decide⟩]⟩, ⟨"order:1:express", 2, [⟨53, by decide⟩]⟩, ⟨"settle", 1, [⟨13, by decide⟩, ⟨11, by decide⟩]⟩]⟩,
    ⟨false, 14, none, [⟨"settle", 1, [⟨4, by decide⟩, ⟨54, by decide⟩]⟩]⟩,
    ⟨false, 14, none, [⟨"settle", 1, [⟨5, by decide⟩, ⟨55, by decide⟩]⟩]⟩,
    ⟨false, 14, none, [⟨"settle", 1, [⟨2, by decide⟩, ⟨56, by decide⟩]⟩]⟩,
    ⟨false, 14, none, [⟨"settle", 1, [⟨3, by decide⟩, ⟨57, by decide⟩]⟩]⟩,
    ⟨false, 15, none, [⟨"order:0:standard", 2, [⟨58, by decide⟩]⟩, ⟨"order:0:express", 2, [⟨59, by decide⟩]⟩, ⟨"order:1:standard", 2, [⟨60, by decide⟩]⟩, ⟨"order:1:express", 2, [⟨61, by decide⟩]⟩, ⟨"settle", 1, [⟨0, by decide⟩, ⟨1, by decide⟩]⟩]⟩
  ], by rfl⟩, ⟨62, by decide⟩⟩

theorem arenaCorrespondence : CausalFill.Exported.ReleaseNoObserveMarket.arena = expectedArena := by rfl

theorem boundProfile : CausalFill.Exported.ReleaseNoObserveMarket.arena = expectedArena ∧
    (expectedArena.checkShape = true ∧
      (∀ budget, ¬ CanWin expectedArena.game expectedArena.root budget)) := by
  constructor
  · exact arenaCorrespondence
  · rw [← arenaCorrespondence]
    exact CausalFill.Exported.ReleaseNoObserveMarket.certifiedProfile
#print axioms boundProfile
end CausalFill.Binding.ReleaseNoObserveMarket
