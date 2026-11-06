import CausalFill.Information

/-!
# Executable certificate checks for finite AND/OR arenas

Every node and alternative in the exported arena is enumerated. Kernel reduction
of `checkLower` establishes a bound for every finite strategy, while `checkUpper`
checks an attaining, strictly ranked strategy. No claim about a Python simulator
is hidden in these definitions: the concrete arena is the theorem statement.
-/

namespace CausalFill.Information

structure ArenaNode (size : Nat) where
  goal : Bool
  rank : Nat
  value : Option Nat
  choices : List (Choice (Fin size))
  deriving Repr, DecidableEq

structure FiniteArena (size : Nat) where
  nodes : Vector (ArenaNode size) size
  root : Fin size

namespace FiniteArena

variable {size : Nat}

def game (arena : FiniteArena size) : Game (Fin size) where
  goal state := (arena.nodes.get state).goal
  choices state := (arena.nodes.get state).choices

def values (arena : FiniteArena size) (state : Fin size) : Option Nat :=
  (arena.nodes.get state).value

def rank (arena : FiniteArena size) (state : Fin size) : Nat :=
  (arena.nodes.get state).rank

def checkLowerAt (arena : FiniteArena size) (state : Fin size) : Bool :=
  let node := arena.nodes.get state
  (if node.goal then node.value == some 0 else true) &&
  node.choices.all (fun choice =>
    boundLE node.value (addBound choice.cost (worstBound arena.values choice.children)))

def checkLower (arena : FiniteArena size) : Bool :=
  (List.finRange size).all arena.checkLowerAt

def checkUpperAt (arena : FiniteArena size) (state : Fin size) : Bool :=
  let node := arena.nodes.get state
  match node.value with
  | none => true
  | some required =>
    node.goal || node.choices.any (fun choice =>
      (addBound choice.cost (worstBound arena.values choice.children) == some required) &&
      choice.children.all (fun child => decide (arena.rank child < node.rank)))

def checkUpper (arena : FiniteArena size) : Bool :=
  (List.finRange size).all arena.checkUpperAt

/-- A separate representational check: goal nodes terminate and every available
action has at least one possible successor. `CanWin` itself is defined for all
arenas; an empty successor list would otherwise be a vacuous successful action. -/
def checkShape (arena : FiniteArena size) : Bool :=
  (List.finRange size).all fun state =>
    let node := arena.nodes.get state
    (if node.goal then node.choices.isEmpty else true) &&
    node.choices.all (fun choice => !choice.children.isEmpty)

theorem lower_of_check {arena : FiniteArena size}
    (checked : arena.checkLower = true) : ValidLower arena.game arena.values := by
  have each : ∀ state, arena.checkLowerAt state = true := by
    intro state
    exact (List.all_eq_true.mp checked) state (List.mem_finRange state)
  constructor
  · intro state goal
    have parts := Bool.and_eq_true_iff.mp (each state)
    have nodeGoal : (arena.nodes.get state).goal = true := goal
    simpa [values, nodeGoal] using parts.1
  · intro state choice member
    have parts := Bool.and_eq_true_iff.mp (each state)
    exact (List.all_eq_true.mp parts.2) choice member

theorem upper_of_check {arena : FiniteArena size}
    (checked : arena.checkUpper = true) : ValidUpper arena.game arena.values arena.rank := by
  intro state required finite
  have atState := (List.all_eq_true.mp checked) state (List.mem_finRange state)
  have finiteNode : (arena.nodes.get state).value = some required := finite
  simp only [checkUpperAt, finiteNode] at atState
  rcases Bool.or_eq_true_iff.mp atState with goal | choice
  · exact Or.inl goal
  · right
    obtain ⟨chosen, member, accepted⟩ := List.any_eq_true.mp choice
    have parts := Bool.and_eq_true_iff.mp accepted
    refine ⟨chosen, member, ?_, ?_⟩
    · simpa using parts.1
    · intro child inChildren
      have lower := (List.all_eq_true.mp parts.2) child inChildren
      exact of_decide_eq_true lower

theorem exact_budget_of_checks {arena : FiniteArena size}
    (lower : arena.checkLower = true) (upper : arena.checkUpper = true)
    {state : Fin size} {required : Nat} (finite : arena.values state = some required) :
    CanWin arena.game state required ∧
      (∀ budget, CanWin arena.game state budget → required ≤ budget) :=
  certified_exact_budget (lower_of_check lower) (upper_of_check upper) finite

theorem unwinnable_of_check {arena : FiniteArena size}
    (lower : arena.checkLower = true) {state : Fin size}
    (infinite : arena.values state = none) : ∀ budget, ¬ CanWin arena.game state budget :=
  infinite_value_unwinnable (lower_of_check lower) infinite

end FiniteArena
end CausalFill.Information
