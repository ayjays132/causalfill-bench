"""Rebuild the human-readable research brief; needs reportlab (not a core dependency)."""
from pathlib import Path
from xml.sax.saxutils import escape
import json
import sys

from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak, Flowable
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
import reportlab

# Embed the redistributable fonts supplied with reportlab so that PDF readers
# do not substitute a metrically incompatible base-14 font.
FONTDIR=Path(reportlab.__file__).parent/'fonts'
for name,filename in [('CFBSans','Vera.ttf'),('CFBSans-Bold','VeraBd.ttf'),
                      ('CFBSans-Italic','VeraIt.ttf'),('CFBSans-BoldItalic','VeraBI.ttf')]:
    pdfmetrics.registerFont(TTFont(name,str(FONTDIR/filename)))
pdfmetrics.registerFontFamily('CFBSans',normal='CFBSans',bold='CFBSans-Bold',
                              italic='CFBSans-Italic',boldItalic='CFBSans-BoldItalic')
MONO='Courier'
mono_path=Path('/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf')
if mono_path.exists():
    pdfmetrics.registerFont(TTFont('CFBMono',str(mono_path)))
    MONO='CFBMono'

ROOT=Path(__file__).resolve().parents[1]
DEST=Path(sys.argv[1]) if len(sys.argv)>1 else ROOT/'reports/CausalFill_Research_Brief.pdf'
DEST.parent.mkdir(parents=True,exist_ok=True)
VER=json.loads((ROOT/'reports/build-verification-v0.2.json').read_text())
NAVY=colors.HexColor('#10263B')
TEAL=colors.HexColor('#007F7A')
PALE=colors.HexColor('#EAF5F3')
GRAY=colors.HexColor('#516170')
LINE=colors.HexColor('#D7E0E6')
W,H=A4

styles=getSampleStyleSheet()
styles.add(ParagraphStyle(name='TitleCF',fontName='CFBSans-Bold',fontSize=31,leading=35,textColor=NAVY,spaceAfter=14))
styles.add(ParagraphStyle(name='SubCF',fontName='CFBSans',fontSize=15,leading=21,textColor=GRAY,spaceAfter=18))
styles.add(ParagraphStyle(name='SectionCF',fontName='CFBSans-Bold',fontSize=21,leading=26,textColor=NAVY,spaceAfter=14))
styles.add(ParagraphStyle(name='HCF',fontName='CFBSans-Bold',fontSize=12,leading=16,textColor=TEAL,spaceBefore=12,spaceAfter=6))
styles.add(ParagraphStyle(name='BodyCF',fontName='CFBSans',fontSize=10.2,leading=14.8,textColor=NAVY,spaceAfter=9))
styles.add(ParagraphStyle(name='SmallCF',fontName='CFBSans',fontSize=8.6,leading=12,textColor=GRAY,spaceAfter=7))
styles.add(ParagraphStyle(name='TableCF',fontName='CFBSans',fontSize=9,leading=12,textColor=NAVY))
styles.add(ParagraphStyle(name='TableHeadCF',fontName='CFBSans-Bold',fontSize=9,leading=12,textColor=colors.white))
styles.add(ParagraphStyle(name='CodeCF',fontName=MONO,fontSize=8.6,leading=12,textColor=NAVY,backColor=PALE,borderPadding=10,spaceBefore=5,spaceAfter=10))

story=[]
def p(text,style='BodyCF'):story.append(Paragraph(text,styles[style]))
def h(text):p(text,'HCF')
def page(title,kicker):
    if story:story.append(PageBreak())
    p(kicker.upper(),'SmallCF');p(title,'SectionCF')
def table(headers,rows,widths):
    data=[[Paragraph(escape(str(x)),styles['TableHeadCF']) for x in headers]]
    for row in rows:data.append([Paragraph(str(x),styles['TableCF']) for x in row])
    t=Table(data,colWidths=widths,repeatRows=1,hAlign='LEFT')
    t.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),NAVY),('VALIGN',(0,0),(-1,-1),'TOP'),
        ('LEFTPADDING',(0,0),(-1,-1),9),('RIGHTPADDING',(0,0),(-1,-1),9),
        ('TOPPADDING',(0,0),(-1,-1),8),('BOTTOMPADDING',(0,0),(-1,-1),8),
        ('ROWBACKGROUNDS',(0,1),(-1,-1),[colors.white,PALE]),
        ('LINEBELOW',(0,0),(-1,0),0.5,NAVY),('LINEBELOW',(0,1),(-1,-1),0.4,LINE)]))
    story.append(t);story.append(Spacer(1,10))

