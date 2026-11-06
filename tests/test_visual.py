"""Recovery is checked against geometry; public references receive pixels only."""
from copy import deepcopy
import json
import math
import unittest

from causalfill.domains.visual import VisualTask, recover_visual_from_image, solve_visual
from causalfill.session import Session


class VisualTaskTests(unittest.TestCase):
    def test_pixel_reference_solves_split_difficulty_twins(self):
        for split in ('train','dev','transfer'):
            for difficulty in (1,2,3):
                for twin in (0,1):
                    for seed in range(2):
                        task=VisualTask(seed,split,difficulty,twin)
                        session=Session(task)
                        fill=solve_visual(session.public(),session.call)
                        with self.subTest(split=split,difficulty=difficulty,twin=twin,seed=seed):
                            self.assertTrue(task.evaluate(fill).success)
                            self.assertEqual(session.cost,4)
                            self.assertEqual(session.invalid,0)

    def test_transfer_subpixel_calibration_has_measured_bounded_error(self):
        errors=[]
        for seed in range(4):
            task=VisualTask(seed,'transfer',3)
            self.assertTrue(all(row[2] % 1 in (0.25,0.75) for row in task._camera['matrix']))
            answer=recover_visual_from_image(json.loads(task.files['/scene/visual.json']),task.image())
            verdict=task.evaluate(answer)
            self.assertTrue(verdict.success)
            errors.append(verdict.details['maximum_position_error_world'])
        self.assertGreater(max(errors),0)
        self.assertLess(max(errors),0.6)

    def test_hidden_twins_preserve_complete_public_payload_and_overview(self):
        for split in ('dev','transfer'):
            for seed in range(3):
                first=VisualTask(seed,split,3,0)
                second=VisualTask(seed,split,3,1)
                self.assertEqual(first.public(),second.public())
                self.assertEqual(first.files,second.files)
                self.assertEqual(first.query('capture',{'view':'overview'}),second.query('capture',{'view':'overview'}))
                self.assertNotEqual(first.query('capture',{'view':'inspection'}),second.query('capture',{'view':'inspection'}))
                self.assertEqual(first._camera,second._camera)
                self.assertEqual(first._palette,second._palette)
                self.assertEqual(first._tokens,second._tokens)
                self.assertEqual(first._target[1],second._target[1])
                self.assertEqual(abs(first._target[0]-second._target[0]),40)
                self.assertNotEqual(first.reference_answer()['dispatch'],second.reference_answer()['dispatch'])
                self.assertNotEqual(first.reference_answer()['tokens_left_of_target'],second.reference_answer()['tokens_left_of_target'])
                self.assertFalse(second.evaluate(first.reference_answer()).success)

    def test_correct_dispatch_alone_does_not_pass_recovery(self):
        task=VisualTask(4)
        answer=task.reference_answer()
        answer['target_world'][0]=48
        verdict=task.evaluate(answer)
        self.assertFalse(verdict.success)
        self.assertEqual(verdict.outcome,1)
        self.assertFalse(verdict.details['pose_correct'])
        answer=task.reference_answer();answer['tokens_left_of_target']+=1
        self.assertFalse(task.evaluate(answer).success)

    def test_pose_tolerance_is_exact_at_and_beyond_both_boundaries(self):
        task=VisualTask(5)
        for axis in (0,1):
            for sign in (-1,1):
                answer=task.reference_answer()
                value=task._target[axis]+sign*0.6
                answer['target_world'][axis]=value
                self.assertTrue(task.evaluate(answer).success)
                answer['target_world'][axis]=math.nextafter(value,-math.inf if sign<0 else math.inf)
                self.assertFalse(task.evaluate(answer).success)

    def test_unobserved_overview_fails_closed_for_pixel_reference(self):
        task=VisualTask(11,'transfer',3)
        spec=json.loads(task.files['/scene/visual.json'])
        with self.assertRaises(ValueError):recover_visual_from_image(spec,task.image('overview'))

    def test_invalid_requests_are_atomic_and_payloads_are_defensive(self):
        task=VisualTask(2)
        before=deepcopy(task.__dict__)
        for name,args in [('capture',{}),('capture',{'view':True}),('capture',{'view':[]}),
                          ('capture',{'view':'oracle'}),('capture',{'view':'overview','seed':2}),('oracle',{})]:
            with self.assertRaises(ValueError):task.query(name,args)
            self.assertEqual(task._images,before['_images'])
            self.assertEqual(task._target,before['_target'])
        original=task.image(); altered=task.image();altered['sha256']='0'*64
        self.assertEqual(original,task.image())

    def test_fill_validation_rejects_bool_nonfinite_and_unknown_keys(self):
        task=VisualTask(9)
        for value in (True,math.nan,math.inf,'28',-1,97):
            answer=task.reference_answer();answer['target_world'][0]=value
            self.assertFalse(task.evaluate(answer).success)
        for key,value in [('tokens_left_of_target',True),('tokens_left_of_target',2.0),
                          ('dispatch',[]),('dispatch',True),('dispatch','east'),('secret',1)]:
            answer=task.reference_answer();answer[key]=value
            self.assertFalse(task.evaluate(answer).success)

    def test_public_contract_contains_no_target_or_camera_answer(self):
        task=VisualTask(17,'transfer',3)
        spec=json.loads(task.files['/scene/visual.json'])
        for key in ('target_world','camera_matrix','seed','world','tokens_left_of_target','answer'):
            self.assertNotIn(key,spec)
        self.assertNotIn('matrix',spec['sensor'])
        self.assertEqual(set(task.image()),{'mime_type','width','height','png_base64','sha256'})
        self.assertTrue(all(type(value) is str for value in task.files.values()))


if __name__=='__main__':unittest.main()
