# Workflow symbolic certification

Workflow strict success now requires a sufficient symbolic proof of equality and bounded total evaluation over a public integer input domain. Finite behavioral tests remain a separate diagnostic and an additional acceptance condition. This closes the demonstrated finite-test blind spot: adding `max(0,scale-19)` to the correct expression passes every previous behavioral test but changes the result at `scale=20`.

The implementation is ordinary Python in `causalfill/workflow_certificate.py`. It is not Lean-checked, does not invoke an external computer algebra system, and does not claim to decide every mathematical equivalence. The checker never calls the workflow interpreter, task generator, behavioral tests, or reference policy to obtain its symbolic result. The runtime interpreter and the existing arithmetic specification supply separate behavioral checks.

## Public statement and input domain

The procedure specification remains public in `/docs/current.txt`; `/docs/certification.json` publishes the exact domain, supported proof rules, and limits. The submitted artifact remains one expression string. No additional solver-supplied axiom, assumed model, or claimed certificate is accepted.

| Input | Type and range |
|---|---|
| `balance`, `amount`, `fee`, `reserve`, `ceiling` | Integers from −1,000,000 through 1,000,000 |
| `scale` | Integer from 1 through 1,000,000 |
| Transfer floor/cap procedure | Additionally assumes `reserve <= ceiling` |

Arithmetic is exact rational arithmetic, with no rounding. Every intermediate reduced `Fraction` must have an absolute numerator at most `10**30` and denominator at most `10**30`. The certificate covers the entire declared domain, including signed inputs and future scale values. A direct call to the general Fraction interpreter outside this domain is not covered by the certificate.

The grammar allows the six input names, bounded integer literals, unary signs, addition, subtraction, multiplication, division, and `min`/`max` with two through four positional arguments. The existing source, AST and runtime depth limits remain: 800 characters, 120 AST nodes, depth 20, and integer literals with absolute value at most 10,000.

## What a positive certificate establishes

The checker independently parses the candidate and evaluator-held specification. It checks every original AST subexpression for totality and resource bounds before any cancellation can remove that subexpression. It then derives canonical forms using exact rational identities and sound min/max identities. Strict success requires all of the following:

1. Every original subexpression of both expressions is certified total and bounded on the public domain.
2. The two derived canonical forms are exactly equal. SHA256 fingerprints summarize those forms but do not replace the actual equality comparison.
3. The independent arithmetic behavioral suite passes and all its inputs lie within the public contract.

The certificate records source commitments, normal-form commitments, AST sizes, normalization work, and conservative intermediate bounds. `certify_equivalence(..., include_proof=True)` additionally exports the normalized expressions and the bound record for every original value-producing AST node. These are recomputed artifacts; the checker does not trust claims supplied by the candidate.

The result `not_certified` means that this sufficient proof system did not establish the required claim. It does **not** mean that mathematical equivalence has been disproved. A formula with a variable divisor, an inconvenient but safe cancellation, or a stronger unimplemented identity can be equivalent and still remain uncertified.

## Arithmetic proof rules

Arithmetic normalizes to a rational polynomial. A monomial is a sorted product of variable atoms and canonical lattice atoms; coefficients are exact `Fraction` values. Addition combines equal monomials, multiplication distributes and combines products, and zero coefficients disappear. Consequently, commuted products, reassociated sums, rational rescaling, and distributive identities can certify without matching the reference string.

Examples include:

```text
balance - amount*scale - fee
balance - fee - scale*amount
(2*balance - 2*fee - 2*amount*scale)/2
(balance/2 + balance/2) - amount*scale - fee
```

A divisor must normalize to a nonzero rational constant. For example, `balance/(amount-amount+2)` can normalize to `balance/2`, after certifying every original intermediate. A variable denominator remains unsupported even if a stronger system could prove it nonzero. Thus `balance/scale*scale` is mathematically equivalent to `balance` on the positive-scale domain, but this checker reports `not_certified`.

This restriction is essential to the simple totality argument. Neither `0/(scale-20)` nor `(scale-20)/(scale-20)-1` can be canceled to zero: at an allowed input, the original program divides by zero. Likewise, `0*(1/(scale-20))` must evaluate its unsafe child and cannot evade certification.

## Min/max proof rules

At a min/max boundary, each arithmetic polynomial is a leaf. The checker converts the lattice expression into a bounded maximum of minimum terms. `max` combines terms; `min` distributes across terms. Repeated leaves and terms disappear. A minimum term containing both a smaller and larger proved-ordered leaf keeps the smaller leaf. A maximum drops a term only when another term is proved at least as large.

