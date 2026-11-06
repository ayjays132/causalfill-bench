import CausalFill.BoundedFault

/- The explicit aliases bind the selected theorem names to independently
   written types. The verifier mutates one theorem to a weaker, well-typed
   statement and requires this audit to reject the changed import. -/
namespace CausalFill.BoundedFault.StatementAudit

open CausalFill.BoundedFault

example {Query World : Type} (truth : Query → World → Bool) (world : World)
    (left right : List (Reading Query)) :
    mismatches truth world (left ++ right) =
      mismatches truth world left + mismatches truth world right :=
  mismatches_append truth world left right

example {Query World : Type} (truth : Query → World → Bool) (world : World)
    (history : List (Reading Query)) (query : Query) (reported : Bool) :
    mismatches truth world (history ++ [(query, reported)]) =
      mismatches truth world history + discrepancy (truth query world) reported :=
  mismatches_step truth world history query reported

example {Query World : Type} (truth : Query → World → Bool) (world : World)
    (history : List (Reading Query)) (used : Nat) :
    Realizes truth world history used ↔ mismatches truth world history = used :=
  realizes_iff_mismatches truth world history used

example {Query World : Type} (truth : Query → World → Bool) (cap : Nat)
    (history : List (Reading Query)) (world : World) :
    Feasible truth cap history world ↔
      ∃ used, used ≤ cap ∧ Realizes truth world history used :=
  feasible_iff_realizes_within truth cap history world

example (cap debt added : Nat) :
    capped cap (capped cap debt + added) = capped cap (debt + added) :=
  capped_update_exact cap debt added

example (cap debt : Nat) : capped cap debt ≤ cap ↔ debt ≤ cap :=
  capped_live_iff cap debt

example {Query World : Type} (truth : Query → World → Bool) (cap : Nat)
    (world : World) (history : List (Reading Query)) (query : Query) (reported : Bool) :
    capped cap (mismatches truth world (history ++ [(query, reported)])) =
      capped cap (capped cap (mismatches truth world history) +
        discrepancy (truth query world) reported) :=
  capped_state_step truth cap world history query reported

example {Query World : Type} (truth : Query → World → Bool) (cap : Nat)
    (history : List (Reading Query)) (world : World) (used : Nat)
    (realized : Realizes truth world history used) (bounded : used ≤ cap) :
    Feasible truth cap history world :=
  true_world_preserved truth cap history world used realized bounded

example {Query World : Type} (truth : Query → World → Bool) (cap : Nat)
    (world : World) (history continuation : List (Reading Query))
    (excluded : cap < mismatches truth world history) :
    cap < mismatches truth world (history ++ continuation) :=
  excluded_stays_excluded truth cap world history continuation excluded

example {Query World : Type} (truth : Query → World → Bool) (world : World)
    (history : List (Reading Query)) :
    (badReadings truth world history).length = mismatches truth world history :=
  badReadings_length truth world history

example {Query World : Type} (truth : Query → World → Bool) (world : World)
    (history selected : List (Reading Query))
    (supported : selected.Sublist (badReadings truth world history)) :
    selected.length ≤ mismatches truth world history :=
  witness_count_le_mismatches truth world history selected supported

example {Query World : Type} (truth : Query → World → Bool) (cap : Nat)
    (history : List (Reading Query)) (world : World)
    (witness : ExclusionWitness truth cap history world) :
    ¬ Feasible truth cap history world :=
  exclusion_witness_sound truth cap history world witness

example {Query World Action : Type} (truth : Query → World → Bool) (cap : Nat)
    (history : List (Reading Query)) (worlds : List World)
    (success : World → Action → Prop) (action : Action)
    (witnesses : ∀ world, world ∈ worlds → ¬ success world action →
      ExclusionWitness truth cap history world) :
    SafeAction truth cap history worlds success action :=
  witnesses_certify_action truth cap history worlds success action witnesses

example {Query World Action : Type} (truth : Query → World → Bool) (cap : Nat)
    (history : List (Reading Query)) (worlds : List World)
    (success : World → Action → Prop) (action : Action)
    (world : World) (used : Nat)
    (member : world ∈ worlds) (realized : Realizes truth world history used)
    (bounded : used ≤ cap) (safe : SafeAction truth cap history worlds success action) :
    success world action :=
  safe_action_sound truth cap history worlds success action world used member realized bounded safe

end CausalFill.BoundedFault.StatementAudit

#print axioms CausalFill.BoundedFault.mismatches_append
#print axioms CausalFill.BoundedFault.mismatches_step
#print axioms CausalFill.BoundedFault.realizes_iff_mismatches
#print axioms CausalFill.BoundedFault.feasible_iff_realizes_within
#print axioms CausalFill.BoundedFault.capped_update_exact
#print axioms CausalFill.BoundedFault.capped_live_iff
#print axioms CausalFill.BoundedFault.capped_state_step
#print axioms CausalFill.BoundedFault.true_world_preserved
#print axioms CausalFill.BoundedFault.excluded_stays_excluded
#print axioms CausalFill.BoundedFault.badReadings_length
#print axioms CausalFill.BoundedFault.witness_count_le_mismatches
#print axioms CausalFill.BoundedFault.exclusion_witness_sound
#print axioms CausalFill.BoundedFault.witnesses_certify_action
#print axioms CausalFill.BoundedFault.safe_action_sound
