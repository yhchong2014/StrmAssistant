# Reproducible watcher-disabled DLL

This workflow produces a **test variant of the repository-root `StrmAssistant.dll`**,
not a compilation of `StrmAssistant/StrmAssistant.csproj`. The latter is the older
Lite project and does not contain the full plugin's watcher/search implementation.

The supplied DLL reports version **1.0.0.40**. Its Emby **4.9.5.0** startup log
shows successful Chinese-search initialization using the existing `simple` index.
A subsequent long startup gap ends at the extra STRM file watcher's startup log.
Static inspection shows synchronous recursive watcher setup inside plugin startup.
This makes the watcher a strong suspect; disabling it is a diagnostic comparison,
not a guarantee that all startup delay is fixed.

No server logs or user configuration are needed or included in the build.

## Exact change

`StrmAssistant.Services.StrmFileWatcher.Configure(bool, int)` reads its `enabled`
argument twice. Replace those two `ldarg.1` instructions with `ldc.i4.0`:

1. Store `false` in the watcher's `enabled` field.
2. Invoke existing `RebuildWatchers(false)`, preserving cleanup and its disabled
   log message instead of creating recursive filesystem watchers.

The method header, length, branch offsets, disposed check and all other file
bytes are unchanged. The original DLL stays untouched. Settings changes cannot
silently restart the plugin watcher in this variant.

The patcher accepts only this exact original input:

```text
c1df8edc1f6539cb46c3b4122d2431b2651cc9239c7743ea463899a462016c79  StrmAssistant.dll
```

It also checks the managed method signature and full method body, rejects signed
assemblies, verifies the decoded output, and records the two edits and hashes in
`patch-manifest.json`. A new upstream DLL needs fresh inspection and an updated
patch/test; **do not just replace the allowed hash**.

## GitHub Actions / 在 GitHub 下载

Workflow: **Build watcher-disabled test DLL (Emby 4.9)**

- Changes to the patch tools, input DLL or workflow on `main` or the session branch
  trigger a run automatically. Pull requests targeting `main` also run these checks.
- Once this workflow is on the default branch, **Actions → Build watcher-disabled
  test DLL (Emby 4.9) → Run workflow** provides manual builds. Before that, use the
  push-triggered run on the session branch; the manual button may not be available.
- Open a successful run and download the artifact named
  **StrmAssistant-1.0.0.40-watcher-disabled-test**. GitHub may require sign-in.
- Extract it: `StrmAssistant.dll`, `INSTALL.md`, `SHA256SUMS`, `patch-manifest.json`.
- Artifacts expire after 30 days; rerun the workflow to reproduce them.

这是在原 DLL 上关闭额外文件监听的测试补丁，不是编译 Lite 源码。
进入 Actions，打开成功的运行，在 Artifacts 下载测试版。
安装前请阅读 [INSTALL.md](INSTALL.md)，先停止 Emby 并备份原 DLL。
**中文增强搜索保持开启，不要删除分词器或数据库。**

## Local reproduction

Python 3.11 or 3.12, from the repository root:

```sh
python -m venv .venv
# Linux/macOS; on Windows use .venv\Scripts\Activate.ps1
. .venv/bin/activate
python -m pip install -r tools/watcher_patch/requirements.txt
python -m unittest discover -s tools/watcher_patch -p 'test_*.py' -v
python tools/watcher_patch/patch_watcher.py
(cd artifacts/watcher-disabled && sha256sum -c SHA256SUMS)
```

Output: `artifacts/watcher-disabled/` (Git-ignored). The patcher refuses to
replace the original DLL or existing output files. To reproduce a second time,
choose a fresh directory with `--output-dir artifacts/another-test`.

Tests verify the exact two-byte diff, preservation of the surrounding IL,
unchanged input, deterministic output, rejection of unsupported/already-patched
binaries, and the method's simulated behavior for enabled/disabled/disposed states.
**They do not execute the plugin in Emby.** Follow the installation guide's
startup, search, playback and library-import checks on the actual server.

For installation, retained features, trade-offs and rollback, see [INSTALL.md](INSTALL.md).
