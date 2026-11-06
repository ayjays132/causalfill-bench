import CausalFill.ArenaJSON

/-! Generated finite arena. The emitter is untrusted; every check below is
kernel reduction. Semantic JSON is emitted from the actual Lean data. -/
set_option maxRecDepth 200000
set_option maxHeartbeats 0

namespace CausalFill.Exported.ReleaseOpenLoopNoObserveMarket
open CausalFill.Information

def node0 : ArenaNode 10 where
  goal := false
  rank := 0
  value := none
  choices := []

def node1 : ArenaNode 10 where
  goal := false
  rank := 9
  value := none
  choices := []

def node2 : ArenaNode 10 where
  goal := false
  rank := 9
  value := none
  choices := []

def node3 : ArenaNode 10 where
  goal := false
  rank := 9
  value := none
  choices := []

def node4 : ArenaNode 10 where
  goal := false
  rank := 9
  value := none
  choices := []

def node5 : ArenaNode 10 where
  goal := false
  rank := 14
  value := none
  choices := [{ action := "settle", cost := 1, children := [⟨1, by decide⟩] }]

def node6 : ArenaNode 10 where
  goal := false
  rank := 14
  value := none
  choices := [{ action := "settle", cost := 1, children := [⟨2, by decide⟩] }]

def node7 : ArenaNode 10 where
  goal := false
  rank := 14
  value := none
  choices := [{ action := "settle", cost := 1, children := [⟨3, by decide⟩] }]

def node8 : ArenaNode 10 where
  goal := false
  rank := 14
  value := none
  choices := [{ action := "settle", cost := 1, children := [⟨4, by decide⟩] }]

def node9 : ArenaNode 10 where
  goal := false
  rank := 15
  value := none
  choices := [{ action := "order:0:standard", cost := 2, children := [⟨5, by decide⟩] }, { action := "order:0:express", cost := 2, children := [⟨6, by decide⟩] }, { action := "order:1:standard", cost := 2, children := [⟨7, by decide⟩] }, { action := "order:1:express", cost := 2, children := [⟨8, by decide⟩] }, { action := "settle", cost := 1, children := [⟨0, by decide⟩] }]

def arena : FiniteArena 10 where
  nodes := ⟨#[node0, node1, node2, node3, node4, node5, node6, node7, node8, node9], by decide⟩
  root := ⟨9, by decide⟩

theorem shapeChecked : arena.checkShape = true := by decide
theorem lowerChecked : arena.checkLower = true := by decide
theorem upperChecked : arena.checkUpper = true := by decide

theorem unwinnable : ∀ budget, ¬ CanWin arena.game arena.root budget :=
  FiniteArena.unwinnable_of_check lowerChecked (by decide)
theorem certifiedProfile : arena.checkShape = true ∧
    (∀ budget, ¬ CanWin arena.game arena.root budget) :=
  ⟨shapeChecked, unwinnable⟩
#print axioms certifiedProfile
#eval do
  unless arena.checkShape && arena.checkLower && arena.checkUpper do
    throw (IO.userError "finite arena runtime checker rejected certificate")
  IO.FS.writeFile "CausalFill/ReleaseOpenLoopNoObserveMarket.roundtrip.json" (arena.semanticJSON.compress ++ "\n")
  IO.println "ReleaseOpenLoopNoObserveMarket: finite arena kernel theorem and roundtrip accepted"
end CausalFill.Exported.ReleaseOpenLoopNoObserveMarket
