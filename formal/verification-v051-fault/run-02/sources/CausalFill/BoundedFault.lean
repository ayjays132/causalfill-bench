import Std

/-!
# One global budget of corrupted binary observations

The hidden world is fixed. A truthful response table is supplied as a function.
Each transcript occurrence contains a query and a reported bit. Corruption is
an actual bit flip, and its count is shared across the whole transcript.

These statements concern that mathematical model. They do not assert that the
Python parser, simulator, action costs, or certificate optimizer implement it.
The once-only query rule is a separate runtime condition; these soundness
statements hold even for transcripts that repeat a query. A witness is a
subsequence of actual contradictory transcript occurrences, so it cannot reuse
one occurrence to inflate its count. Runtime one-use query IDs must be checked
against those accepted occurrences by the runtime checker.
-/

namespace CausalFill.BoundedFault

variable {Query World Action : Type}

abbrev Reading (Query : Type) := Query × Bool

/-- A binary response spends one corruption precisely when it is not truthful. -/
def discrepancy (expected reported : Bool) : Nat :=
  if reported = expected then 0 else 1

/-- Total corruption debt for one candidate fixed world. -/
def mismatches (truth : Query → World → Bool) (world : World) :
    List (Reading Query) → Nat
  | [] => 0
  | (query, reported) :: rest =>
      discrepancy (truth query world) reported + mismatches truth world rest

/-- Independent operational semantics: each occurrence is honest or flipped. -/
inductive Realizes (truth : Query → World → Bool) (world : World) :
    List (Reading Query) → Nat → Prop where
  | nil : Realizes truth world [] 0
  | honest {history : List (Reading Query)} {used : Nat} (query : Query)
      (prior : Realizes truth world history used) :
      Realizes truth world ((query, truth query world) :: history) used
  | corrupt {history : List (Reading Query)} {used : Nat} (query : Query)
      (prior : Realizes truth world history used) :
      Realizes truth world ((query, !(truth query world)) :: history) (used + 1)

/-- Feasibility is exact discrepancy count at most the one global bound. -/
def Feasible (truth : Query → World → Bool) (cap : Nat)
    (history : List (Reading Query)) (world : World) : Prop :=
  mismatches truth world history ≤ cap

/-- All over-budget counts are represented by the permanent dead value cap+1. -/
def capped (cap debt : Nat) : Nat := min (cap + 1) debt

theorem mismatches_append (truth : Query → World → Bool) (world : World)
    (left right : List (Reading Query)) :
    mismatches truth world (left ++ right) =
      mismatches truth world left + mismatches truth world right := by
  induction left with
  | nil => simp [mismatches]
  | cons reading rest ih =>
    rcases reading with ⟨query, reported⟩
    simp [mismatches, ih, Nat.add_assoc]

theorem mismatches_step (truth : Query → World → Bool) (world : World)
    (history : List (Reading Query)) (query : Query) (reported : Bool) :
    mismatches truth world (history ++ [(query, reported)]) =
      mismatches truth world history + discrepancy (truth query world) reported := by
  simp [mismatches_append, mismatches]

theorem realizes_iff_mismatches (truth : Query → World → Bool) (world : World)
    (history : List (Reading Query)) (used : Nat) :
    Realizes truth world history used ↔ mismatches truth world history = used := by
  constructor
  · intro realization
    induction realization with
    | nil => rfl
    | honest query prior ih =>
      simpa [mismatches, discrepancy] using ih
    | corrupt query prior ih =>
      cases response : truth query world <;>
        simp [mismatches, discrepancy, response, ih, Nat.add_comm]
  · intro equal
    subst used
    induction history with
    | nil => exact Realizes.nil
    | cons reading rest ih =>
      rcases reading with ⟨query, reported⟩
      by_cases same : reported = truth query world
      · subst reported
        simpa [mismatches, discrepancy] using Realizes.honest query ih
      · have flipped : reported = !(truth query world) := by
          cases reported <;> cases response : truth query world <;> simp_all
        rw [flipped]
        have step := Realizes.corrupt query ih
        cases response : truth query world <;>
          simpa [mismatches, discrepancy, response, Nat.add_comm] using step

theorem feasible_iff_realizes_within (truth : Query → World → Bool) (cap : Nat)
    (history : List (Reading Query)) (world : World) :
    Feasible truth cap history world ↔
      ∃ used, used ≤ cap ∧ Realizes truth world history used := by
  constructor
  · intro feasible
    exact ⟨mismatches truth world history, feasible,
      (realizes_iff_mismatches truth world history _).mpr rfl⟩
  · rintro ⟨used, bounded, realized⟩
    have equal := (realizes_iff_mismatches truth world history used).mp realized
    unfold Feasible
    omega

