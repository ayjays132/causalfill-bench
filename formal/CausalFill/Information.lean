import Std

/-!
# Finite information and strategy guarantees

This module formalizes two separate claims:
* identical observations cannot support incompatible successful completions;
* a complete Bellman lower certificate bounds every finite strategy in a
  declared AND/OR arena, and a ranked attaining certificate supplies a strategy.

The arena is the mathematical statement. Python parsing, projection from a
simulator to the arena, costs in physical units, and host isolation are not
asserted to be formally verified by these theorems.
-/

namespace CausalFill.Information

section Observations

variable {World Observation Action : Type}

def Incompatible (success : World → Action → Prop) (left right : World) : Prop :=
  ∀ action, ¬ (success left action ∧ success right action)

theorem equal_observation_equal_choice (observe : World → Observation)
    (policy : Observation → Action) {left right : World}
    (same : observe left = observe right) :
    policy (observe left) = policy (observe right) :=
  congrArg policy same

theorem incompatible_same_observation (observe : World → Observation)
    (policy : Observation → Action) (success : World → Action → Prop)
    {left right : World} (same : observe left = observe right)
    (different : Incompatible success left right) :
    ¬ (success left (policy (observe left)) ∧ success right (policy (observe right))) := by
  intro both
  apply different (policy (observe left))
  exact ⟨both.1, by simpa [same] using both.2⟩

theorem guaranteed_pair_requires_distinguishing_observations
    (observe : World → Observation) (policy : Observation → Action)
    (success : World → Action → Prop) {left right : World}
    (different : Incompatible success left right)
    (both : success left (policy (observe left)) ∧ success right (policy (observe right))) :
    observe left ≠ observe right := by
  intro same
  exact incompatible_same_observation observe policy success same different both

/-- Count successful worlds, retaining multiplicity in the supplied finite list. -/
def successCount (accept : World → Bool) : List World → Nat
  | [] => 0
  | world :: rest => (if accept world then 1 else 0) + successCount accept rest

theorem successCount_zero (accept : World → Bool) (worlds : List World)
    (none : ∀ world, world ∈ worlds → accept world = false) :
    successCount accept worlds = 0 := by
  induction worlds with
  | nil => rfl
  | cons head rest ih =>
    have hh := none head (by simp)
    have hr : ∀ world, world ∈ rest → accept world = false := by
      intro world member
      exact none world (by simp [member])
    simp [successCount, hh, ih hr]

theorem successCount_congr (left right : World → Bool) (worlds : List World)
    (same : ∀ world, world ∈ worlds → left world = right world) :
    successCount left worlds = successCount right worlds := by
  induction worlds with
  | nil => rfl
  | cons head rest ih =>
    have hh := same head (by simp)
    have hr : ∀ world, world ∈ rest → left world = right world := by
      intro world member
      exact same world (by simp [member])
    simp [successCount, hh, ih hr]

theorem successCount_le_one (accept : World → Bool) (worlds : List World)
    (exclusive : worlds.Pairwise (fun left right => ¬ (accept left = true ∧ accept right = true))) :
    successCount accept worlds ≤ 1 := by
  induction worlds with
  | nil => simp [successCount]
  | cons head rest ih =>
    have parts := List.pairwise_cons.mp exclusive
    cases hh : accept head with
    | false => simpa [successCount, hh] using ih parts.2
    | true =>
      have noRest : ∀ world, world ∈ rest → accept world = false := by
        intro world member
        cases hw : accept world with
        | false => rfl
        | true => exact False.elim (parts.1 world member ⟨hh, hw⟩)
      simp [successCount, hh, successCount_zero accept rest noRest]

/-- At most one mutually incompatible world in an observation-equivalence class
can be solved by a deterministic policy. A uniform expected-success statement
follows by dividing by the nonzero number of listed worlds; probability measures
and world-independent randomized policies are not modeled in this file. -/
theorem observation_class_success_le_one
    (observe : World → Observation) (policy : Observation → Action)
    (accept : World → Action → Bool) (worlds : List World) (observation : Observation)
    (same : ∀ world, world ∈ worlds → observe world = observation)
    (exclusive : worlds.Pairwise
      (fun left right => ∀ action, ¬ (accept left action = true ∧ accept right action = true))) :
    successCount (fun world => accept world (policy (observe world))) worlds ≤ 1 := by
  have equality := successCount_congr
    (fun world => accept world (policy (observe world)))
    (fun world => accept world (policy observation)) worlds (by
      intro world member
      rw [same world member])
  rw [equality]
  apply successCount_le_one
  exact exclusive.imp (fun incompatible => incompatible (policy observation))

