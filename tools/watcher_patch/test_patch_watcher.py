"""Static and simulated-control-flow tests; these do not run Emby or the DLL."""

import json
from pathlib import Path
import tempfile
import unittest

import dnfile
from dncil.cil.body.reader import read_method_body_from_bytes

from patch_watcher import (
    ARGUMENT_READ_OFFSETS,
    EXPECTED_BODY,
    PatchError,
    SOURCE_SHA256,
    create_artifact,
    locate_configure,
    patch_bytes,
    sha256,
)

ROOT = Path(__file__).resolve().parents[2]


def decode_configure(data):
    pe = dnfile.dnPE(data=data)
    try:
        offset = pe.get_offset_from_rva(locate_configure(pe).Rva)
        return offset, read_method_body_from_bytes(data[offset:])
    finally:
        pe.close()


def simulate_configure(body, *, enabled_argument, disposed):
    """Interpret only this tiny method, recording rather than executing calls.

This independently checks the disposed branch, field assignment, and argument
passed to RebuildWatchers. It is not a substitute for testing in Emby.
"""
    state = {0x04000267: disposed, 0x04000266: True}
    args = [state, enabled_argument, 60]
    calls = []
    instructions = {i.offset: i for i in body.instructions}
    offsets = [i.offset for i in body.instructions]
    next_offsets = dict(zip(offsets, offsets[1:]))
    stack = []
    locals_ = {}
    pc = offsets[0]
    for _ in range(100):
        instruction = instructions[pc]
        op = instruction.opcode.name
        if op in ("nop", "volatile."):
            pass
        elif op in ("ldarg.0", "ldarg.1"):
            stack.append(args[int(op[-1])])
        elif op == "ldc.i4.0":
            stack.append(False)
        elif op == "ldfld":
            stack.append(stack.pop()[instruction.operand.value])
        elif op == "stfld":
            value = stack.pop()
            stack.pop()[instruction.operand.value] = value
        elif op == "stloc.0":
            locals_[0] = stack.pop()
        elif op == "ldloc.0":
            stack.append(locals_[0])
        elif op == "brfalse.s":
            if not stack.pop():
                pc = instruction.operand
                continue
        elif op == "br.s":
            pc = instruction.operand
            continue
        elif op == "call":
            if instruction.operand.value != 0x060002A8:
                raise AssertionError("Unexpected callee")
            enabled = stack.pop()
            if stack.pop() is not state:
                raise AssertionError("Unexpected receiver")
            calls.append(enabled)
        elif op == "ret":
            if stack:
                raise AssertionError("Unbalanced evaluation stack")
            return state[0x04000266], calls
        else:
            raise AssertionError(f"Unexpected instruction: {op}")
        pc = next_offsets[pc]
    raise AssertionError("Method did not return")


class WatcherPatchTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = (ROOT / "StrmAssistant.dll").read_bytes()
        cls.patched, cls.manifest = patch_bytes(cls.source)
        cls.offset, cls.original_body = decode_configure(cls.source)
        _, cls.patched_body = decode_configure(cls.patched)

    def test_original_is_the_supported_binary(self):
        self.assertEqual(sha256(self.source), SOURCE_SHA256)
        self.assertEqual(self.original_body.raw_bytes, EXPECTED_BODY)

    def test_only_two_bytes_change_in_entire_dll(self):
        self.assertEqual(len(self.source), len(self.patched))
        differences = [i for i, (a, b) in enumerate(zip(self.source, self.patched)) if a != b]
        self.assertEqual(differences, [self.offset + i for i in ARGUMENT_READ_OFFSETS])
        for i in differences:
            self.assertEqual(self.source[i], 0x03)  # ldarg.1
            self.assertEqual(self.patched[i], 0x16)  # ldc.i4.0

    def test_method_header_branches_and_all_other_instructions_unchanged(self):
        before, after = self.original_body, self.patched_body
        self.assertEqual(before.header_size, after.header_size)
        self.assertEqual(before.raw_bytes[:before.header_size], after.raw_bytes[:after.header_size])
        self.assertEqual(len(before.instructions), len(after.instructions))
        self.assertEqual(before.exception_handlers, after.exception_handlers)
        for old, new in zip(before.instructions, after.instructions):
            self.assertEqual(old.offset, new.offset)
            if old.offset in ARGUMENT_READ_OFFSETS:
                self.assertEqual(new.opcode.name, "ldc.i4.0")
            else:
                self.assertEqual(old.get_bytes(), new.get_bytes())

    def test_original_control_flow_uses_caller_setting(self):
        for enabled in (False, True):
            with self.subTest(enabled=enabled):
                self.assertEqual(
                    simulate_configure(self.original_body, enabled_argument=enabled, disposed=False),
                    (enabled, [enabled]),
                )

    def test_patch_disables_watcher_for_both_caller_settings(self):
        for enabled in (False, True):
            with self.subTest(enabled=enabled):
                self.assertEqual(
                    simulate_configure(self.patched_body, enabled_argument=enabled, disposed=False),
                    (False, [False]),
                )

    def test_disposed_guard_still_returns_without_mutation_or_rebuild(self):
        for body in (self.original_body, self.patched_body):
            for enabled in (False, True):
                self.assertEqual(
                    simulate_configure(body, enabled_argument=enabled, disposed=True), (True, [])
                )

    def test_rejects_unknown_corrupt_or_already_patched_input(self):
        for data in (b"", b"not a DLL", self.source[:-1], self.patched):
            with self.subTest(size=len(data)):
                with self.assertRaises(PatchError):
                    patch_bytes(data)

    def test_reproducible_patch_and_manifest(self):
        patched, manifest = patch_bytes(self.source)
        self.assertEqual(patched, self.patched)
        self.assertEqual(manifest, self.manifest)
        self.assertEqual(manifest["patched_sha256"], sha256(self.patched))
        self.assertFalse(manifest["runtime_tested_on_emby"])

    def test_artifact_preserves_input_and_includes_checksums_and_instructions(self):
        with tempfile.TemporaryDirectory() as directory:
            directory = Path(directory)
            source_path = directory / "original.dll"
            source_path.write_bytes(self.source)
            path, manifest = create_artifact(source_path, directory / "artifact")
            self.assertEqual(source_path.read_bytes(), self.source)
            self.assertEqual(path.read_bytes(), self.patched)
            output = path.parent
            self.assertEqual(json.loads((output / "patch-manifest.json").read_text()), manifest)
            self.assertEqual(
                (output / "SHA256SUMS").read_text(), f"{sha256(self.patched)}  StrmAssistant.dll\n"
            )
            self.assertIn("扫描媒体库", (output / "INSTALL.md").read_text(encoding="utf-8"))
            with self.assertRaises(PatchError):
                create_artifact(source_path, output)

    def test_refuses_to_overwrite_input(self):
        with tempfile.TemporaryDirectory() as directory:
            source_path = Path(directory) / "StrmAssistant.dll"
            source_path.write_bytes(self.source)
            with self.assertRaises(PatchError):
                create_artifact(source_path, source_path.parent)
            self.assertEqual(source_path.read_bytes(), self.source)

    def test_bad_input_produces_no_artifact(self):
        with tempfile.TemporaryDirectory() as directory:
            directory = Path(directory)
            source_path = directory / "invalid.dll"
            source_path.write_bytes(b"invalid")
            output = directory / "artifact"
            with self.assertRaises(PatchError):
                create_artifact(source_path, output)
            self.assertFalse(output.exists())


if __name__ == "__main__":
    unittest.main()
