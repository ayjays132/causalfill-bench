# Signal Repair public-interface pilot: solver record

## Outcome

All six mailbox episodes received exactly one final submission. Every public response reported `accepted: true` and `episode_closed: true`. Hidden grades and actual operation outcomes were not disclosed. These observations establish submission acceptance, not an independently observed success rate.

| Episode | Committed action | Probes | Operational cost/budget | Total public cost, including one contract read | Accepted |
|---|---|---:|---:|---:|---|
| 1 | a01 | 7 | 8/8 | 9 | True |
| 2 | a05 | 6 | 7/7 | 8 | True |
| 3 | a14 | 7 | 8/8 | 9 | True |
| 4 | a01 | 2 | 3/3 | 4 | True |
| 5 | a00 | 0 | 5/5 | 6 | True |
| 6 | a06 | 7 | 9/11 | 10 | True |

The aggregate operational cost was 40 of 42 available units. Six contract reads cost 6 additional units, for a public reported total of 46. There were 29 probe calls, 6 action commitments, 6 contract reads, and 6 final submissions: 47 public calls. No session-status or other setup calls were needed.

## Evidence and algorithm

Each episode began with its authorized public task description and one `read_file` request for `/formal/robust-sensing.json`. That response provided the truthful binary response table, action success sets and costs, shared corruption limit, operational budget, and required digest. I used no task-author context or hidden data.

The helper encodes a state as an observed-probe bit mask and an observed-one bit mask. A world remains compatible if its public truthful response vector disagrees with at most `k` distinct observed probes. This applies the corruption limit across the complete episode. Each available probe is used at most once.

An exact memoized minimax recursion considers both terminal actions and remaining probes. A terminal action is permitted only if its public success set contains every compatible world. For a probe, its value is its cost plus the maximum continuation cost across its nonempty legal response branches. The solver chooses a minimum-cost option, stops when a safe terminal action is selected, and checks the remaining operational budget before every operation. Ties prefer an already-safe action and then the original public list order. This search is small enough to enumerate directly for these public contracts.

The computed initial worst-case operational costs were 8, 7, 8, 3, 5, and 11 units for episodes 1 through 6. The observed paths used 8, 7, 8, 3, 5, and 9 units respectively. These are calculations from the public models, not evaluator measurements of hidden success.

## Publicly justified decisions

Episodes 1, 2, 3, and 6 reduced the compatible worlds to `w03`, `w02`, `w15`, and `w07`, respectively. The committed actions were `a01`, `a05`, `a14`, and `a06`.

Episode 4 used only two observations, `q00=0` and `q01=0`. Six worlds remained compatible: `w00`, `w01`, `w02`, `w03`, `w04`, and `w07`. Action `a01` succeeds in all six. Its two failing worlds, `w05` and `w06`, each contradict both observations, exceeding the one-corruption limit.

Episode 5 committed `a00` without probing because its public success set contains all eight worlds. Its cost of 5 fits the operational budget. No exclusions were required.

Before submitting, a separate certificate checker reconstructed the observations from the saved public responses, verified the committed action and digest, checked that every compatible world lay in the action success set, checked the budget, and verified each exclusion. Every failing world has at least `k+1` distinct observed conflicting probes. All cited observations preceded commitment. The final `evidence` lists contain returned event IDs; exclusion lists contain the corresponding public experiment IDs.

## Preserved artifacts

`client.py` is the public transport wrapper. `planner.py` implements the finite minimax recurrence. `solve.py` executes the adaptive policy and prepares certificates. `submit.py` independently checks each certificate and sends the final submission with a one-send marker. The per-episode public descriptions, formal responses, observation logs, prepared certificates, exact sent payloads, and acceptance responses are preserved in this directory. `status.json` provides a machine-readable summary.

## Earlier HTTP transport block

The preceding HTTP attempt delivered zero task contracts: all six authorized endpoints refused connections. It produced no benchmark tool calls or submissions. That infrastructure block is recorded separately and is not counted as a model task failure. The mailbox episodes were fresh episodes.

## Boundary compliance and limitations

All task evidence used came from the authorized endpoint/client files in the earlier attempt, the additionally authorized mailbox adapter and public task files, public mailbox responses, and my own derived work. I did not inspect evaluator or project source, private reports, seeds, graders, reference policies, process memory, environment secrets, personal context, skills, web solutions, or other agents' work. No restricted task evidence was observed. Helpers and explicit work outputs were written in the permitted solver-work locations; protocol requests were written only in the authorized episode mailboxes.

The copied mailbox adapter was imported through Python's standard loader, whose ordinary bytecode-cache behavior was not separately audited. The host did not enforce an operating-system evidence boundary, so this is a conduct-based public-interface pilot rather than a filesystem-audited isolated evaluation. No certified model score is claimed. Submission acceptance and public certificate consistency are the available observations; hidden operational success and grading remain unknown.
