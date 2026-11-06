import CausalFill.BoundedFault
open CausalFill.BoundedFault

def fixtureTruth : Unit → Unit → Bool := fun _ _ => false
example : ([((), true), ((), true)] : List (Reading Unit)).Sublist
    (badReadings fixtureTruth () [((), true)]) := by decide