class Process(Flowable):
    def __init__(self):Flowable.__init__(self);self.width=495;self.height=124
    def draw(self):
        c=self.canv
        boxes=[(0,70,'1. Missing component'),(173,70,'2. Choose evidence'),(346,70,'3. Recover + act'),
               (0,2,'6. Report each metric'),(173,2,'5. Verify consequence'),(346,2,'4. Change condition')]
        for x,y,t in boxes:
            c.setFillColor(PALE);c.setStrokeColor(LINE);c.roundRect(x,y,149,45,6,stroke=1,fill=1)
            c.setFillColor(NAVY);c.setFont('CFBSans-Bold',9);c.drawCentredString(x+74.5,y+19,t)
        c.setStrokeColor(TEAL);c.setLineWidth(1.5)
        for x,y,dx,dy in [(150,92,20,0),(323,92,20,0),(420,68,0,-18),(343,24,-17,0),(170,24,-17,0)]:
            c.line(x,y,x+dx,y+dy)
            if dx>0:c.line(x+dx,y,x+dx-4,y+3);c.line(x+dx,y,x+dx-4,y-3)
            elif dx<0:c.line(x+dx,y,x+dx+4,y+3);c.line(x+dx,y,x+dx+4,y-3)
            else:c.line(x,y+dy,x-3,y+dy+4);c.line(x,y+dy,x+3,y+dy+4)

page('CausalFill-Bench','Research prototype | v0.2.0 | November 1, 2026')
p('Recover what is missing.<br/>Choose the evidence.<br/>Make the procedure work.','TitleCF')
p('A working benchmark for missing components, deliberate experiments and independently checkable completions.','SubCF')
table(['Implementation checks','Development controls','State space'],[
    [f"<b>{VER['unit_and_integration_tests']['passed']} tests passed</b><br/>Includes real loopback HTTP tests.",
     '<b>2,700 episodes</b><br/>Three scripted policies on the same 900 paired cases.',
     '<b>Up to 100 variables</b><br/>Sparse track has nine total tool-cost units.']],[165,165,165])
h('What this release establishes')
p('The source implements ten task configurations, budgeted public tools, typed submissions, behavioral verifiers, proof certificates and reproducible reports. A public-tool reference solved all 810 answerable development cases and correctly abstained on all 90 ambiguity controls. The formal extension checks proof validity and exact finite experiment bounds.')
h('What it does not establish')
p('The benchmark is not yet demonstrated to be frontier-hard or scientifically novel. Exploratory assistant trials passed the sampled sparse, robotics and proof tasks. Their isolation and provenance limitations exclude a clean leaderboard claim. The certificates are checked in Python; no Lean verification, real-robot transfer or new mathematical theorem is claimed.')
p('<b>Project concept and direction:</b> Phillip A. Holland Jr.<br/><b>Implementation and research synthesis:</b> AI-assisted.<br/><b>Distribution:</b> original MIT-licensed source; no third-party benchmark tasks or model weights bundled.','SmallCF')

page('The research question','01 | Test a mechanism, then its consequences')
p('<b>Can an agent identify a missing causal component, obtain enough evidence to recover it, and restore correct behavior within a declared budget?</b> A missing word becomes useful when the completed word controls an executable decision. Missing state becomes useful when a subsequent action depends on it.')
story.append(Process());story.append(Spacer(1,12))
h('A concrete example')
p('A procurement skill has lost its transit rule and shipping fees. The agent can obtain itemized quotes, compare weekday and weekend delivery promises, reconstruct the coefficients, then actually order and sell goods through the simulated horizon. Correct words without a working business do not pass.')
h('The unit of evaluation')
p('Each episode has an environment, a partially specified procedure, a set of permitted observations and actions, a budget, and a separate verifier. The agent returns a typed completion and, when required, produces a trajectory. The final grade checks the stated property rather than similarity to one original string.')
h('Uncertainty is part of the contract')
p('Some controls deliberately have two incompatible hidden route names that produce exactly the same permitted observations. Correct behavior is to acknowledge that the literal cannot be identified. These controls measure abstention separately and never add to capability success.')
h('Masks are constrained')
p('A dependency-graph planner ranks missing components by downstream influence while respecting declared evidence costs. It rejects masks without a declared recovery path. The ranking is a design proxy, not a learned measure of model difficulty. Domain tests and constructive public-tool solutions are still required.')
p('The current automatic causal/random mask comparison applies to word tasks. Other domains have explicit fixed gaps. Matched declared slot count is not exact model-token matching.','SmallCF')

