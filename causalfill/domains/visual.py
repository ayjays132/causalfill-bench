"""Controlled image-only recovery with relational counting and executable routing.

The evaluator uses latent geometry to score; the public reference uses only a
PNG, a palette, and three known world landmarks.  This task is intentionally a
small raster family.  It is not a natural-image or learned-perception study.
"""
from __future__ import annotations

from copy import deepcopy
from fractions import Fraction
import json
import math

from ..types import Task, Verdict, fields, finite_number, strict_int
from ..vision import detect_components, pixel_to_world, recover_calibration, render_scene

VISUAL_VERSION = "visual_v1"
PALETTE = [(221,66,145),(39,180,194),(149,91,218),
           (220,73,49),(45,151,84),(231,174,42)]
LANDMARK_POINTS = [[8,8],[88,8],[8,88]]


def _rect(bounds, rgb):
    return {"shape":"rect","bounds":bounds,"rgb":rgb}


def _circle(point, radius, rgb):
    return {"shape":"circle","center":point,"radius":radius,"rgb":rgb}


def _make_camera(rng, split):
    # Every advertised transform keeps the entire fiducial/target support in frame.
    shear = rng.choice((-0.25,0.25)) if split == "transfer" else 0
    base = [[2,shear],[0,2]]
    if split == "train":
        orient = [[1,0],[0,1]]
    elif split == "dev":
        orient = rng.choice([[[1,0],[0,1]],[[-1,0],[0,1]],[[0,1],[-1,0]]])
    else:
        orient = rng.choice([[[0,-1],[1,0]],[[-1,0],[0,-1]],[[0,1],[1,0]],[[1,0],[0,-1]]])
    linear = [[sum(orient[i][k]*base[k][j] for k in range(2)) for j in range(2)] for i in range(2)]
    shift = [rng.randrange(-4,5),rng.randrange(-4,5)]
    if split == 'transfer':
        # Subpixel shifts expose centroid quantization rather than making all
        # calibrated poses exact by pixel-grid symmetry. Shared across twins.
        shift = [value+rng.choice((0.25,0.75)) for value in shift]
    matrix = [[linear[i][0],linear[i][1],120+shift[i]-48*sum(linear[i])] for i in range(2)]
    return {"width":240,"height":240,"matrix":matrix}


def solve_visual(public, call):
    """Task-aware scripted reference using only public JSON and PNG observations."""
    def use(name,args):
        response = call(name,args)
        if "error" in response:
            raise ValueError(response["error"])
        return response
    spec = json.loads(use("read_file",{"path":"/scene/visual.json"})["content"])
    image = use("capture",{"view":"inspection"})["image"]
    return recover_visual_from_image(spec,image)


def recover_visual_from_image(spec, image):
    """Recover a typed completion from a public contract and its image pixels."""
    tolerance = spec["sensor"]["rgb_noise_bound"]
    matrix = recover_calibration(image,spec["landmarks"],tolerance=tolerance)
    target = detect_components(image,spec["palette"]["target"],tolerance=tolerance,min_pixels=8)
    if len(target) != 1:
        raise ValueError("one fully visible target is required")
    position = pixel_to_world(matrix,target[0]["center"])
    tokens = detect_components(image,spec["palette"]["token"],tolerance=tolerance,min_pixels=8)
    points = [pixel_to_world(matrix,value["center"]) for value in tokens]
    # The generated family guarantees a 4-world-unit relation margin; apparent
    # ties are treated as insufficient evidence instead of silently guessed.
    margin = spec["relation_minimum_margin_world"]
    if any(abs(point[0]-position[0]) < margin/2 for point in points):
        raise ValueError("relation is too close to the declared resolution margin")
    count = sum(point[0] < position[0] for point in points)
    dispatch = "WEST" if position[0] < spec["dispatch_divider_world_x"] else "EAST"
    return {"target_world":[round(value,6) for value in position],
            "tokens_left_of_target":count,"dispatch":dispatch}


