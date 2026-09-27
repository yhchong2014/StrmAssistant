# StrmAssistant — watcher-disabled TEST DLL / 关闭额外文件监听测试版

## What this is

A binary patch of the supplied **StrmAssistant 1.0.0.40** DLL, intended for a
comparison test on **Emby 4.9.5.0**. It is **not** a rebuild of the older Lite
source in this repository and is not an upstream release. The assembly version
stays 1.0.0.40; identify this variant using `SHA256SUMS` and `patch-manifest.json`.

Only two IL instruction bytes change, both in
`StrmAssistant.Services.StrmFileWatcher.Configure`:

```csharp
// Before (simplified):
if (disposed) return;
this.enabled = enabled;
RebuildWatchers(enabled);

// After (simplified):
if (disposed) return;
this.enabled = false;
RebuildWatchers(false);
```

The existing cleanup and disposed checks stay intact. Settings saves cannot
re-enable the extra watcher in this test variant. The patch does not execute the
input DLL, rewrite the assembly, or change its embedded dependencies/resources.

## Retained features / 保留功能

The patch leaves the implementations and configuration of these features unchanged:

- Chinese/pinyin enhanced search / 启用增强搜索
- Cover layout and missing-cover backdrop fallback / 优化封面显示、缺失封面使用背景图
- Pinyin-initial sorting / 拼音首字母排序
- Thunder subtitle downloads / 迅雷字幕下载
- Next-episode MediaInfo preloading / 启用 MediaInfo 预加载
- MediaInfo extraction **after Emby imports an item** / 入库时提取媒体信息
- Compressed metadata responses / 启用压缩传输

**Trade-off:** the plugin no longer watches folders to notify Emby about new
STRM files, or logs modifications detected by that watcher. Use Emby's own
real-time monitoring where supported, or scheduled/manual **扫描媒体库**.
Once imported, items can still trigger the existing MediaInfo extraction handler,
subject to its enabled setting and library scope. The patch does not disable
Emby's own library monitor.

## Safe installation on the existing server / 安装

1. Wait for active library scans/writes to finish, then **stop Emby completely**.
2. Back up the Emby configuration/data directory (including `library.db`) and
   the original `/config/plugins/StrmAssistant.dll`. Store the DLL backup
   **outside the plugins folder**, so Emby cannot load both variants.
3. Verify the downloaded DLL checksum if possible:
   - Linux: run `sha256sum -c SHA256SUMS` in this artifact's directory.
   - PowerShell: `Get-FileHash .\StrmAssistant.dll -Algorithm SHA256`, then compare
     with `SHA256SUMS`.
4. Replace **only** `/config/plugins/StrmAssistant.dll` with this artifact's
   `StrmAssistant.dll`. Preserve the existing file owner/read permissions.
   For Docker, use the corresponding host path mapped to `/config`.
5. Leave Chinese enhanced search enabled and keep the existing plugin settings.
   **Do not delete `library.db`, `libsimple`, `libsimple.so`, or other tokenizer
   files. Do not uninstall the plugin or restore the search index for this test.**
6. Start Emby. Do not install the original and patched DLL side by side.

这是原 DLL 的独立测试补丁，不是 Lite 版。停止 Emby 并备份后，只替换
`/config/plugins/StrmAssistant.dll`。备份 DLL 请放在 plugins 目录以外。
保留“启用增强搜索”和分词器文件，不需要关闭中文搜索或重建数据库。

## Verify the test / 验证

- Temporarily enable **启用调试日志** if necessary.
- Look for `StrmFileWatcher 已禁用`; the watcher should no longer report
  `StrmFileWatcher 已启动，监听路径`.
- Confirm Chinese search still reports `增强搜索 - 加载成功`, and its status is
  `正常生效 / simple 中文增强分词`.
- Compare time from the initial server startup message to `Core startup complete`
  against the original DLL. The watcher is a strong suspect, not a proven
  explanation for every second of the delay.
- Test Chinese and pinyin searches and playback of an existing item.
- Add a test STRM file and run **扫描媒体库**. Check that it imports and, if enabled
  and in scope, missing MediaInfo is extracted.
- Turn off debug logging after diagnosis. Avoid automatic plugin replacement
  during the comparison: an upstream updater can overwrite this test DLL.

Static tests verify the exact two-byte change and its control flow. **No live
Emby 4.9.5.0 runtime test has been performed by the build workflow.** Success of
this patch does not establish compatibility of every upstream feature.

## Roll back / 回滚

Stop Emby, replace the test DLL with your backed-up original DLL, and start Emby.
No search-index restoration is needed just to switch between these two variants.
If you later want to **uninstall** the plugin entirely, follow its separate
Chinese-search disable-and-restore procedure first.

## Log privacy

Do not commit server logs or configuration files. Logs may contain access tokens,
private addresses and paths. Share only a redacted startup excerpt. Deleting a
public GitHub file does not erase its older commits; rotate exposed secrets.