page('What the agent can do','02 | Eight content domains, ten configurations')
table(['Task','Missing component','Evidence and final check'],[
    ['Words','Routing literals and conditions','Choose Boolean inputs; verify every possible input.'],
    ['Workflow','An arithmetic return expression','Read current rules and test examples; check new arguments, boundaries and runtime scale.'],
    ['Grid','A short transform program','Observe examples and chosen experiments; verify a typed DSL on new grids.'],
    ['Vending','Five procurement rules','Operate purchases, deliveries, stock, prices and cash through 16-24 simulated days.'],
    ['Robotics','Position, path and handling rule','Calibrate symbolic views, sense obstacles, verify geometry and force constraints.'],
    ['Latent control','An affine operator','Probe 8, 32 or 100 variables; verify exact affine equivalence.'],
    ['Sparse latent','The operator with scarce observations','Nine cost units; recover a sparse map and verify all basis cases plus interventions.'],
    ['Ambiguity','An unobservable route name','Observation-equivalent worlds; assess justified abstention separately.'],
    ['Proof','A missing derivation and consistency witness','Bind a fixed theorem; check every resolution inference and a satisfying model.'],
    ['Diagnosis','The true world and elimination evidence','Choose experiments under a certified optimal budget; rule out every competitor.'],
],[82,130,283])
h('Tool and grading boundaries')
p('The interface is a virtual computer workspace with typed tools. Robotics observations are numerical. Candidate code uses a small whitelist language. Acceptance closes an episode and returns no grade to the agent.')
h('Equivalent solutions count')
p('Equivalent safe paths and expressions can pass. Affine, proof and diagnosis certificates establish their declared finite properties. Workflow and grid use finite behavioral suites. Latent/sparse and words/ambiguity are paired configurations of two domains.')

page('A real meaning for 100D','03 | Sparse identification, with explicit information accounting')
p('The mathematical task represents 100 coupled state variables over the finite field GF(101). It is not a scene with 100 physical spatial directions. In the transfer setting each output row has at most two nonzero input coefficients plus an offset.')
p('y[i] = b[i] + a[i] * x[j] + c[i] * x[k]  (mod 101)','CodeCF')
h('The control and the scarce-observation track')
p('The control can recover an arbitrary affine map with a zero probe followed by every standard-basis probe. In 100D that takes 101 interventions. The sparse track grants nine total cost units, so that approach cannot fit. The public problem gives the sparsity constraint without the reference derivation.')
h('A constructive five-probe reference')
p('Observe the zero vector to identify offsets. Probe coordinate values 1, j, j squared and j cubed. After subtracting offsets, each output row supplies four moments. A two-term recurrence identifies the two coordinate indices and their coefficients. The implementation also handles coefficient cancellation and zero-coordinate edge cases.')
p('D = m0*m2 - m1*m1<br/>s = (m0*m3 - m1*m2) / D<br/>p = (m1*m3 - m2*m2) / D<br/>Find roots of t*t - s*t + p, all modulo 101.','CodeCF')
p('These are classical sparse-interpolation / Prony-style ideas, not a new theorem [8]. Five 100-element outputs contain 500 field values. The gain is in structured intervention efficiency, not the impossible recovery of hundreds of unknowns from five scalar readings.')
h('Independent verification')
p('The submitted sparse matrix is checked against an independently generated affine construction at zero and every basis vector. Equality there establishes equality for every input under the affine contract. Twelve dense interventions provide an additional implementation check. The reference succeeds using six total cost units including one document read.')
p('The exploratory assistant used six probes and passed. This case therefore provides a solvable structured challenge, not evidence that current strong models cannot solve it.','SmallCF')

