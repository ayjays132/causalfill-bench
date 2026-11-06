import CausalFill.BoundedFault
open CausalFill.BoundedFault

def fixtureTruth : Unit → Unit → Bool := fun _ _ => false
example : Feasible fixtureTruth 1 [((), true)] () := by unfold Feasible; decide
example : ¬ Feasible fixtureTruth 0 [((), true)] () := by unfold Feasible; decide
example : ¬ ([((), true), ((), true)] : List (Reading Unit)).Sublist
    (badReadings fixtureTruth () [((), true)]) := by decide
example : capped 1 3 = 2 := by decide
example : capped 1 (capped 1 3 + 0) = 2 := by decide
