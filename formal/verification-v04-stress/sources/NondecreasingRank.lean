import CausalFill.ReleaseAdaptiveMarket
set_option maxRecDepth 200000
set_option maxHeartbeats 0
open CausalFill.Information
open CausalFill.Exported.ReleaseAdaptiveMarket
def changed : FiniteArena 326 := { arena with
  nodes := arena.nodes.set arena.root.val
    { arena.nodes.get arena.root with rank := 0 } arena.root.isLt }
example : changed.checkUpper = true := by decide
