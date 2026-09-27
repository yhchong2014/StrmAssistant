# Strm Assistant

![logo](StrmAssistant/Properties/thumb.png "logo")

## Purpose

1. Improve initial playback start speed
2. Image capture and thumbnail preview enhanced
3. Playback behavior-based intro and credits detection
4. Independent external subtitle scan

## Update

1. Support concurrent tasks
2. Support non-strm media imported with ffprobe blocked
3. Include media extras
4. Process media items by release date in the descending order
5. Add plugin config page with library multi-selection
6. Image capture enhanced
7. Introduce catch-up mode
8. Playback behavior-based intro and credits detection for episodes
9. Independent external subtitle scan

## Install

1. Download `StrmAssistant.dll` to the `plugins` folder
2. Restart Emby
3. Go to the Plugins page and check the plugin version and settings

**Note**: The minimum required Emby version is 4.8.5.0.

## Emby 4.9.5.0 watcher-disabled test DLL

The supplied root `StrmAssistant.dll` differs from the older Lite source here.
A separate [patch workflow](tools/watcher_patch/README.md) reproduces a test DLL
that disables only its extra STRM file watcher, leaving Chinese search intact.
It does not rebuild the Lite project or establish full 4.9 compatibility.
Read the [installation and rollback guide](tools/watcher_patch/INSTALL.md) first.
