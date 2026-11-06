import CausalFill.BoundedFault
open CausalFill.BoundedFault

axiom CausalFill.BoundedFault.UnapprovedAssumption : False
theorem CausalFill.BoundedFault.UnapprovedClaim : False :=
  CausalFill.BoundedFault.UnapprovedAssumption
#print axioms CausalFill.BoundedFault.UnapprovedClaim
