import Std

/-!
# A small propositional assurance contract for CausalFill-Bench

Theorems in this file concern the executable, typed checker defined here.
The external Python parser, resource limits, sorting, serialization, and
statement hashes are not assumed to be verified Lean implementations.
-/

namespace CausalFill

structure Literal where
  var : Nat
  positive : Bool
  deriving DecidableEq, BEq, ReflBEq, LawfulBEq, Repr

abbrev Clause := List Literal
abbrev CNF := List Clause
abbrev Valuation := Nat → Bool

def pos (index : Nat) : Literal := ⟨index, true⟩
def neg (index : Nat) : Literal := ⟨index, false⟩

def Literal.complement (literal : Literal) : Literal :=
  ⟨literal.var, !literal.positive⟩

def LiteralHolds (valuation : Valuation) (literal : Literal) : Prop :=
  valuation literal.var = literal.positive

instance (valuation : Valuation) (literal : Literal) : Decidable (LiteralHolds valuation literal) :=
  inferInstanceAs (Decidable (valuation literal.var = literal.positive))

def ClauseHolds (valuation : Valuation) (clause : Clause) : Prop :=
  ∃ literal, literal ∈ clause ∧ LiteralHolds valuation literal

def CNFHolds (valuation : Valuation) (clauses : CNF) : Prop :=
  ∀ clause, clause ∈ clauses → ClauseHolds valuation clause

def Satisfiable (clauses : CNF) : Prop :=
  ∃ valuation, CNFHolds valuation clauses

def Entails (clauses : CNF) (goal : Literal) : Prop :=
  ∀ valuation, CNFHolds valuation clauses → LiteralHolds valuation goal

def NonvacuousEntailment (clauses : CNF) (goal : Literal) : Prop :=
  Satisfiable clauses ∧ Entails clauses goal

theorem complement_holds_iff (valuation : Valuation) (literal : Literal) :
    LiteralHolds valuation literal.complement ↔ ¬ LiteralHolds valuation literal := by
  cases hval : valuation literal.var <;>
    cases hpol : literal.positive <;>
    simp [LiteralHolds, Literal.complement, hval, hpol]

theorem empty_clause_false (valuation : Valuation) :
    ¬ ClauseHolds valuation [] := by
  rintro ⟨literal, hmem, _⟩
  simp at hmem

/-- Clause semantics depend on membership, not order or multiplicity. -/
def SameClause (left right : Clause) : Prop :=
  ∀ literal, literal ∈ left ↔ literal ∈ right

theorem sameClause_holds {left right : Clause} (h : SameClause left right)
    (valuation : Valuation) : ClauseHolds valuation left ↔ ClauseHolds valuation right := by
  constructor
  · rintro ⟨literal, hmem, hholds⟩
    exact ⟨literal, (h literal).mp hmem, hholds⟩
  · rintro ⟨literal, hmem, hholds⟩
    exact ⟨literal, (h literal).mpr hmem, hholds⟩

/-- Keep one occurrence of every literal. Ordering has no logical significance. -/
def deduplicate : Clause → Clause
  | [] => []
  | literal :: rest =>
    if literal ∈ rest then deduplicate rest else literal :: deduplicate rest

@[simp] theorem mem_deduplicate (literal : Literal) (clause : Clause) :
    literal ∈ deduplicate clause ↔ literal ∈ clause := by
  induction clause with
  | nil => simp [deduplicate]
  | cons head rest ih =>
    by_cases h : head ∈ rest
    · simp only [deduplicate, ite_eq_left h, ih, List.mem_cons]
      constructor
      · exact Or.inr
      · intro hmem
        rcases hmem with heq | hmem
        · subst literal
          exact h
        · exact hmem
    · simp [deduplicate, h, ih]

theorem deduplicate_holds (valuation : Valuation) (clause : Clause) :
    ClauseHolds valuation (deduplicate clause) ↔ ClauseHolds valuation clause :=
  sameClause_holds (fun literal => mem_deduplicate literal clause) valuation

def without (clause : Clause) (removed : Literal) : Clause :=
  clause.filter (fun literal => decide (literal ≠ removed))

/-- Remove the selected sign separately from each parent, then form the union. -/
def mergeResolvent (left right : Clause) (leftPivot rightPivot : Literal) : Clause :=
  deduplicate (without left leftPivot ++ without right rightPivot)

@[simp] theorem mem_mergeResolvent (literal : Literal) (left right : Clause)
    (leftPivot rightPivot : Literal) :
    literal ∈ mergeResolvent left right leftPivot rightPivot ↔
      (literal ∈ left ∧ literal ≠ leftPivot) ∨
      (literal ∈ right ∧ literal ≠ rightPivot) := by
  simp [mergeResolvent, without]