page('A completed answer must carry a proof','04 | Fixed assumptions, checked inferences, non-vacuity')
p('The proof track turns the request for "axiom level" rigor into a precise contract. The agent receives an immutable finite propositional statement: premises F, a signed goal g, and a SHA-256 commitment. It must produce two independently checked artifacts.')
table(['Obligation','What the checker establishes'],[
    ['Resolution certificate','Every step follows from earlier clauses of F plus NOT g. The final clause is empty, so F entails g.'],
    ['Consistency witness','A complete Boolean assignment satisfies the original F. The proof cannot win merely because its assumptions contradict each other.'],
    ['Statement commitment','Premises, variable count, ordering and signed goal match the trusted evaluator statement. The solver cannot substitute an easier theorem.'],
],[145,350])
h('The trusted rule is small')
p('From (A OR p) and (B OR NOT p), derive (A OR B). The checker computes this resolvent itself. It accepts only earlier parent indices and a valid pivot; the solver supplies no new axioms or claimed clauses. Induction over the derivation establishes that every derived clause follows from the original inputs.')
h('A concrete verified result')
p('A fresh exploratory solver produced an 865-step proof for a 43-variable statement with 238 premises, plus a valid consistency model. The scripted search produced 6,073 steps for that same statement. Both passed. A shorter certificate is useful here, but this one instance does not establish model superiority or frontier difficulty.')
h('Check the artifact independently')
p('python -m causalfill.verify_proof statement.json fill.json<br/>  --expected-sha256 TRUSTED_STATEMENT_HASH','CodeCF')
p('Use the command on one line. Obtain the expected hash from the evaluator, not the claimant. The standalone checker imports no generator or proof-search module. The source package includes the actual statement, fill, verification result and reproducible command.')
p('Axiom\'s checkable proof-artifact workflow is a relevant standard [9]; VERINA and miniF2F are close prior art [10, 11]. This implementation uses a bounded Python resolution kernel, not Lean/Mathlib, an open-conjecture proof, or a newly proposed logical foundation.','SmallCF')

page('Prove how much evidence is needed','05 | Exact adaptive identification in a finite world')
p('The diagnosis track supplies a complete table of candidate worlds and binary experiment outcomes, while hiding which world is current. The agent chooses experiments and must identify the true world within a mathematically certified worst-case query budget.')
p('D(S) = 0                         if |S| = 1<br/>D(S) = 1 + min_q max(D(S0), D(S1)) otherwise','CodeCF')
p('S is the set of worlds still compatible with observations. An informative experiment q partitions it into nonempty S0 and S1. Every branch becomes smaller. Checking the recurrence across every informative alternative proves an exact optimum: both an attainable upper bound and a matching lower bound.')
h('Why counting bits is not enough')
p('Thirty-two worlds require at least five binary answers in an unrestricted decision tree. But the permitted experiments may not supply the right partitions. The included constrained example has 32 worlds and ten experiments: its exact worst-case optimum is six queries, not five. Its certificate checks 1,448 version-space states. A separate strategy checker verifies a tree attaining six.')
h('A lucky guess does not pass')
p('The final completion identifies the world and gives an observed experiment that excludes each of the other 31 candidates. The evaluator checks these witnesses against the actual episode history. Correctly guessing a label without distinguishing evidence fails. This makes the answer accountable to information obtained within the budget.')
h('What the guarantee covers')
p('The result is exact for deterministic adaptive identification in the supplied finite noiseless table. It does not prove model computation is optimal, address unknown hypotheses or noisy sensors, or establish real-world causal identification. The mathematical recurrence and exact query-learning tradition are established prior art [12].')
h('Independent audit')
p('For all 154 distinct small tables formed from two to four different three-bit response vectors, an independent exhaustive enumeration of complete query policies matched the certified optimum. Missing states, false bounds, wrong leaf identities and malformed certificates are rejected. The release also includes a five-query example with 541 checked states.')
p('The proof-search and experiment-optimization procedures are untrusted producers. Their final certificates must pass separate checks. The remaining trust base includes the Python runtime, the checker implementations and the task specification.','SmallCF')

page('From recovered state to action','06 | Robotics and delayed operational effects')
h('Robotics: observe, calibrate, plan')
p('The target may be occluded in one camera. Three known fiducials allow recovery of each camera\'s two-dimensional affine transform. Complementary numerical views determine a three-dimensional target location. Lidar reports occupied boxes in world coordinates. The completed plan must reach the target, stay within bounds, avoid clearance-expanded obstacles and satisfy the material\'s force limit.')
p('This tests symbolic sensor fusion and geometric planning. It does not evaluate pixels, learned visual features, contact dynamics, a physical gripper or real-world safety. Existing masked-view and active-perception work is substantial and must be credited [5, 6].')
h('Vending: the consequence arrives later')
p('Orders spend money immediately, while stock becomes sellable only at delivery. Inventory expires, purchases consume capacity, prices change demand and daily fees continue. A completed procurement rule passes only when the agent also reaches the horizon, earns the cash target, serves enough demand and sells on enough distinct days.')
p('A review found that a purely price-dependent service ratio could be gamed by suppressing later demand. The implemented selling-day requirement closes that particular loophole. This simulator is original and much smaller than Vending-Bench\'s year-long setting [2].')
h('Counterfactual twins')
p('Operational twins alter one causal parameter, such as delivery delay or obstacle height. The formal tracks instead change theorem polarity or the current diagnostic world. Reports distinguish these three variation types. Both members must pass for paired success. A single plan valid in both is accepted. Separate twin episodes do not establish continuous online adaptation.')
h('A path to external validation')
p('A later robotics study could wrap LIBERO or RoboCasa, replace numeric projections with camera frames, introduce noise and dynamics, and test actual manipulation under held-out layouts. Improvements in perception, control or transfer would require separate training and controlled evaluation. This benchmark alone does not confer those capabilities.')