/-- Maximum number of listed worlds solved by any listed common completion.
This permits overlapping successful-completion sets; disjointness is unnecessary. -/
def completionCapacity (accept : World → Action → Bool) (worlds : List World) :
    List Action → Nat
  | [] => 0
  | action :: rest => max (successCount (fun world => accept world action) worlds)
      (completionCapacity accept worlds rest)

theorem successCount_le_completionCapacity (accept : World → Action → Bool)
    (worlds : List World) (actions : List Action) {action : Action}
    (member : action ∈ actions) :
    successCount (fun world => accept world action) worlds ≤
      completionCapacity accept worlds actions := by
  induction actions with
  | nil => simp at member
  | cons first rest ih =>
    rcases List.mem_cons.mp member with equal | inRest
    · subst action
      exact Nat.le_max_left _ _
    · exact Nat.le_trans (ih inRest) (Nat.le_max_right _ _)

/-- Cardinality bound for any finite observation-equivalence class. The legal
completion list must include the policy's selected completion. For distinct
uniform worlds this count divided by the list length is an accuracy bound. -/
theorem observation_class_capacity_bound
    (observe : World → Observation) (policy : Observation → Action)
    (accept : World → Action → Bool) (worlds : List World) (actions : List Action)
    (observation : Observation)
    (same : ∀ world, world ∈ worlds → observe world = observation)
    (legal : policy observation ∈ actions) :
    successCount (fun world => accept world (policy (observe world))) worlds ≤
      completionCapacity accept worlds actions := by
  rw [successCount_congr
    (fun world => accept world (policy (observe world)))
    (fun world => accept world (policy observation)) worlds (by
      intro world member
      rw [same world member])]
  exact successCount_le_completionCapacity accept worlds actions legal

end Observations

section Strategies

variable {State : Type}

structure Choice (State : Type) where
  action : String
  cost : Nat
  children : List State
  deriving Repr, DecidableEq

structure Game (State : Type) where
  goal : State → Bool
  choices : State → List (Choice State)

/-- A finite successful strategy. Action choice is existential (OR), while all
possible observation children must be handled (AND). The same remaining budget
is available on each mutually exclusive branch; costs do not add across them. -/
inductive CanWin (game : Game State) : State → Nat → Prop where
  | done (state : State) (budget : Nat) (goal : game.goal state = true) :
      CanWin game state budget
  | step (state : State) (choice : Choice State) (remaining budget : Nat)
      (allowed : choice ∈ game.choices state)
      (cost : choice.cost + remaining ≤ budget)
      (branches : ∀ child, child ∈ choice.children → CanWin game child remaining) :
      CanWin game state budget

theorem canWin_mono {game : Game State} {state : State} {small large : Nat}
    (win : CanWin game state small) (more : small ≤ large) :
    CanWin game state large := by
  cases win with
  | done state budget goal => exact CanWin.done state large goal
  | step state choice remaining budget allowed cost branches =>
    exact CanWin.step state choice remaining large allowed (Nat.le_trans cost more) branches

/-- `none` is infinity/unwinnable, not a zero budget. -/
def MeetsBound (value : Option Nat) (budget : Nat) : Prop :=
  ∃ required, value = some required ∧ required ≤ budget

def boundLE : Option Nat → Option Nat → Bool
  | _, none => true
  | none, some _ => false
  | some left, some right => decide (left ≤ right)

def addBound (cost : Nat) : Option Nat → Option Nat
  | none => none
  | some value => some (cost + value)

def worstBound (values : State → Option Nat) : List State → Option Nat
  | [] => some 0
  | child :: rest =>
    match values child, worstBound values rest with
    | some first, some following => some (max first following)
    | _, _ => none

theorem worstBound_meets (values : State → Option Nat) (children : List State) (budget : Nat)
    (each : ∀ child, child ∈ children → MeetsBound (values child) budget) :
    MeetsBound (worstBound values children) budget := by
  induction children with
  | nil => exact ⟨0, rfl, Nat.zero_le budget⟩
  | cons first rest ih =>
    obtain ⟨a, ha, hle⟩ := each first (by simp)
    have er : ∀ child, child ∈ rest → MeetsBound (values child) budget := by
      intro child member
      exact each child (by simp [member])
    obtain ⟨b, hb, hble⟩ := ih er
    refine ⟨max a b, ?_, Nat.max_le.mpr ⟨hle, hble⟩⟩
    simp [worstBound, ha, hb]

