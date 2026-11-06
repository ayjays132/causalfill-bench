"""Independent regression oracles for the controlled image and decision tracks."""
import unittest

from tools.stress_vision_audit_v05 import (
    Audit, all_small_trees, decision_enumeration, decision_forgery_checks,
    decoder_attacks, pixel_noise_and_calibration, raster_checks,
    replay_alias_checks, visual_scoring_boundaries, exhaustive_transfer_calibration,
    robot_integrity_checks, robot_common_action_checks,
)


class IndependentVisionAuditTests(unittest.TestCase):
    def verify_audit(self, operation):
        audit = Audit()
        operation(audit)
        self.assertEqual(audit.failures, [])

    def test_exact_fraction_pixel_oracle(self):
        self.verify_audit(lambda audit: raster_checks(audit, cases=12))

    def test_png_crc_stream_resource_and_metadata_attacks(self):
        self.verify_audit(decoder_attacks)

    def test_sensor_noise_occlusion_and_landmark_pathologies(self):
        self.verify_audit(lambda audit: pixel_noise_and_calibration(audit, cases=4))

    def test_fraction_centroids_under_subpixel_camera_calibration(self):
        self.verify_audit(lambda audit: exhaustive_transfer_calibration(audit, limit=8))

    def test_complete_small_policy_enumeration(self):
        self.assertEqual(len(all_small_trees()), 74)
        self.verify_audit(lambda audit: decision_enumeration(audit, table_limit=8))

    def test_noisy_decision_certificate_forgeries(self):
        self.verify_audit(decision_forgery_checks)

    def test_exact_replay_aggregation_for_billions_of_alias_paths(self):
        self.verify_audit(replay_alias_checks)

    def test_visual_scoring_boundaries_and_invalid_call_atomicity(self):
        self.verify_audit(visual_scoring_boundaries)

    def test_robot_oracle_purity_terminal_commit_and_invalid_atomicity(self):
        self.verify_audit(robot_integrity_checks)

    def test_robot_contact_conditioning_common_action_sets(self):
        self.verify_audit(robot_common_action_checks)


if __name__ == "__main__":
    unittest.main()
