#!/usr/bin/env python3
"""Reproducibly disable only the extra STRM watcher in the supplied plugin DLL.

This is a narrowly scoped binary patch, NOT a build of the Lite source tree.
Unknown binaries are rejected. No plugin or embedded native code is executed.
"""

import argparse
import hashlib
import json
from pathlib import Path

import dnfile
from dncil.cil.body.reader import read_method_body_from_bytes

SOURCE_SHA256 = "c1df8edc1f6539cb46c3b4122d2431b2651cc9239c7743ea463899a462016c79"
TARGET_TYPE = "StrmAssistant.Services.StrmFileWatcher"
TARGET_METHOD = "Configure"
# Instance void Configure(bool enabled, int refreshDelaySeconds).
EXPECTED_SIGNATURE = bytes.fromhex("2002010208")
# Includes the original fat method header. This additionally guards layout,
# branches, fields, method tokens, and the disposed check against drift.
EXPECTED_BODY = bytes.fromhex(
    "1330020022000000220000110002fe137b670200040a062c03002b11"
    "0203fe137d66020004020328a8020006002a"
)
# dncil offsets are relative to the method header, not to the first instruction.
ARGUMENT_READ_OFFSETS = (0x1D, 0x26)
LDARG_1 = 0x03
LDC_I4_0 = 0x16


class PatchError(ValueError):
    """The input or proposed patch did not pass a safety check."""


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def locate_configure(pe):
    """Find the target by managed metadata, never by a global byte search."""
    matches = [
        method.row
        for typedef in pe.net.mdtables.TypeDef.rows
        if f"{typedef.TypeNamespace}.{typedef.TypeName}" == TARGET_TYPE
        for method in typedef.MethodList
        if str(method.row.Name) == TARGET_METHOD
    ]
    if len(matches) != 1:
        raise PatchError("Expected exactly one StrmFileWatcher.Configure method.")
    method = matches[0]
    if method.Signature.value != EXPECTED_SIGNATURE or not method.Rva:
        raise PatchError("Unexpected Configure signature or missing IL body.")
    return method


def patch_bytes(source):
    """Return patched bytes and an auditable manifest, leaving input untouched."""
    if sha256(source) != SOURCE_SHA256:
        raise PatchError(
            "Unsupported input DLL. Expected the supplied StrmAssistant 1.0.0.40 "
            f"with SHA256 {SOURCE_SHA256}; got {sha256(source)}. "
            "Do not bypass this check for a different version."
        )

    pe = dnfile.dnPE(data=source)
    try:
        if pe.net is None:
            raise PatchError("Input is not a managed assembly.")
        if pe.net.struct.Flags & 0x08 or pe.net.struct.StrongNameSignatureSize:
            raise PatchError("Refusing to invalidate a strong-name signature.")
        if pe.OPTIONAL_HEADER.DATA_DIRECTORY[4].Size:
            raise PatchError("Refusing to invalidate an Authenticode signature.")
        method = locate_configure(pe)
        offset = pe.get_offset_from_rva(method.Rva)
        body = read_method_body_from_bytes(source[offset:])
        if body.raw_bytes != EXPECTED_BODY or body.exception_handlers:
            raise PatchError("Unexpected Configure method body/layout.")
        reads = [i for i in body.instructions if i.opcode.name == "ldarg.1"]
        if tuple(i.offset for i in reads) != ARGUMENT_READ_OFFSETS:
            raise PatchError("Unexpected enabled-argument usage.")

        patched = bytearray(source)
        edits = []
        for instruction in reads:
            file_offset = offset + instruction.offset
            if patched[file_offset] != LDARG_1:
                raise PatchError("Expected ldarg.1 at the patch site.")
            # Use false instead of the caller's enabled flag in BOTH places:
            # this.enabled = false; RebuildWatchers(false);
            # The original disposed guard and watcher cleanup remain intact.
            patched[file_offset] = LDC_I4_0
            edits.append({
                "file_offset": file_offset,
                "method_offset": instruction.offset,
                "before": "03 (ldarg.1)",
                "after": "16 (ldc.i4.0)",
            })

        patched = bytes(patched)
        differences = [i for i, (a, b) in enumerate(zip(source, patched)) if a != b]
        if len(source) != len(patched) or differences != [e["file_offset"] for e in edits]:
            raise PatchError("Unexpected changes outside the two patch sites.")
        new_body = read_method_body_from_bytes(patched[offset:])
        for old, new in zip(body.instructions, new_body.instructions):
            expected = b"\x16" if old.offset in ARGUMENT_READ_OFFSETS else old.get_bytes()
            if new.get_bytes() != expected:
                raise PatchError("Patched IL failed verification.")
        if len(body.instructions) != len(new_body.instructions):
            raise PatchError("Instruction count changed.")

        manifest = {
            "variant": "watcher-disabled-test",
            "assembly_version": "1.0.0.40 (unchanged)",
            "source_sha256": sha256(source),
            "patched_sha256": sha256(patched),
            "size_bytes": len(patched),
            "target": f"{TARGET_TYPE}.{TARGET_METHOD}",
            "changes": edits,
            "behavior": "Force enabled=false and call RebuildWatchers(false).",
            "runtime_tested_on_emby": False,
        }
        return patched, manifest
    finally:
        pe.close()


def create_artifact(source_path, output_dir):
    source_path = Path(source_path).resolve()
    output_dir = Path(output_dir).resolve()
    dll_path = output_dir / "StrmAssistant.dll"
    if dll_path.resolve() == source_path:
        raise PatchError("Refusing to overwrite the input DLL; choose a separate directory.")
    names = ("StrmAssistant.dll", "patch-manifest.json", "SHA256SUMS", "INSTALL.md")
    if any((output_dir / name).exists() for name in names):
        raise PatchError("Output files already exist; choose a fresh output directory.")

    patched, manifest = patch_bytes(source_path.read_bytes())
    instructions = (Path(__file__).resolve().parent / "INSTALL.md").read_bytes()
    output_dir.mkdir(parents=True, exist_ok=True)
    dll_path.write_bytes(patched)
    (output_dir / "patch-manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
    )
    (output_dir / "SHA256SUMS").write_text(
        f"{manifest['patched_sha256']}  StrmAssistant.dll\n", encoding="ascii"
    )
    (output_dir / "INSTALL.md").write_bytes(instructions)
    return dll_path, manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=Path("StrmAssistant.dll"))
    parser.add_argument("--output-dir", type=Path, default=Path("artifacts/watcher-disabled"))
    args = parser.parse_args()
    try:
        path, manifest = create_artifact(args.input, args.output_dir)
    except (PatchError, OSError) as error:
        parser.exit(1, f"ERROR: {error}\n")
    print(f"Created: {path}")
    print(f"SHA256: {manifest['patched_sha256']}")
    print("Exactly two IL bytes changed. Original DLL unchanged. Emby runtime test still required.")


if __name__ == "__main__":
    main()