theorem capped_update_exact (cap debt added : Nat) :
    capped cap (capped cap debt + added) = capped cap (debt + added) := by
  simp only [capped]
  omega

theorem capped_live_iff (cap debt : Nat) :
    capped cap debt ≤ cap ↔ debt ≤ cap := by
  simp only [capped]
  omega

theorem capped_state_step (truth : Query → World → Bool) (cap : Nat)
    (world : World) (history : List (Reading Query)) (query : Query) (reported : Bool) :
    capped cap (mismatches truth world (history ++ [(query, reported)])) =
      capped cap (capped cap (mismatches truth world history) +
        discrepancy (truth query world) reported) := by
  rw [mismatches_step]
  exact (capped_update_exact cap _ _).symm

theorem true_world_preserved (truth : Query → World → Bool) (cap : Nat)
    (history : List (Reading Query)) (world : World) (used : Nat)
    (realized : Realizes truth world history used) (bounded : used ≤ cap) :
    Feasible truth cap history world :=
  (feasible_iff_realizes_within truth cap history world).mpr ⟨used, bounded, realized⟩

theorem excluded_stays_excluded (truth : Query → World → Bool) (cap : Nat)
    (world : World) (history continuation : List (Reading Query))
    (excluded : cap < mismatches truth world history) :
    cap < mismatches truth world (history ++ continuation) := by
  rw [mismatches_append]
  omega

/-- Contradictory actual occurrences, with order and multiplicity preserved. -/
def badReadings (truth : Query → World → Bool) (world : World)
    (history : List (Reading Query)) : List (Reading Query) :=
  history.filter (fun reading => !(reading.2 == truth reading.1 world))

theorem badReadings_length (truth : Query → World → Bool) (world : World)
    (history : List (Reading Query)) :
    (badReadings truth world history).length = mismatches truth world history := by
  induction history with
  | nil => rfl
  | cons reading rest ih =>
    rcases reading with ⟨query, reported⟩
    cases reported <;> cases response : truth query world <;>
      simp_all [badReadings, mismatches, discrepancy, Nat.add_comm]

/-- Subsequence support prevents reusing a single transcript occurrence. -/
def ExclusionWitness (truth : Query → World → Bool) (cap : Nat)
    (history : List (Reading Query)) (world : World) : Prop :=
  ∃ selected : List (Reading Query),
    selected.Sublist (badReadings truth world history) ∧ cap < selected.length

theorem witness_count_le_mismatches (truth : Query → World → Bool) (world : World)
    (history selected : List (Reading Query))
    (supported : selected.Sublist (badReadings truth world history)) :
    selected.length ≤ mismatches truth world history := by
  calc
    selected.length ≤ (badReadings truth world history).length := supported.length_le
    _ = mismatches truth world history := badReadings_length truth world history

theorem exclusion_witness_sound (truth : Query → World → Bool) (cap : Nat)
    (history : List (Reading Query)) (world : World)
    (witness : ExclusionWitness truth cap history world) :
    ¬ Feasible truth cap history world := by
  rcases witness with ⟨selected, supported, enough⟩
  have count := witness_count_le_mismatches truth world history selected supported
  unfold Feasible
  omega

/-- Success regions may overlap. No identification requirement is introduced. -/
def SafeAction (truth : Query → World → Bool) (cap : Nat)
    (history : List (Reading Query)) (worlds : List World)
    (success : World → Action → Prop) (action : Action) : Prop :=
  ∀ world, world ∈ worlds → Feasible truth cap history world → success world action

theorem witnesses_certify_action (truth : Query → World → Bool) (cap : Nat)
    (history : List (Reading Query)) (worlds : List World)
    (success : World → Action → Prop) (action : Action)
    (witnesses : ∀ world, world ∈ worlds → ¬ success world action →
      ExclusionWitness truth cap history world) :
    SafeAction truth cap history worlds success action := by
  intro world member feasible
  apply Classical.byContradiction
  intro failed
  exact exclusion_witness_sound truth cap history world
    (witnesses world member failed) feasible

theorem safe_action_sound (truth : Query → World → Bool) (cap : Nat)
    (history : List (Reading Query)) (worlds : List World)
    (success : World → Action → Prop) (action : Action)
    (world : World) (used : Nat)
    (member : world ∈ worlds) (realized : Realizes truth world history used)
    (bounded : used ≤ cap) (safe : SafeAction truth cap history worlds success action) :
    success world action :=
  safe world member (true_world_preserved truth cap history world used realized bounded)

end CausalFill.BoundedFault