class VisualTask(Task):
    family = "visual"

    def __init__(self, seed:int, split:str="dev", difficulty:int=2, twin:int=0):
        super().__init__(seed,split,difficulty,twin)
        self.twin_kind = "target_horizontal_translation"
        # Consume all shared random draws before applying the intervention.
        palette = [list(color) for color in PALETTE]
        if split == "transfer":
            self.rng.shuffle(palette)
        self._palette = {"fiducial_0":palette[0],"fiducial_1":palette[1],"fiducial_2":palette[2],
                         "target":palette[3],"token":palette[4],"distractor":palette[5]}
        self._camera = _make_camera(self.rng,split)
        self._noise = {1:2,2:4,3:6}[difficulty]
        self._noise_seed = self.rng.randrange(2**63)
        self._base_side = self.rng.randrange(2)
        target_y = self.rng.choice([44,48,52])
        # Every target has a token on both sides plus at least one between the
        # intervention positions, so the relational count changes in each pair.
        choices = [[20,28],[44,28],[76,28],[36,68],[60,68],[72,68]]
        self.rng.shuffle(choices)
        required = [[20,28],[44,28],[76,28]]
        optional = [point for point in choices if point not in required]
        self._tokens = required + optional[:difficulty-1]
        self._distractors = [[24,76],[72,20]][:1+(difficulty>1)]
        x = [28,68][self._base_side ^ twin]
        self._target = [x,target_y]
        self._landmarks = [{"world":point,"rgb":palette[i]} for i,point in enumerate(LANDMARK_POINTS)]
        self._images = {}
        structure = {"train":"clear-translated-camera","dev":"occluded-rotated-camera", "transfer":"occluded-shear-palette-permutation"}[split]
        self.structural_signature = f"visual:{structure}:{VISUAL_VERSION}"
        self.budget = 12
        self.max_calls = 16
        self.prompt = (
            "Recover missing visual components from actual RGB PNG observations. Use the advertised "
            "color legend and three world landmarks to calibrate the camera. Report the target's world "
            "position, count token objects strictly to its west (smaller world x), and complete the "
            "dispatch rule. Image-left may differ from world-west. Some overview images contain an "
            "opaque inspection shutter; the inspection view exposes the scene. A color label is a "
            "public convention, not an embedded object annotation. Read /scene/visual.json."
        )
        self.slots = {
            "target_world":{"type":"array[number,number]","description":"Target center in world x,y; each coordinate within the declared 0.6 world-unit tolerance."},
            "tokens_left_of_target":{"type":"integer","description":"Count token-color objects with world x strictly less than target world x."},
            "dispatch":{"type":"enum[WEST,EAST]","description":"WEST iff target world x < 48; EAST otherwise."},
        }
        self.tools = {
            "capture":{"description":"Return a PNG-only image envelope from the named view; a fixed-pattern noise realization repeats exactly. The inspection view uncovers the shutter; this is a declared 2D mask change.",
                       "arguments":{"view":"overview or inspection"},"cost":3},
        }
        spec = {
            "version":VISUAL_VERSION,"world_bounds":[[0,0],[96,96]],
            "landmarks":deepcopy(self._landmarks),
            "palette":{key:deepcopy(self._palette[key]) for key in ("target","token","distractor")},
            "sensor":{"encoding":"PNG RGB8 noninterlaced","width":240,"height":240,
                      "rgb_noise_bound":self._noise,"noise_model":"fixed-pattern additive integer per-channel noise in [-bound,+bound], clipped to [0,255]; independent of the target intervention",
                      "camera_model":"unknown invertible affine, including subpixel translation in transfer; recover from three visible landmarks",
                      "landmark_radius_world":2.5,"object_center_tolerance_world":0.6},
            "views":{"overview":"opaque shutter in dev/transfer; clear in train",
                     "inspection":"same camera, palette and noise; shutter absent"},
            "dispatch_divider_world_x":48,"relation_minimum_margin_world":4,
            "target_count":1,"token_count_range":[3,5],"task_domain":"controlled 2D raster scenes",
            "interpretation":"Return world-relative geometry, not screen-relative geometry. All inspection objects and landmarks are fully visible, separated, and in frame.",
        }
        self.files = {"/scene/visual.json":json.dumps(spec,separators=(",",":")),
                      "/docs/visual.txt":(
                          "The PNG carries no object coordinates, segmentation labels, seed, depth, camera transform, or answer. "
                          "All colors and three landmark world points are in the public contract. Noise is bounded and fixed "
                          "per view pair; repeated captures provide no independent noise samples. Landmarks are single opaque "
                          "discs and object colors do not overlap the landmark colors. The unknown camera can reflect, rotate, "
                          "translate and (in transfer) shear the scene. Calibrate before interpreting world-west. The target "
                          "has at least four world units of horizontal separation from every token. The evaluator checks all "
                          "three requested fields independently against its latent scene and dispatch semantics. Merely "
                          "routing correctly without recovering the position and count does not satisfy this recovery track. "
                          "The paired intervention changes only target x. This is a small generated perception/control "
                          "exercise, not a benchmark of general natural-image understanding.")}

    def scene_shapes(self, view="inspection"):
        """Evaluator-only renderer input, used by image QA export, never a tool."""
        if view not in ("overview","inspection"):
            raise ValueError("unknown view")
        shapes = [_rect([2,2,94,94],[210,220,231]),_rect([3,3,93,93],[241,244,248])]
        # A sparse table grid is purely decorative and never carries a label.
        for location in (16,32,48,64,80):
            shapes.append(_rect([location-0.18,4,location+0.18,92],[222,229,237]))
            shapes.append(_rect([4,location-0.18,92,location+0.18],[222,229,237]))
        for landmark in self._landmarks:
            shapes.append(_circle(landmark["world"],3.4,[255,255,255]))
            shapes.append(_circle(landmark["world"],2.5,landmark["rgb"]))
        for point in self._tokens:
            shapes.append(_circle(point,3.3,[255,255,255]))
            shapes.append(_circle(point,2.5,self._palette["token"]))
        for x,y in self._distractors:
            shapes.append(_rect([x-3,y-3,x+3,y+3],self._palette["distractor"]))
        shapes.append(_circle(self._target,4.4,[255,255,255]))
        shapes.append(_circle(self._target,3.5,self._palette["target"]))
        if view == "overview" and self.split != "train":
            # This covers the complete target support in both worlds.  It is
            # drawn after the target and independent of its hidden position.
            shapes.append(_rect([16,38,80,58],[70,82,101]))
            shapes.append(_rect([17,39,79,40],[99,115,134]))
            shapes.append(_rect([17,56,79,57],[48,61,81]))
        return shapes

    def image(self, view="inspection"):
        """Evaluator-side cached rendering; returns a defensive public envelope."""
        if type(view) is not str or view not in ("overview","inspection"):
            raise ValueError("unknown view")
        if view not in self._images:
            self._images[view] = render_scene(self.scene_shapes(view),self._camera,
                                             noise=self._noise,noise_seed=self._noise_seed)
        return deepcopy(self._images[view])

    def query(self,name,args):
        if name != "capture":
            raise ValueError("unknown visual tool")
        fields(args,{"view"})
        view = args["view"]
        if type(view) is not str or view not in ("overview","inspection"):
            raise ValueError("view must be overview or inspection")
        return {"view":view,"image":self.image(view)}

    def evaluate(self,fill):
        try:
            fields(fill,{"target_world","tokens_left_of_target","dispatch"})
            target = fill["target_world"]
            if type(target) is not list or len(target) != 2:
                raise ValueError("target_world must contain two finite numbers")
            coordinates = [finite_number(value,0,96,"world coordinate") for value in target]
            count = strict_int(fill["tokens_left_of_target"],0,20,"token count")
            dispatch = fill["dispatch"]
            if type(dispatch) is not str or dispatch not in ("WEST","EAST"):
                raise ValueError("dispatch must be WEST or EAST")
            # Exact represented-decimal comparisons avoid epsilon at the
            # published acceptance boundary; the scorer does not call the
            # pixel detector or calibration reference.
            errors = [abs(Fraction(str(value))-Fraction(truth)) for value,truth in zip(coordinates,self._target)]
            pose_correct = all(value <= Fraction(3,5) for value in errors)
            expected_count = sum(point[0] < self._target[0] for point in self._tokens)
            count_correct = count == expected_count
            expected_dispatch = "WEST" if self._target[0] < 48 else "EAST"
            dispatch_correct = dispatch == expected_dispatch
            success = pose_correct and count_correct and dispatch_correct
            return Verdict(success,(pose_correct+count_correct)/2,float(dispatch_correct),1.0,{
                "pose_correct":pose_correct,"count_correct":count_correct,"dispatch_correct":dispatch_correct,
                "maximum_position_error_world":float(max(errors)),
                "renderer_version":VISUAL_VERSION,"perception_scope":"controlled 2D RGB pixels with known palette and landmarks",
                "success_requires":"pose plus relational count plus executable dispatch",
            })
        except (ValueError,TypeError,KeyError,OverflowError) as exc:
            return Verdict(False,details={"invalid_fill":str(exc)[:240]})

    def reference_answer(self):
        """Evaluator oracle used only to test scoring; not model performance."""
        return {"target_world":deepcopy(self._target),
                "tokens_left_of_target":sum(point[0] < self._target[0] for point in self._tokens),
                "dispatch":"WEST" if self._target[0] < 48 else "EAST"}

    def reference_actions(self):
        return [("capture",{"view":"inspection"})]
