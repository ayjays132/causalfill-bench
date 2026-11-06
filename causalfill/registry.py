"""Evaluator-only registry; public clients must not import this module."""
from .domains.words import WordsTask, AmbiguousWordsTask
from .domains.workflow import WorkflowTask
from .domains.grid import GridTask
from .domains.vending import VendingTask
from .domains.vending_adaptive import VendingAdaptiveTask
from .domains.robotics import RoboticsTask
from .domains.robotics_barrier import RoboticsBarrierTask
from .domains.latent import LatentTask
from .domains.visual import VisualTask
from .domains.robotics_vision import RoboticsVisionTask
from .domains.robust_sensing import RobustSensingTask

def factories():
    from .domains.latent import SparseLatentTask
    from .domains.proof import ProofTask
    from .domains.diagnosis import DiagnosisTask
    return {"words":WordsTask,"workflow":WorkflowTask,"grid":GridTask,"vending":VendingTask,
            "vending_adaptive":VendingAdaptiveTask,
            "robotics":RoboticsTask,"robotics_barrier":RoboticsBarrierTask,"latent":LatentTask,"latent_sparse":SparseLatentTask,
            "ambiguity":AmbiguousWordsTask,"proof":ProofTask,"diagnosis":DiagnosisTask,
            "visual":VisualTask,"robotics_vision":RoboticsVisionTask,
            "robust_sensing":RobustSensingTask}

def make_task(kind,seed=0,split="dev",difficulty=2,twin=0,mask_strategy="causal"):
    table=factories()
    if kind not in table: raise ValueError(f"unknown family: {kind}")
    if kind=="words": return WordsTask(seed,split,difficulty,twin,strategy=mask_strategy)
    return table[kind](seed,split,difficulty,twin)

