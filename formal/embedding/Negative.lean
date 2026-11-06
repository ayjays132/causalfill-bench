import Std

-- Deliberate negative control. This file must fail kernel elaboration.
theorem mustReject : False := by decide
