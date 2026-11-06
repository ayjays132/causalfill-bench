# Original grid-program induction

## Purpose and provenance

This domain explores the idea of inferring a visual transformation from a few
examples, then choosing an experiment when examples are ambiguous. It is
inspired by ARC's emphasis on novel task rules and generalization, but contains
only original procedural tasks. No ARC dataset items, evaluator code, scores,
or branding are bundled. A score here is not an ARC-AGI score.

This is a small, explicit induction control family. Its public grammar has
12 train candidates, 48 dev candidates, and 48 transfer candidates. It is not
advertised as a difficult frontier-model benchmark on its own. Agent
performance needs to be measured before claims about difficulty can be made.

## Interface

Grids have one to eight rows and columns. Each cell is an exact integer from
zero to four; zero denotes background. The solver receives masked pipeline
slots and can read demonstrations. The `transform` tool evaluates a chosen
valid grid at cost one. A submission contains a `program` list with at most
four operations, executed in order.

| Operation | Meaning |
| --- | --- |
| `recolor(source, target)` | Replace one nonzero color throughout the grid. |
| `rotate90(turns)` | Rotate clockwise by zero, one, two, or three quarter turns. |
| `keep_color(color)` | Replace every other color with background. |
| `crop` | Retain the smallest nonzero bounding rectangle; all-zero becomes `[[0]]`. |
| `flip_h` | Reverse every row. |

The DSL is interpreted as data, never executed as submitted source. Inputs
must be rectangular and bounded. Booleans, floats, invalid colors, extra
fields, and unknown operations are rejected. Empty programs are legal
identity maps. Equivalent compositions can pass even when they differ from
the planted program.

## Structural splits

- **Train:** a single recoloring operation.
- **Dev:** rotation followed by recoloring.
- **Transfer:** retain one color, crop its bounding box, rotate, then recolor.

The transfer skeleton composes selection, object extent, geometry, and symbol
mapping. It is structurally held out from the train and dev grammars. Some
primitive operations are absent from the train generation grammar and are
introduced by the documented DSL; this should not be described as a pure
composition-only split in which all individual primitives were learned in
training. The DSL is public in every split. There are only three task
templates, so results cannot establish broad distribution-shift robustness.

Difficulty changes the number of demonstrations (three, two, or one) and
the total cost budget (ten, seven, or five). It does not silently change the
semantics or add inaccessible hidden rules. In transfer tasks, singleton
examples deliberately leave selection and orientation unresolved. An active
experiment supplies the missing evidence.

## Solvability witness

One 8x8 diagnostic grid contains four asymmetric L shapes of different colors
and areas: three, four, five, and six cells. Every shape has four distinct
rotations. When a transfer program selects and crops one color, its area
identifies the source, orientation identifies the rotation, and output value
identifies the recoloring. The same experiment distinguishes all train and
dev candidates as well.

An executable test enumerates every grammar candidate and checks that all
diagnostic outputs are distinct. The helper `infer_program` takes only the
public split name and observed input/output examples. It cannot inspect a
task object, seed, hidden program, or evaluator. A measured reference can
issue the diagnostic through the budgeted session; a test verifies success
with one tool cost unit. The diagnostic is a disclosed engineering control,
not a secret answer or a claim of human-like abstraction.

## Behavioral verification

The grader runs every color assignment for 1x1, 1x2, 2x1, and 2x2 grids,
plus the asymmetric diagnostic, all-background edge cases, and 32 separately
generated larger rectangular grids. It checks output dimensions and cell
values exactly. The candidate program is not compared to the planted syntax.
For example, two horizontal flips before a recolor remain acceptable.

The grid verifier is a finite behavioral suite. It is not a complete proof
of equivalence over every valid 8x8 grid and every permissible candidate
program. This differs from the latent affine domain, whose zero-and-basis
certificate is complete within its stated affine class. The test suite
specifically verifies that a program fitting the visible singleton examples
can still fail held-out cases.

The counterfactual twin changes exactly the final recoloring target. All
input grids, source selection, rotation, structural class, and random checks
remain fixed. Demonstration outputs change as consequences of that one
intervention. Reusing the original fill fails the twin.

## Relevant primary source

ARC Prize describes the benchmark's reasoning and generalization motivation:
<https://arcprize.org/arc-agi>. This prototype adapts that broad experimental
principle only; it implements its own task distribution and active-query
protocol.