theorem mergeResolvent_sound (valuation : Valuation) (left right : Clause)
    (leftPivot rightPivot : Literal)
    (opposite : LiteralHolds valuation leftPivot → LiteralHolds valuation rightPivot → False)
    (hleft : ClauseHolds valuation left) (hright : ClauseHolds valuation right) :
    ClauseHolds valuation (mergeResolvent left right leftPivot rightPivot) := by
  obtain ⟨literal, hmem, hholds⟩ := hleft
  by_cases heq : literal = leftPivot
  · subst literal
    obtain ⟨other, hother, hotherHolds⟩ := hright
    have hne : other ≠ rightPivot := by
      intro heq
      subst other
      exact opposite hholds hotherHolds
    exact ⟨other, (mem_mergeResolvent _ _ _ _ _).mpr (Or.inr ⟨hother, hne⟩), hotherHolds⟩
  · exact ⟨literal, (mem_mergeResolvent _ _ _ _ _).mpr (Or.inl ⟨hmem, heq⟩), hholds⟩

/-- The first successful orientation takes priority, as in the Python kernel. -/
def resolve (left right : Clause) (pivot : Nat) : Option Clause :=
  if pos pivot ∈ left ∧ neg pivot ∈ right then
    some (mergeResolvent left right (pos pivot) (neg pivot))
  else if neg pivot ∈ left ∧ pos pivot ∈ right then
    some (mergeResolvent left right (neg pivot) (pos pivot))
  else
    none

theorem resolve_sound {left right result : Clause} {pivot : Nat}
    (hresolve : resolve left right pivot = some result)
    (valuation : Valuation) (hleft : ClauseHolds valuation left)
    (hright : ClauseHolds valuation right) : ClauseHolds valuation result := by
  unfold resolve at hresolve
  split at hresolve
  · cases hresolve
    apply mergeResolvent_sound valuation left right (pos pivot) (neg pivot) _ hleft hright
    intro hp hn
    have h : true = false := hp.symm.trans hn
    cases h
  · split at hresolve
    · cases hresolve
      apply mergeResolvent_sound valuation left right (neg pivot) (pos pivot) _ hleft hright
      intro hn hp
      have h : false = true := hn.symm.trans hp
      cases h
    · cases hresolve

/-- An abstract finite derivation using precisely the executable resolution rule. -/
inductive Derivable (premises : CNF) : Clause → Prop where
  | premise {clause : Clause} : clause ∈ premises → Derivable premises clause
  | resolution {left right result : Clause} {pivot : Nat} :
      Derivable premises left → Derivable premises right →
      resolve left right pivot = some result → Derivable premises result

theorem derivable_sound {premises : CNF} {clause : Clause}
    (hderive : Derivable premises clause) (valuation : Valuation)
    (hpremises : CNFHolds valuation premises) : ClauseHolds valuation clause := by
  induction hderive with
  | premise hmem => exact hpremises _ hmem
  | resolution _ _ hresolve ihleft ihright =>
    exact resolve_sound hresolve valuation ihleft ihright

theorem derivable_empty_unsatisfiable {premises : CNF}
    (hderive : Derivable premises []) : ∀ valuation, ¬ CNFHolds valuation premises := by
  intro valuation hpremises
  exact empty_clause_false valuation (derivable_sound hderive valuation hpremises)

structure Step where
  left : Nat
  right : Nat
  pivot : Nat
  deriving DecidableEq, Repr

/-- Zero-based lookup. An out-of-range reference fails. -/
def lookup {α : Type} : List α → Nat → Option α
  | [], _ => none
  | value :: _, 0 => some value
  | _ :: rest, index + 1 => lookup rest index

theorem lookup_mem {α : Type} {values : List α} {index : Nat} {value : α}
    (h : lookup values index = some value) : value ∈ values := by
  induction values generalizing index with
  | nil => simp [lookup] at h
  | cons head rest ih =>
    cases index with
    | zero =>
      simp [lookup] at h
      subst value
      simp
    | succ index =>
      exact List.mem_cons_of_mem head (ih h)

def executeStep (pool : CNF) (step : Step) : Option Clause :=
  match lookup pool step.left, lookup pool step.right with
  | some left, some right => resolve left right step.pivot
  | _, _ => none

theorem executeStep_sound {pool : CNF} {step : Step} {result : Clause}
    (hstep : executeStep pool step = some result) (valuation : Valuation)
    (hpool : CNFHolds valuation pool) : ClauseHolds valuation result := by
  cases hleft : lookup pool step.left with
  | none => simp [executeStep, hleft] at hstep
  | some left =>
    cases hright : lookup pool step.right with
    | none => simp [executeStep, hleft, hright] at hstep
    | some right =>
      have hresolve : resolve left right step.pivot = some result := by
        simpa [executeStep, hleft, hright] using hstep
      exact resolve_sound hresolve valuation
        (hpool left (lookup_mem hleft)) (hpool right (lookup_mem hright))

/-- Every supplied step is checked, including every step after an empty clause. -/
def derive : CNF → List Step → Option CNF
  | pool, [] => some pool
  | pool, step :: rest =>
    match executeStep pool step with
    | none => none
    | some result => derive (pool ++ [result]) rest

