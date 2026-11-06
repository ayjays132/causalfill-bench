import CausalFill.FiniteArena
import Lean.Data.Json.FromToJson

/-! JSON of actual semantic Lean definitions, for comparison to source JSON.
This is an executable correspondence check, not a proof of the exporter. -/

namespace CausalFill.Information.FiniteArena

open Lean

def choiceJSON {size : Nat} (choice : Choice (Fin size)) : Json :=
  Json.mkObj [
    ("action", toJson choice.action),
    ("cost", toJson choice.cost),
    ("children", toJson (choice.children.map (fun child => child.val)))
  ]

def nodeJSON {size : Nat} (node : ArenaNode size) : Json :=
  Json.mkObj [
    ("goal", toJson node.goal),
    ("rank", toJson node.rank),
    ("value", toJson node.value),
    ("choices", Json.arr (node.choices.map choiceJSON).toArray)
  ]

def semanticJSON {size : Nat} (arena : FiniteArena size) : Json :=
  Json.mkObj [
    ("size", toJson size),
    ("root", toJson arena.root.val),
    ("nodes", Json.arr (arena.nodes.toArray.map nodeJSON))
  ]

end CausalFill.Information.FiniteArena
