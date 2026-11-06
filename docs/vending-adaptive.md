# Adaptive vending: a complete finite procurement game

`vending_adaptive` is a separate v0.4 task family. It preserves the earlier
vending family's fill-in-the-gap procurement and real-accounting ideas while
introducing hidden, changing demand and irreversible purchasing decisions.
The earlier `vending` family retains its existing semantics.

The new family supplies an explicit table of possible worlds, a small mutable
economic runtime, and a separate compiler into a finite partially observed
game. An independently checked certificate can establish the minimum
worst-case operational cost of guaranteed success in that game. It can also
establish that every fixed script fails on at least one permitted world.
These are bounded statements about the released model. They establish neither
language-model difficulty nor a new planning algorithm, and they do not
validate real-world commercial or robotic performance.

## Public task and success

An episode has two, three, or four rounds. Each round requires one case of a
single product, `tea` or `cocoa`. A case contains four or six units and exactly
fills the cold store. The product demanded in the current round is initially
hidden. The complete candidate-world table is public, but the true row is not
marked. Future rounds can have different demand.

The participant must restore four missing procurement fields:

| Field | Meaning | Public evidence |
| --- | --- | --- |
| `standard_lead_days` | Standard supplier's fixed delivery delay | Quote arrival minus order day |
| `fixed_shipping_cents` | Fixed standard shipping fee per order | Difference between one-case and two-case quote schedules |
| `case_shipping_cents` | Additional shipping fee for each case | Two-case shipping minus one-case shipping |
| `receipt_event` | Event that makes purchased stock physically available | Published accounting rules: `delivery` |

For shipping quotes (S_1) and (S_2), the recoverable fields are

\[
c = S_2-S_1,\qquad f=S_1-c,\qquad S(q)=f+cq.
\]

Quotes for multiple cases are hypothetical tariff observations. Actual orders
are indivisible single cases because one case fills storage. The masked
shipping rule therefore includes a counterfactual quantity term even though
the operating storage capacity remains one case.

Success requires all four fields to be correct, every round completed, every
request served, final cash at least the public target, and valid accounting.
The score checks final outcomes. It does not inspect whether a participant
called `forecast`, `assay`, `calibrate`, or any minimum number of observations.
A participant that legitimately infers a demand without another experiment
can buy immediately.

## Physical and financial transition rules

Each round starts on day `2 * stage` and closes two days later. The standard
supplier takes one or two days; express takes one day and adds a public fixed
surcharge. Both arrive before the market closes.

An `order` immediately debits item and shipping costs, records an invoice, and
creates pending stock. It does not create available stock. `settle` advances
to the market deadline and performs these operations in order:

1. Record physical delivery and move the case into available stock.
2. Sell only units of the demanded product at the public fixed price.
3. Expire all remaining stock; no goods carry into the next round.
4. Pay the public operating fee and publish the market result.

There is no borrowing, refund, resale, terminal inventory value, or choice of
price that can suppress the service denominator. A missed request closes the
service contract irreversibly. Settling without an order is permitted but
misses the entire request. Ordering the wrong product delivers real goods,
pays real money, serves no requests, and expires the goods.

Let (u) be case size, (p) the selling price per unit, (w) the unit purchase
cost, (f+c) the one-case standard shipping cost, (o) the operating fee, and

\[
\pi=up-(uw+f+c)-o.
\]

With (T) rounds, initial cash (C_0), and express surcharge (e>0), the
published target is

\[
C_{\mathrm{target}}=C_0+T\pi-e.
\]

Every perfectly served all-standard trajectory ends at (C_0+T\pi). One
express order is therefore a valid alternative and ends exactly at the cash
target. Two express orders make the target unreachable. The runtime closes
that business after its next settlement because even the largest possible
future profit cannot repair the deficit. This decision uses actual cash and
the published future-profit bound. The compiler expresses the equivalent
condition with its accumulated express count.

Initial cash funds every legal order prefix, even without sales. Therefore an
insufficient-cash error cannot leak the hidden demand before a purchase. The
cash goal still imposes a real spending constraint. All amounts use integer
cents; no floating-point rounding participates in grading.

## Experiments and information structure

Each round has one diagnostic sampling opportunity. The participant chooses
either the cheaper coded forecast or the more expensive direct assay.
Calibration is a separate experiment available once per episode in any open
round. Samples and calibration must precede the irreversible order.