page('Measured results and integrity','07 | What was actually run')
table(['Scripted policy','Answerable success','Correct unanswerable abstention'],[
    ['Public-tool reference','810 / 810','90 / 90'],
    ['Blind empty completion','0 / 810','0 / 90'],
    ['Always abstain','0 / 810','90 / 90'],
],[170,155,170])
p('Each policy ran on the same 900 episodes: ten configurations, three structural splits, three difficulty levels, five seeds and two twins. All 2,700 recorded trace chains were consistent. The public-tool reference used no invalid calls. These are scripted implementation controls, not LLM scores.')
h('140 unit and integration tests passed')
p('Checks cover numerical and accounting invariants, geometry, ambiguity, leakage, grouped metrics, proof soundness, statement binding and exact query bounds. Eight tests exercise real loopback HTTP, including a 6,018-step, 102,511-byte proof submission.')
h('Exploratory assistant trial')
table(['Task','Evaluator grade','Tool cost'],[
    ['100D sparse transfer','Pass','6 / 9'],
    ['Symbolic robotics transfer','Pass','19 / 40'],
    ['Proof transfer: 865 checked steps','Pass','7 / 20'],
],[235,120,140])
p('The earlier sparse/robotics trial had context exposure: its coordinator saw sparse-method summaries before using a fresh solver context. The formal trial forbade collaboration and web tools and used a fresh context. All three grades passed, but shared-host isolation and incomplete model metadata exclude comparative leaderboard claims.')
h('Flaws caught before release')
p('Review fixed answer leakage through metadata, hardcoded constants passing weak code checks, a giant-integer exception, a service-ratio loophole and a parser limit rejecting legitimate large proofs. Regression checks preserve these fixes.')

page('Scoring, isolation and reproducibility','08 | Make success interpretable')
h('Keep the metric vector visible')
p('The headline is macro success over answerable task labels. Latent and sparse latent receive separate weights; an eight-domain macro needs an explicitly registered remapping. Correct impossible-case abstention never increases capability success. Reports retain outcomes, cost, calibration and paired success by variation type. Serialized byte counts are not billed tokens.')
h('Do not treat seeds as independent mechanisms')
p('Confidence intervals resample structural-signature clusters within each family. They are withheld when a headline family has too few clusters. Repeated seeds improve checks within a generator but do not establish generalization to new concepts. Perfect scripted-reference intervals do not imply universal reliability.')
h('An observation boundary is not an OS sandbox')
p('The authenticated HTTP service exposes only the public episode and permitted tools. It withholds grade/source/reset endpoints and arbitrary host-file access, bounds requests and accepts one final submission. For a credible model comparison, the evaluator still needs a separate isolated container or VM. The agent must not see its source, seeds, processes or private results.')
p('Trace hash chains allow consistency checks against a trusted final hash. An actor who can rewrite both trace and hash can forge a new chain. Preserve evaluator ownership or an external anchor. The optional Docker recipe has not been exercised in this release.')
h('Publish the experiment, not just a percentage')
p('Record source fingerprint, exact model and harness, prompt, sampling parameters, retries, context/skill conditions, token and tool usage, runtime limits, network policy, all permitted traces and excluded attempts. Separate reference results from real-model results. Publish observable evidence and final artifacts rather than demanding private chain-of-thought.')
h('Calibrate the missing-information claim')
p('A complete procedure, random omission, causal omission, static evidence and active evidence answer different questions. Match information and tokens when making a causal comparison. The shipped no-tools option is prompt-only, and the no-skill option removes only a generic guide; neither should be relabeled as a stronger experimental condition.')

