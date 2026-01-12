import os
import subprocess
import logging

try:
	import ui
except ImportError:
	class UI:
		def message(self, msg):
			print(f"NVDA SPEECH: {msg}")
	ui = UI()

ADDON_DIR = os.path.dirname(os.path.abspath(__file__))
BIN_DIR = os.path.join(ADDON_DIR, "bin")


def ensure_bin_dir():
	if not os.path.exists(BIN_DIR):
		os.makedirs(BIN_DIR)


def sanitize_filename(name):
	if not name:
		return "Unknown"

	invalid_chars = '<>:"/\\|?*'
	for char in invalid_chars:
		name = name.replace(char, "_")

	name = name.strip(" .")

	if len(name) > 100:
		name = name[:100]

	return name or "Unknown"


def get_yt_dlp_path():
	return os.path.join(BIN_DIR, "yt-dlp.exe")


def get_ffmpeg_path():
	return os.path.join(BIN_DIR, "ffmpeg.exe")


def get_ffprobe_path():
	return os.path.join(BIN_DIR, "ffprobe.exe")


def check_dependencies(progress_hook=None):
	ensure_bin_dir()
	yt_dlp_path = get_yt_dlp_path()
	ffmpeg_path = get_ffmpeg_path()
	ffprobe_path = get_ffprobe_path()

	missing = []

	if not os.path.exists(yt_dlp_path):
		missing.append("yt-dlp.exe")

	if not os.path.exists(ffmpeg_path):
		missing.append("ffmpeg.exe")

	if not os.path.exists(ffprobe_path):
		missing.append("ffprobe.exe")

	if missing:
		raise Exception(f"Missing required files in bin directory: {', '.join(missing)}. Please ensure the addon was installed correctly.")

	return yt_dlp_path, ffmpeg_path, ffprobe_path


def cleanup_partial_files(output_path, title, filename=None):
	if not output_path:
		return

	if filename:
		try:
			if os.path.isabs(filename):
				base_name = os.path.basename(filename)
				dir_name = os.path.dirname(filename)
				if dir_name and os.path.exists(dir_name):
					output_path = dir_name
				filename = base_name

			base_without_ext = os.path.splitext(filename)[0]
			candidates = [
				filename,
				filename + ".part",
				filename + ".ytdl",
				filename + ".temp",
				base_without_ext + ".mp4.part",
				base_without_ext + ".f0.mp4",
				base_without_ext + ".f1.mp4",
				base_without_ext + ".f2.mp4",
			]

			for cand in candidates:
				full_path = os.path.join(output_path, cand)
				if os.path.exists(full_path):
					try:
						os.remove(full_path)
					except:
						pass
		except:
			pass

	if not title:
		return

	safe_title = "".join([c for c in title if c.isalnum() or c in " ._-"]).strip()
	if not safe_title:
		return

	try:
		for file in os.listdir(output_path):
			if safe_title.lower() in file.lower():
				if file.endswith(".part") or file.endswith(".ytdl") or file.endswith(".temp"):
					try:
						os.remove(os.path.join(output_path, file))
					except:
						pass
	except:
		pass


def download_video_with_process(url, output_path, quality_str, progress_hook, remove_watermark=True):
	yt_dlp_path, ffmpeg_path, ffprobe_path = check_dependencies(progress_hook)

	if progress_hook:
		progress_hook("Starting download...")
		try:
			ui.message("Starting download...")
		except:
			pass

	out_tmpl = "%(title).100s.%(ext)s"

	if not os.path.exists(output_path):
		try:
			os.makedirs(output_path)
		except Exception as e:
			logging.error(f"Failed to create output path: {e}")

	temp_path = os.path.join(os.path.expanduser("~"), "AppData", "Local", "Temp", "nvda_tiktok_downloader")
	if not os.path.exists(temp_path):
		try:
			os.makedirs(temp_path)
		except:
			pass

	cmd = [
		yt_dlp_path,
		"--ffmpeg-location", os.path.dirname(ffmpeg_path),
		"--output", out_tmpl,
		"--paths", f"home:{output_path}",
		"--paths", f"temp:{temp_path}",
		"--newline",
		"--no-playlist",
		"--no-warnings",
		"--no-check-certificates",
		"--encoding", "utf-8",
		"--no-colors",
		"--progress-template", "download:NVDA_TTDL_PROGRESS:%(progress._percent_str)s|%(progress._total_bytes_str)s|%(progress._speed_str)s|%(progress._eta_str)s",
		"--print", "after_move:NVDA_TTDL_FILEPATH:%(filepath)s",
	]

	if remove_watermark:
		cmd.extend(["--format", "bestvideo*+bestaudio/best"])
	else:
		cmd.extend(["--format", "best"])

	cmd.extend(["--merge-output-format", "mp4"])

	if quality_str and quality_str != "best":
		cmd.extend(["-S", f"res:{quality_str}"])

	cmd.append(url)

	startupinfo = subprocess.STARTUPINFO()
	startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW

	process = subprocess.Popen(
		cmd,
		stdout=subprocess.PIPE,
		stderr=subprocess.STDOUT,
		text=True,
		startupinfo=startupinfo,
		encoding="utf-8",
		errors="replace",
	)

	return process