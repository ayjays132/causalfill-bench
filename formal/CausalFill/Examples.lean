import CausalFill.Resolution

namespace CausalFill.Examples

-- Empty-clause, direction, tautology, and complete-certificate edge cases.
example : refutes [[pos 1], [neg 1]] [⟨0, 1, 1⟩] = true := by decide
example : refutes [[neg 1], [pos 1]] [⟨0, 1, 1⟩] = true := by decide
example : refutes [[]] [] = true := by decide
example : refutes [] [] = false := by decide
example : refutes [[pos 1, neg 1]] [⟨0, 0, 1⟩] = false := by decide
example : refutes [[pos 1], [neg 1]] [⟨0, 1, 1⟩, ⟨3, 0, 1⟩] = false := by decide
example : refutes [[pos 1], [neg 1]] [⟨0, 2, 1⟩] = false := by decide
example : refutes [[pos 1], [neg 2]] [⟨0, 1, 1⟩] = false := by decide
example : refutes [[], [pos 1, pos 2], [neg 1]] [⟨1, 2, 1⟩] = false := by decide
example : resolve [pos 1, pos 1] [neg 1, pos 2] 1 = some [pos 2] := by decide

def examplePremises : CNF := [[pos 1], [neg 1, pos 2]]
def exampleGoal : Literal := pos 2
def exampleSteps : List Step := [⟨0, 1, 1⟩, ⟨3, 2, 2⟩]
def exampleAssignment : List Bool := [true, true]

theorem exampleModelAccepted :
    checkModel (assignmentValuation exampleAssignment) examplePremises = true := by decide

theorem exampleProofAccepted :
    refutes (examplePremises ++ [[exampleGoal.complement]]) exampleSteps = true := by decide

theorem exampleNonvacuous : NonvacuousEntailment examplePremises exampleGoal :=
  checked_nonvacuous exampleModelAccepted exampleProofAccepted

theorem negativeGoalNonvacuous : NonvacuousEntailment [[neg 1]] (neg 1) :=
  checked_nonvacuous (assignment := [false]) (steps := [⟨0, 1, 1⟩]) (by decide) (by decide)

end CausalFill.Examples
