# TikTok Downloader for NVDA

A powerful and accessible NVDA add-on to download videos from TikTok. Designed specifically for visually impaired users with full screen reader support.

## Features

- **Video Download**: Download TikTok videos in MP4 format
- **Watermark-Free Option**: Attempt to download videos without the TikTok watermark
- **Quality Selection**: Choose from Best, 1080p, 720p, 480p, or 360p
- **Smart URL Detection**: Automatically detects TikTok URLs from your browser address bar or clipboard
- **Background Downloads**: Downloads continue in the background while you use other applications
- **Download Queue**: Add multiple videos to the queue and download them sequentially
- **Real-time Progress**: View download speed, file size, ETA, and percentage
- **Sound Notifications**: Audio feedback when downloads complete or fail (configurable)
- **Auto-Retry**: Automatically retry failed downloads (configurable attempts)
- **Download Statistics**: Track your total number of downloaded videos
- **Persistent State**: Interrupted downloads are saved and can be retried after restarting NVDA

## Requirements

- NVDA 2019.3 or later
- Windows 10 or later
- Ensure you have the `bin` folder populated with `yt-dlp.exe`, `ffmpeg.exe`, AND `ffprobe.exe`. (These are excluded from the repo to save space).

## Installation

1. Download the latest `.nvda-addon` file from the [Releases](../../releases) page
2. Open the file with NVDA running
3. Confirm the installation when prompted
4. Restart NVDA if required

### Manual Installation (Development)

1. Clone this repository
2. Download the required binaries:
   - [yt-dlp.exe](https://github.com/yt-dlp/yt-dlp/releases/latest/download/yt-dlp.exe)
   - [ffmpeg](https://www.gyan.dev/ffmpeg/builds/) (essentials build - extract `ffmpeg.exe` and `ffprobe.exe`)
3. Place the binaries in `globalPlugins/tiktokDownloader/bin/`
4. Copy the `addon` folder to your NVDA user configuration directory (e.g., `%APPDATA%\nvda\addons`).

## Usage

### Opening the Downloader

- Press `NVDA+Shift+T` to open the TikTok Downloader dialog
- Or navigate to **NVDA Menu → Tools → TikTok Downloader...**

### Downloading a Video

1. Copy a TikTok video URL to your clipboard (the add-on will auto-detect it)
2. Open the downloader with `NVDA+Shift+T`
3. The URL should be automatically filled in; if not, paste it manually
4. Select your preferred quality
5. Check "Try to remove watermark" if desired
6. Click "Add to Download Queue" or press Enter

### Quick Download

Press `NVDA+Shift+Control+T` to instantly start downloading a TikTok video from your clipboard without opening the dialog.

### Managing Downloads

- **Retry**: Retry a failed or stopped download
- **Stop**: Stop an active download
- **Remove**: Remove a download from the list
- **Open File Location**: Open the folder containing a completed download
- **Clear Completed**: Remove all completed downloads from the list
- **Stop All**: Stop all active downloads

### Keyboard Shortcuts in the Downloads List

- `Delete`: Remove the selected download
- `Enter`: Open the file location for completed downloads

## Configuration

Access settings via **NVDA Menu → Preferences → Settings → TikTok Downloader**:

| Setting | Description |
|---------|-------------|
| Download Folder | Where downloaded videos are saved (default: Downloads folder) |
| Play Sound Notifications | Enable/disable completion and error sounds |
| Try to Remove Watermark by Default | Always attempt watermark-free downloads |
| Auto-Retry Attempts | Number of automatic retry attempts (0-10, default: 2) |

## Keyboard Shortcuts Summary

| Shortcut | Action |
|----------|--------|
| `NVDA+Shift+T` | Open TikTok Downloader |
| `NVDA+Shift+Control+T` | Quick download from clipboard |
| `Escape` | Close the dialog |
| `Delete` | Remove selected download |
| `Enter` | Open file location (completed downloads) |

## Supported URL Formats

The add-on supports various TikTok URL formats:

- `https://www.tiktok.com/@username/video/1234567890`
- `https://m.tiktok.com/...`
- `https://vm.tiktok.com/...`
- `https://vt.tiktok.com/...`

## Technical Details

- Uses [yt-dlp](https://github.com/yt-dlp/yt-dlp) for video extraction and downloading
- Uses [ffmpeg](https://ffmpeg.org/) for video merging and format conversion
- Downloads are processed in a queue with up to 3 concurrent downloads
- Download state is persisted in `nvda_tiktok_downloader_state.json` in the user's home directory
- The add-on automatically updates yt-dlp on startup

## Troubleshooting

### "yt-dlp.exe not found" or "ffmpeg.exe not found"

Make sure the required binaries are present in the `bin` folder:
- `globalPlugins/tiktokDownloader/bin/yt-dlp.exe`
- `globalPlugins/tiktokDownloader/bin/ffmpeg.exe`
- `globalPlugins/tiktokDownloader/bin/ffprobe.exe`

### Download fails with error

1. Make sure you have an active internet connection
2. Try updating yt-dlp via **Settings → Check for yt-dlp Updates**
3. Some videos may be region-restricted or private
4. Check if the URL is valid and the video still exists

### No sound notifications

Check that "Play sound notifications" is enabled in the add-on settings.

## Contributing

Contributions are welcome! Please feel free to submit issues or pull requests.

## License

This project is licensed under the GNU General Public License v2.0.

## Acknowledgments

- [NVDA](https://www.nvaccess.org/) - The free screen reader for Windows
- [yt-dlp](https://github.com/yt-dlp/yt-dlp) - The powerful video downloader
- [ffmpeg](https://ffmpeg.org/) - The multimedia framework