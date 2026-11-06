# Upstream notices for Lean proof dependencies

The NDJSON proof exports retain dependency declarations from the official Lean
4.35.0 toolchain and its bundled libraries. Those upstream portions retain their
upstream terms; the repository's MIT license applies to original CausalFill code
and assets.

The two notices here are copied unchanged from the official Linux release:

- [Lean license](Lean-4.35.0-LICENSE.txt)
- [Notices for libraries included in the toolchain](Lean-4.35.0-bundled-LICENSES.txt)

The complete official toolchain is installed separately. Its executables and
compiler caches are excluded from the CausalFill source archive. Including its
notices does not imply that every library listed there is included in the proof
export. Dependency-source attribution remains available in the pinned upstream
release at https://github.com/leanprover/lean4/tree/v4.35.0 .

The export metadata identifies Lean commit
`eb6cafb7290e8bd5f2937522d8d804f58f02bafc` and the exporter version. The release
verification records preserve the actual proof export and its dependency closure.
