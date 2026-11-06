import CausalFill.BoundedFault
open CausalFill.BoundedFault
example : capped 1 (capped 1 3 + 0) ≤ 1 := by decide