theorem member_meets_worstBound (values : State → Option Nat) (children : List State)
    {maximum : Nat} (bound : worstBound values children = some maximum)
    {child : State} (member : child ∈ children) : MeetsBound (values child) maximum := by
  induction children generalizing maximum with
  | nil => simp at member
  | cons first rest ih =>
    cases ha : values first with
    | none => simp [worstBound, ha] at bound
    | some a =>
      cases hb : worstBound values rest with
      | none => simp [worstBound, ha, hb] at bound
      | some b =>
        have hm : max a b = maximum := by simpa [worstBound, ha, hb] using bound
        subst maximum
        rcases List.mem_cons.mp member with equal | inRest
        · subst child
          exact ⟨a, ha, Nat.le_max_left a b⟩
        · obtain ⟨required, hv, hle⟩ := ih hb inRest
          exact ⟨required, hv, Nat.le_trans hle (Nat.le_max_right a b)⟩

theorem boundLE_finite {value : Option Nat} {right budget : Nat}
    (ordered : boundLE value (some right) = true) (within : right ≤ budget) :
    MeetsBound value budget := by
  cases value with
  | none => simp [boundLE] at ordered
  | some left =>
    have hle : left ≤ right := by simpa [boundLE] using ordered
    exact ⟨left, rfl, Nat.le_trans hle within⟩

/-- Every available alternative is checked. Checking only a selected action
would establish no lower bound on strategies that select another action. -/
def ValidLower (game : Game State) (values : State → Option Nat) : Prop :=
  (∀ state, game.goal state = true → values state = some 0) ∧
  (∀ state choice, choice ∈ game.choices state →
    boundLE (values state) (addBound choice.cost (worstBound values choice.children)) = true)

theorem lower_certificate_sound {game : Game State} {values : State → Option Nat}
    (certificate : ValidLower game values) {state : State} {budget : Nat}
    (win : CanWin game state budget) : MeetsBound (values state) budget := by
  induction win with
  | done state budget goal =>
    exact ⟨0, certificate.1 state goal, Nat.zero_le budget⟩
  | step state choice remaining budget allowed cost branches ih =>
    obtain ⟨maximum, hmaximum, hle⟩ := worstBound_meets values choice.children remaining ih
    have alternative := certificate.2 state choice allowed
    rw [hmaximum] at alternative
    apply boundLE_finite alternative
    exact Nat.le_trans (Nat.add_le_add_left hle choice.cost) cost

theorem infinite_value_unwinnable {game : Game State} {values : State → Option Nat}
    (certificate : ValidLower game values) {state : State}
    (infinite : values state = none) : ∀ budget, ¬ CanWin game state budget := by
  intro budget win
  obtain ⟨required, finite, _⟩ := lower_certificate_sound certificate win
  simp [infinite] at finite

def ValidUpper (game : Game State) (values : State → Option Nat) (rank : State → Nat) : Prop :=
  ∀ state required, values state = some required →
    game.goal state = true ∨
    ∃ choice, choice ∈ game.choices state ∧
      addBound choice.cost (worstBound values choice.children) = some required ∧
      ∀ child, child ∈ choice.children → rank child < rank state

theorem upper_certificate_sound {game : Game State} {values : State → Option Nat}
    {rank : State → Nat} (certificate : ValidUpper game values rank)
    {state : State} {required : Nat} (finite : values state = some required) :
    CanWin game state required := by
  have ranked : ∀ height, ∀ current, rank current = height →
      ∀ amount, values current = some amount → CanWin game current amount := by
    intro height
    induction height using Nat.strongRecOn with
    | ind height ih =>
      intro current sameHeight amount value
      rcases certificate current amount value with goal | chosen
      · exact CanWin.done current amount goal
      · obtain ⟨choice, allowed, equal, descending⟩ := chosen
        cases hm : worstBound values choice.children with
        | none => simp [addBound, hm] at equal
        | some maximum =>
          have costEqual : choice.cost + maximum = amount := by simpa [addBound, hm] using equal
          apply CanWin.step current choice maximum amount allowed (Nat.le_of_eq costEqual)
          intro child member
          obtain ⟨needed, hneeded, hle⟩ := member_meets_worstBound values choice.children hm member
          have smaller : rank child < height := by simpa [sameHeight] using descending child member
          have childWin := ih (rank child) smaller child rfl needed hneeded
          exact canWin_mono childWin hle
  exact ranked (rank state) state rfl required finite

/-- A two-sided certificate establishes an exact minimax budget in the arena. -/
theorem certified_exact_budget {game : Game State} {values : State → Option Nat}
    {rank : State → Nat} (lower : ValidLower game values)
    (upper : ValidUpper game values rank) {state : State} {required : Nat}
    (finite : values state = some required) :
    CanWin game state required ∧ (∀ budget, CanWin game state budget → required ≤ budget) := by
  refine ⟨upper_certificate_sound upper finite, ?_⟩
  intro budget win
  obtain ⟨other, equal, hle⟩ := lower_certificate_sound lower win
  have same : required = other := by simpa [finite] using equal
  simpa [same] using hle

end Strategies

end CausalFill.Information