theorem derive_sound (steps : List Step) :
    ∀ {pool result : CNF} {valuation : Valuation},
      derive pool steps = some result → CNFHolds valuation pool → CNFHolds valuation result := by
  induction steps with
  | nil =>
    intro pool result valuation hderive hpool
    simp [derive] at hderive
    subst result
    exact hpool
  | cons step rest ih =>
    intro pool result valuation hderive hpool
    cases hstep : executeStep pool step with
    | none => simp [derive, hstep] at hderive
    | some clause =>
      have hclause : ClauseHolds valuation clause := executeStep_sound hstep valuation hpool
      have hnext : CNFHolds valuation (pool ++ [clause]) := by
        intro other hmem
        rcases List.mem_append.mp hmem with hmem | hmem
        · exact hpool other hmem
        · have heq : other = clause := by simpa using hmem
          subst other
          exact hclause
      apply ih (pool := pool ++ [clause]) (valuation := valuation) _ hnext
      simpa [derive, hstep] using hderive

/--
With no steps, an existing empty premise suffices. With steps, only an empty
last derived clause suffices. A malformed suffix makes the whole check fail.
-/
def refutes (premises : CNF) (steps : List Step) : Bool :=
  match derive premises steps with
  | none => false
  | some pool =>
    match steps with
    | [] => decide (([] : Clause) ∈ premises)
    | _ :: _ => decide (lookup pool (pool.length - 1) = some [])

theorem refutes_unsatisfiable {premises : CNF} {steps : List Step}
    (hcheck : refutes premises steps = true) :
    ∀ valuation, ¬ CNFHolds valuation premises := by
  intro valuation hpremises
  cases hderive : derive premises steps with
  | none => simp [refutes, hderive] at hcheck
  | some pool =>
    have hpool : CNFHolds valuation pool := derive_sound steps hderive hpremises
    cases steps with
    | nil =>
      have hempty : ([] : Clause) ∈ premises := by
        simpa [refutes, hderive] using hcheck
      exact empty_clause_false valuation (hpremises [] hempty)
    | cons step rest =>
      have hlast : lookup pool (pool.length - 1) = some [] := by
        simpa [refutes, hderive] using hcheck
      exact empty_clause_false valuation (hpool [] (lookup_mem hlast))

theorem unsatisfiable_extension_entails {premises : CNF} {goal : Literal}
    (hunsat : ∀ valuation, ¬ CNFHolds valuation (premises ++ [[goal.complement]])) :
    Entails premises goal := by
  intro valuation hpremises
  by_cases hgoal : LiteralHolds valuation goal
  · exact hgoal
  · have hneg : LiteralHolds valuation goal.complement :=
      (complement_holds_iff valuation goal).mpr hgoal
    have hextended : CNFHolds valuation (premises ++ [[goal.complement]]) := by
      intro clause hmem
      rcases List.mem_append.mp hmem with hmem | hmem
      · exact hpremises clause hmem
      · have heq : clause = [goal.complement] := by simpa using hmem
        subst clause
        exact ⟨goal.complement, by simp, hneg⟩
    exact False.elim (hunsat valuation hextended)

theorem refutation_entails {premises : CNF} {goal : Literal} {steps : List Step}
    (hcheck : refutes (premises ++ [[goal.complement]]) steps = true) :
    Entails premises goal :=
  unsatisfiable_extension_entails (refutes_unsatisfiable hcheck)

theorem derivable_empty_entails {premises : CNF} {goal : Literal}
    (hderive : Derivable (premises ++ [[goal.complement]]) []) : Entails premises goal :=
  unsatisfiable_extension_entails (derivable_empty_unsatisfiable hderive)

theorem satisfiable_refutation_nonvacuous {premises : CNF} {goal : Literal} {steps : List Step}
    (hsat : Satisfiable premises)
    (hcheck : refutes (premises ++ [[goal.complement]]) steps = true) :
    NonvacuousEntailment premises goal :=
  ⟨hsat, refutation_entails hcheck⟩

def checkModel (valuation : Valuation) (premises : CNF) : Bool :=
  premises.all (fun clause => clause.any (fun literal => decide (LiteralHolds valuation literal)))

theorem checkModel_sound {valuation : Valuation} {premises : CNF}
    (hcheck : checkModel valuation premises = true) : CNFHolds valuation premises := by
  simpa [checkModel, CNFHolds, ClauseHolds] using hcheck

/-- A finite model uses Python's one-based variables; unspecified values are false. -/
def assignmentValuation (assignment : List Bool) : Valuation
  | 0 => false
  | index + 1 => (lookup assignment index).getD false

theorem checked_nonvacuous {premises : CNF} {goal : Literal} {steps : List Step}
    {assignment : List Bool}
    (hmodel : checkModel (assignmentValuation assignment) premises = true)
    (hproof : refutes (premises ++ [[goal.complement]]) steps = true) :
    NonvacuousEntailment premises goal :=
  satisfiable_refutation_nonvacuous
    ⟨assignmentValuation assignment, checkModel_sound hmodel⟩ hproof

theorem checked_derivation_nonvacuous {premises : CNF} {goal : Literal}
    {assignment : List Bool}
    (hmodel : checkModel (assignmentValuation assignment) premises = true)
    (hderive : Derivable (premises ++ [[goal.complement]]) []) :
    NonvacuousEntailment premises goal :=
  ⟨⟨assignmentValuation assignment, checkModel_sound hmodel⟩, derivable_empty_entails hderive⟩

end CausalFill