The precise term rule is: `min(A) <= min(B)` if, for every leaf `b` in `B`, some leaf `a` in `A` has a proved relation `a <= b`. This is sound because `min(A) <= a <= b` for every such `b`, hence `min(A) <= min(B)`. The available leaf order facts are equality, exact ordering of rational constants, and the explicit `reserve <= ceiling` assumption when the task declares it.

These rules justify commutativity, associativity, idempotence, absorption, and distributivity of min/max. They also preserve a legitimate alternative floor/cap order:

```text
min(max(x,reserve),ceiling)
max(reserve,min(ceiling,x))
```

These are certified equal only when the public task guarantees `reserve <= ceiling`. Without that assumption they can differ, and the checker does not apply it. The normalizer does not infer arbitrary inequalities between polynomial leaves from sampled values.

Arithmetic can operate on entire canonical lattice atoms. Equal atoms may cancel after their original subexpressions have passed the resource and totality checks. Arithmetic operations do not generally distribute into min/max, so additional valid real-order identities can remain unsupported.

## Intermediate resource certificate

For every original AST value, the checker carries a pair `(M,D)` with the following meaning on every integer input in the declared box:

- `|value| <= M`, where `M` is a nonnegative exact rational bound.
- The reduced denominator of `value` divides the positive integer `D`.

If the reduced value is `n/d`, these two facts imply `|n| = |value| d <= M D` and `d <= D`. Requiring `M D <= 10**30` and `D <= 10**30` is therefore sufficient for the runtime Fraction limits.

| Original AST operation | Magnitude bound | Denominator divisor |
|---|---|---|
| Integer input | 1,000,000 | 1 |
| Integer constant `k` | `abs(k)` | 1 |
| Unary sign | `M` | `D` |
| Addition/subtraction | `M_a + M_b` | `lcm(D_a,D_b)` |
| Multiplication | `M_a M_b` | `D_a D_b` |
| Division by normalized constant `p/q`, `p != 0`, reduced and `q > 0` | `M_a q/abs(p)` | `D_a abs(p)` |
| `min` or `max` | Maximum child magnitude bound | LCM of child denominator divisors |

These rules are proved by induction on the original AST. Integer inputs start with denominator one. Sum denominators divide the LCM; product denominators divide the product. Dividing by `p/q` multiplies a possible denominator by `abs(p)`, while `q` multiplies the numerator. A min/max result equals one evaluated child, so the LCM and maximum are conservative. The divisor expression itself must already be total and bounded before its normalized constant value is used.

Bounds intentionally ignore many correlations and cancellations. For example, a huge `u-u` might be zero as a final mathematical expression, but the original program still evaluates `u` twice. An expression containing six multiplied `balance` values can exceed the runtime numeric cap at an allowed extreme input even though all old small behavioral inputs succeed. The checker rejects that expression before cancellation. Conversely, a syntactically redundant chain of divisions of zero can have an overly large denominator divisor even though every actual Fraction reduces to zero; that valid expression remains `not_certified` under the conservative system.

## Resource limits on proof computation

Symbolic expansion itself is bounded: at most 256 polynomial terms, 24 atoms per monomial, 128 lattice terms, 16,384 bytes per canonical representation, and 50,000 normalization work units. Coefficient integers also have an explicit bit bound. Size checks precede potentially expanding serialization. Exceeding any proof limit returns `not_certified` instead of attempting unbounded search or silently reverting to sampled acceptance.

The constants are part of the public certification contract. Limits can refuse an equivalent expression; they cannot make an uncertified expression pass strict success.

## Validation and limits of the evidence

`tests/test_workflow_certificate.py` includes the threshold exploit with concrete in-domain counterexamples, pole/zero cancellation attacks, intermediate overflow hidden by cancellation, exact numerator/denominator cap boundaries, legitimate algebraic and clamp alternatives, malformed syntax, and expansion limits. It independently evaluates every reported intermediate bound on 486 combinations of box endpoints per audited expression. It also checks 905 bounded min/max expressions over three variables on all 27 small relative-value assignments, and fixed-seed polynomial identities over lattice atoms.

The broader operations stress harness supplies additional generated workflow instances, out-of-distribution witnesses, and public-reference checks. These tests validate concrete implementation behavior and can reveal defects. They are not a machine-checked proof of Python, `Fraction`, the AST parser, hashing, the whole evaluator, or every conceivable normalizer execution. The all-input guarantee comes from the stated sufficient proof rules and their correct implementation, subject to those trusted components and the explicit input contract.

The workflow signature advances to `v2` because acceptance now includes the symbolic and totality certificate. Behavioral pass rate remains in diagnostics; strict success and the outcome metric stay false for an uncertified submission even when all sampled cases pass. No model-performance or frontier-difficulty claim follows from this repair.
