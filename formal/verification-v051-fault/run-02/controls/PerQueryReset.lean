import CausalFill.BoundedFault
open CausalFill.BoundedFault

def fixtureTruth : Unit → Unit → Bool := fun _ _ => false
example : Feasible fixtureTruth 1 [((), true), ((), true)] () := by unfold Feasible; decide