| Tool | Cost | Result or effect |
| --- | ---: | --- |
| `calibrate` | 1 | Reveal the shared calibration bit; once per episode |
| `forecast` | 1 | Reveal this round's coded demand bit; consumes its diagnostic sample |
| `assay` | 2 | Reveal this round's demand bit directly; consumes its diagnostic sample |
| `order` | 2 | Pay for one case of a chosen product and supplier |
| `settle` | 1 | Deliver, sell, expire leftovers, pay fees, and reveal realized demand |
| `quote` | 1 | Reveal static tariff and delivery terms for one to three cases |
| `status` | 1 | Repeat current public state and accounting totals |
| `ledger` | 1 | Read up to 100 prior financial events |

An already consumed sample cannot be resampled or replaced, and an accepted
order cannot be changed. These are public interface constraints, not grading
requirements. Invalid domain actions leave all domain state unchanged; the
outer Session still charges the applicable tool cost and records the error.

The split determines the forecast mechanism and candidate-world set:

| Split | Candidate demand sequences | Forecast bit at round (t) | Candidate worlds for 2 / 3 / 4 rounds |
| --- | --- | --- | --- |
| `train` | All binary sequences | (d_t) | 4 / 8 / 16 |
| `dev` | All binary sequences, each with both calibration values | (d_t\oplus k) | 8 / 16 / 32 |
| `transfer` | All sequences containing both products, each with both calibration values | (d_t\oplus k\oplus d_{t-1}), with (d_{-1}=0) | 4 / 12 / 28 |

The public `/market/contract.json` contains the complete world table, forecast
rule, prices, capacity, horizon, cash target, and all public economic
parameters. Each row contains only `demand: [bit, ...]` and
`calibration: bit`. The generator shuffles the rows and selects the true row
without marking it. The certification problem requires success in every row;
its validity does not depend on assigning a probability distribution.

The transfer restriction can save a future query. In a two-round transfer
episode, observing the first demand determines the second because both
products must occur. With more rounds, such deduction depends on the realized
prefix. This creates a small opportunity to combine sensing, public
constraints, and operating feedback instead of repeating a fixed sampling
schedule.

Twins share all public files, economic parameters, and calibration. The twin
changes the categorical demand-trajectory parameter to the complemented
sequence. This can alter several round values and is explicitly reported as
`twin_kind: demand_trajectory`; it is not presented as a one-coordinate
physical intervention.

## Finite-game projection and independent checks

`compile_market_game(contract, recovered_terms)` consumes the public world
table and economic terms recoverable through quotes. It does not receive a
selected-world index. The runtime's `game_statement()` supplies the same
statement for evaluator audits.

The compiler uses the shared `finite-belief-game-v1` schema:

- A global action table provides exact action IDs, positive costs, and
  `observe` or `act` classifications.
- Each concrete state has a decreasing integer rank, canonical public
  observation string, terminal outcome, and every available action edge.
- Initial states enumerate every possible world and share the same initial
  public observation.
- Terminal states have rank zero and no outgoing economic actions.

Actions are primitive tools, including separate purchase and settlement
steps. `order:0:standard`, for example, maps to
`order({"product":"tea","supplier":"standard"})`. Both products, both
suppliers, both diagnostic choices, calibration whenever available, and
settlement without an order are included. No search-depth cutoff removes an
allowed alternative.

The runtime computes mutable invoices, deliveries, stock, revenues, expiry,
fees, and cash. The compiler separately derives projected cash and inventory
from stage, order status, successful service prefix, express count, and breach
condition. It does not call runtime `query`, `evaluate`, or a reference answer
to construct transitions. That separation permits meaningful conformance
testing, although both are still Python implementations of the specified
economy.

Every domain response contains an `observation` string matching its projected
node. Quote details, invoices, market records, status accounting, and ledger
history are functions of the public contract, recovered terms, and the
participant's action/observation history. They must not contain another
latent-world channel. Session event IDs, accumulated cost, and errors also
depend only on the public interaction history for domain-equivalent states.

The finite arena omits positive-cost stutters: static file reads, tariff
quotes after recovery, status/ledger repeats, and invalid actions. These
cannot improve operational information once the contract and terms are
given. Removing them cannot destroy an otherwise successful operational
strategy and cannot increase its action cost. This argument is scoped to the
published observation contract; runtime conformance tests audit the relevant
extra response fields and invalid-action behavior.