page('Research grounding and next release','09 | Credit the ingredients; test the new combination')
refs=[
('1','ARC-AGI-3','https://arcprize.org/arc-agi/3','Interactive exploration and action-efficient reasoning.'),
('2','Vending-Bench 2','https://andonlabs.com/evals/vending-bench-2','Long-horizon operational consequences.'),
('3','HumanEval Infilling','https://github.com/openai/human-eval-infilling','Executable code infilling already exists.'),
('4','SkillsBench','https://github.com/benchflow-ai/skillsbench','Skill conditions and deterministic task verification.'),
('5','ESI-Bench','https://esi-bench.github.io/','Active perception-action evaluation.'),
('6','Multi-View Masked World Models','https://proceedings.mlr.press/v202/seo23a.html','Masked viewpoints for robotic representations.'),
('7','OpenAI math and GPT-Red','https://github.com/openai/math','Verification scope and adversarial research are inspirations; no model or Lean integration.'),
('8','Ben-Or and Tiwari, STOC 1988','https://doi.org/10.1145/62212.62241','Established sparse interpolation prior art.'),
('9','Axiom: Proof of Concept','https://axiommath.ai/research/proof-of-concept/','Independently checkable proof artifacts, with Lean verification.'),
('10','VERINA','https://github.com/sunblaze-ucb/verina','Joint evaluation of specifications, code and proofs.'),
('11','miniF2F','https://github.com/openai/miniF2F','Existing formal theorem-proving benchmark.'),
('12','Bshouty, ALT 2019','https://proceedings.mlr.press/v98/bshouty19a.html','Exact learning from queries and adaptive strategies.'),
]
for n,name,url,note in refs:
    p(f'<b>[{n}] <link href="{url}" color="#007F7A">{escape(name)}</link>.</b> {escape(note)}','SmallCF')
p('Additional official context: <link href="https://openai.com/index/building-scientific-understanding-with-academic-communities/" color="#007F7A">OpenAI scientific release, October 26, 2026</link>; <link href="https://openai.com/index/unlocking-self-improvement-gpt-red/" color="#007F7A">GPT-Red</link>; <link href="https://github.com/openai/plugins" color="#007F7A">OpenAI Plugins</link>. Sources were checked November 1, 2026.','SmallCF')
h('Clarifying the requested references')
p('OpenAI\'s math repository is a plausible match to the mathematics request; it labels its materials as raw research at varying verification stages. No official method named "100D red teaming" was verified. GPT-Red concerns adversarial robustness; 100-dimensional state recovery is a separate design choice here. No OpenAI mathematical claim is independently verified by this project.')
h('The next scientific milestone')
p('Freeze tasks and budgets; obtain independent checker and task review; run strong-model and human comparisons; add future private structural families; measure matched-information effects; and seek replication. A breakthrough claim needs evidence of capabilities or failures missed by prior benchmarks, not just more generated instances.')
h('Start locally')
p('python -m causalfill demo --family latent_sparse<br/>  --split transfer --difficulty 3<br/>python -m unittest discover -s tests -v','CodeCF')
p('Use the complete command on one line. On Windows, py may replace python. No GPU or third-party package is required for the benchmark core. The accompanying source package contains the full research specification, protocol, tests, traces, metrics and release gates.','SmallCF')

def decorate(canvas,doc):
    canvas.saveState()
    if doc.page>1:
        canvas.setStrokeColor(LINE);canvas.line(50,H-42,W-50,H-42)
        canvas.setFillColor(GRAY);canvas.setFont('CFBSans',8)
        canvas.drawString(50,H-32,'CAUSALFILL-BENCH  /  RESEARCH PROTOTYPE')
    canvas.setStrokeColor(LINE);canvas.line(50,43,W-50,43)
    canvas.setFillColor(GRAY);canvas.setFont('CFBSans',8)
    canvas.drawString(50,29,'v0.2.0  |  2026-11-01  |  Phillip A. Holland Jr.')
    canvas.drawRightString(W-50,29,str(doc.page))
    canvas.restoreState()

doc=SimpleDocTemplate(str(DEST),pagesize=A4,rightMargin=50,leftMargin=50,topMargin=58,bottomMargin=58,
    title='CausalFill-Bench: Research Brief and Verification',author='Phillip A. Holland Jr.; AI-assisted development')
doc.build(story,onFirstPage=decorate,onLaterPages=decorate)
print(DEST)