There are four deliberately different comparisons:

| Mode | Paid experiments allowed? | Operational feedback usable? |
| --- | --- | --- |
| `adaptive` | Yes | Yes |
| `no_observe` | No | Yes |
| `open_loop` | Yes | No; one fixed script |
| `open_loop_no_observe` | No | No; one fixed script |

`no_observe` still learns from receipts and realized market demand. Its
impossibility result is stronger than testing a single fixed procurement
baseline: the initial unresolved product decision already forces an
irreversible failure in some candidate world. The complete certificate also
checks all later alternatives rather than relying solely on that informal
argument.

The independently checked operational minimax costs for the nine released
profiles are:

| Split | 2 rounds | 3 rounds | 4 rounds |
| --- | ---: | ---: | ---: |
| `train` | 8 | 12 | 16 |
| `dev` | 9 | 13 | 17 |
| `transfer` | 8 | 13 | 17 |

The three restricted modes have no guaranteed winning strategy in all nine
profiles. These costs cover only finite-game actions. They exclude file and
quote setup and the final fill submission. They do not assert an end-to-end
minimum for recovering the terms. A sufficient public setup is one contract
read and two quotes, costing three more units.

The largest full graph has 8,192 states and 13,664 transitions. The small
two-round training fixture has four worlds, 448 states, and 732 transitions.
Its exact raw statement, four mode certificates, and winning strategy are
exported under `artifacts/v04/finite-games/`. Counts describe this finite
representation; they are not a difficulty metric.

## Public controller and audit APIs

`solve_vending_adaptive(public, call)` is a constructive authored reference.
It reads the public contract, recovers fees and delivery time from quotes,
calibrates when the forecast rule needs it, and filters possible worlds using
the realized demand prefix. It samples a forecast only while the current
demand remains ambiguous, then places a standard order and settles the
round. Its callback receives ordinary Session tools. It does not read a
task's private row, private answer, model state, or compiler certificate.

The episode cost budget is `5 * rounds + 8`; the call limit is
`6 * rounds + 20`. The direct-assay controller is another valid solution:
assay every round, make one express purchase if desired, and use the standard
supplier thereafter. It needs neither calibration nor forecasts and still
fits the budget. Successful execution with this alternative demonstrates that
scoring depends on outcomes rather than a required sensor name.

Evaluator-only helpers support exhaustive independent audit:

```python
task.game_statement()                 # defensive copy of the full arena
task.game_state_id()                  # current evaluator state projection
task.clone_for_world(index)           # fresh runtime with a selected world
task.game_replay_witness(node_id)      # initial world + primitive action path
market_action_request(contract, aid)  # exact public tool name and arguments
```

Selecting a world and obtaining state IDs are never public episode tools.
Evaluator clones may share the immutable compiled table; mutable economic
state and ledgers remain separate. A scored model must operate through the
isolated public interface, not these authoring helpers.

## Validation and limits

`tests/test_vending_adaptive.py` covers every listed world across all nine
profiles for two reference-controller seeds; all-world direct-assay and
one-express alternatives; fixed procurement scripts versus raw demand rows;
independent cash and inventory reconstruction from events; sensor truth
tables; typed invalid-action atomicity; wrong-stock, missing-order, and
cash-goal failures; static-read nonleakage; twin equality; defensive copying;
and strict compiler inputs. Run the focused suite with:

```bash
python -m unittest tests.test_vending_adaptive -v
```

The separate v0.4 release stress harness compares real primitive tool
transitions with the complete graph and checks additional interface
observations. The finite-game checker independently checks the optimizer's
certificate; the strategy checker separately replays its actions in every
raw initial world. Lean assurance is scoped to the exported finite statement
and the checked theorem, not automatically to the Python economic runtime or
the compiler that produced that statement.

The market is intentionally small, deterministic, and fully specified. It
tests action-dependent information use and irreversible procurement within
an exact model. It has no natural-language negotiation, noisy sensors,
competitors, real payments, continuous motion, perception, or learned demand
model. An authored controller solving the suite is evidence of solvability.
Evaluating a language model, claiming transfer to robotics, or asserting a
scientific breakthrough requires separate experiments and evidence.
