import os
import time
import json
import logging
import threading
import subprocess
from dataclasses import dataclass, field
from collections import deque
from typing import Optional, Callable, Dict, Any, List, Tuple

import addonHandler
addonHandler.initTranslation()

from . import downloader
from .constants import (
	STATUS_QUEUED,
	STATUS_STARTING,
	STATUS_DOWNLOADING,
	STATUS_MERGING,
	STATUS_COMPLETED,
	STATUS_ERROR,
	STATUS_STOPPED,
	STATUS_INTERRUPTED,
	STATUS_RETRYING,
	is_finished_status,
	is_active_status,
	guess_state_from_status_text,
)

try:
	import config
except Exception:
	config = None


def _default_download_path() -> str:
	return os.path.join(os.path.expanduser("~"), "Downloads")


def _state_file_path() -> str:
	return os.path.join(os.path.expanduser("~"), "nvda_tiktok_downloader_state.json")


@dataclass
class DownloadItem:
	id: int
	url: str
	quality_str: str
	remove_watermark: bool = True

	title: str = field(default_factory=lambda: _("Resolving..."))
	state: str = STATUS_QUEUED
	statusText: str = STATUS_QUEUED
	progress: Optional[float] = None

	file_path: Optional[str] = None
	current_filename: Optional[str] = None

	retry_count: int = 0
	manual_stop: bool = False
	completed: bool = False

	process: Optional[subprocess.Popen] = None

	created_at: float = field(default_factory=time.time)
	updated_at: float = field(default_factory=time.time)

	def to_public_dict(self) -> Dict[str, Any]:
		return {
			"title": self.title,
			"state": self.state,
			"status": self.statusText,
			"progress": self.progress,
			"process": self.process,
			"url": self.url,
			"file_path": self.file_path,
			"retry_count": self.retry_count,
			"completed": self.completed,
			"manual_stop": self.manual_stop,
			"current_filename": self.current_filename,
			"params": {
				"url": self.url,
				"quality_str": self.quality_str,
				"known_title": None if self.title == _("Resolving...") else self.title,
				"remove_watermark": self.remove_watermark,
			}
		}

	def to_persist_dict(self) -> Dict[str, Any]:
		return {
			"id": self.id,
			"url": self.url,
			"quality_str": self.quality_str,
			"remove_watermark": self.remove_watermark,
			"title": self.title,
			"state": self.state,
			"statusText": self.statusText,
			"progress": self.progress,
			"file_path": self.file_path,
			"current_filename": self.current_filename,
			"retry_count": self.retry_count,
			"manual_stop": self.manual_stop,
			"completed": self.completed,
			"created_at": self.created_at,
			"updated_at": self.updated_at,
		}

	@staticmethod
	def from_persist_dict(d: Dict[str, Any]) -> "DownloadItem":
		item = DownloadItem(
			id=int(d.get("id")),
			url=d.get("url", ""),
			quality_str=d.get("quality_str", "best"),
			remove_watermark=bool(d.get("remove_watermark", True)),
		)
		item.title = d.get("title") or _("Unknown Video")
		item.state = d.get("state") or guess_state_from_status_text(d.get("statusText", ""))
		item.statusText = d.get("statusText") or f"{item.title} - {item.state}"
		item.progress = d.get("progress")
		item.file_path = d.get("file_path")
		item.current_filename = d.get("current_filename")
		item.retry_count = int(d.get("retry_count", 0))
		item.manual_stop = bool(d.get("manual_stop", False))
		item.completed = bool(d.get("completed", False))
		item.created_at = float(d.get("created_at", time.time()))
		item.updated_at = float(d.get("updated_at", time.time()))
		item.process = None
		return item


class DownloadManager:

	def __init__(
		self,
		max_concurrent: int = 3,
		on_item_added: Optional[Callable[[int, Dict[str, Any]], None]] = None,
		on_item_updated: Optional[Callable[[int, Dict[str, Any]], None]] = None,
		on_item_removed: Optional[Callable[[int], None]] = None,
		on_queue_updated: Optional[Callable[[], None]] = None,
		is_updating_callable: Optional[Callable[[], bool]] = None,
		play_sound_callable: Optional[Callable[[bool], None]] = None,
	):
		self.MAX_CONCURRENT = max(1, int(max_concurrent))
		self._lock = threading.RLock()
		self._queue = deque()
		self._items: Dict[int, DownloadItem] = {}
		self._next_id = 0

		self._on_item_added = on_item_added
		self._on_item_updated = on_item_updated
		self._on_item_removed = on_item_removed
		self._on_queue_updated = on_queue_updated
		self._is_updating = is_updating_callable or (lambda: False)
		self._play_sound = play_sound_callable

	def iter_snapshot(self) -> List[Tuple[int, Dict[str, Any]]]:
		with self._lock:
			return [(i, item.to_public_dict()) for i, item in self._items.items()]

	def get_snapshot(self, d_id: int) -> Optional[Dict[str, Any]]:
		with self._lock:
			item = self._items.get(d_id)
			return item.to_public_dict() if item else None

	def get_active_count(self) -> int:
		active_states = {STATUS_STARTING, STATUS_DOWNLOADING, STATUS_MERGING, STATUS_RETRYING}
		with self._lock:
			return sum(1 for it in self._items.values() if it.state in active_states)

	def get_queued_count(self) -> int:
		with self._lock:
			return len(self._queue)

	def is_url_downloading(self, url: str) -> bool:
		with self._lock:
			for it in self._items.values():
				if it.url == url and is_active_status(it.state) and not is_finished_status(it.state):
					return True
		return False

	def start_download(self, url: str, quality_str: str, known_title: Optional[str] = None, remove_watermark: bool = True) -> int:
		with self._lock:
			d_id = self._next_id
			self._next_id += 1

			item = DownloadItem(
				id=d_id,
				url=url,
				quality_str=quality_str,
				remove_watermark=remove_watermark,
			)
			if known_title:
				item.title = known_title
			item.state = STATUS_QUEUED
			item.statusText = STATUS_QUEUED
			item.updated_at = time.time()

			self._items[d_id] = item
			self._queue.append(d_id)

		if self._on_item_added:
			self._on_item_added(d_id, item.to_public_dict())
		self._signal_queue_update()
		self._process_queue()
		return d_id

	def retry_download(self, d_id: int):
		with self._lock:
			item = self._items.get(d_id)
			if not item:
				return
			item.retry_count = 0
			item.manual_stop = False
			item.completed = False
			item.state = STATUS_QUEUED
			item.statusText = f"{item.title} - {STATUS_QUEUED}"
			item.progress = None
			item.updated_at = time.time()
			if d_id not in self._queue:
				self._queue.append(d_id)

		self._notify_item_updated(d_id)
		self._signal_queue_update()
		self._process_queue()

	def stop_download(self, d_id: int, download_path: str):
		with self._lock:
			item = self._items.get(d_id)
			if not item:
				return

			try:
				self._queue.remove(d_id)
			except ValueError:
				pass

			item.manual_stop = True

			proc = item.process

		if proc:
			try:
				if proc.poll() is None:
					proc.terminate()
					try:
						proc.wait(timeout=2)
					except Exception:
						proc.kill()
			except Exception:
				pass

		temp_path = os.path.join(os.path.expanduser("~"), "AppData", "Local", "Temp", "nvda_tiktok_downloader")
		try:
			downloader.cleanup_partial_files(download_path, item.title, item.current_filename)
			downloader.cleanup_partial_files(temp_path, item.title, item.current_filename)
		except Exception:
			pass

		with self._lock:
			item = self._items.get(d_id)
			if not item:
				return
			item.state = STATUS_STOPPED
			item.statusText = f"{item.title} - {STATUS_STOPPED}"
			item.progress = None
			item.updated_at = time.time()

		self._notify_item_updated(d_id)
		self._signal_queue_update()
		self._process_queue()

	def stop_all(self, download_path: str):
		with self._lock:
			ids = list(self._items.keys())
		for d_id in ids:
			snap = self.get_snapshot(d_id)
			if not snap:
				continue
			state = snap.get("state") or guess_state_from_status_text(snap.get("status", ""))
			if not is_finished_status(state):
				self.stop_download(d_id, download_path)

	def remove_download(self, d_id: int, download_path: str):
		snap = self.get_snapshot(d_id)
		if snap:
			state = snap.get("state") or guess_state_from_status_text(snap.get("status", ""))
			if is_active_status(state) and not is_finished_status(state):
				self.stop_download(d_id, download_path)

		with self._lock:
			try:
				self._queue.remove(d_id)
			except ValueError:
				pass

			if d_id in self._items:
				del self._items[d_id]

		if self._on_item_removed:
			self._on_item_removed(d_id)
		self._signal_queue_update()
		self.save_state()

	def clear_completed(self) -> int:
		to_remove = []
		with self._lock:
			for d_id, it in self._items.items():
				if it.state == STATUS_COMPLETED:
					to_remove.append(d_id)

		for d_id in to_remove:
			with self._lock:
				if d_id in self._items:
					del self._items[d_id]
			if self._on_item_removed:
				self._on_item_removed(d_id)

		if to_remove:
			self._signal_queue_update()
			self.save_state()
		return len(to_remove)

	def open_file_location(self, d_id: int, download_path: str) -> bool:
		snap = self.get_snapshot(d_id)
		if not snap:
			return False

		file_path = snap.get("file_path")
		if file_path and os.path.exists(file_path):
			try:
				subprocess.run(["explorer", "/select,", file_path], check=False)
				return True
			except Exception:
				pass

		if download_path and os.path.exists(download_path):
			try:
				os.startfile(download_path)
				return True
			except Exception:
				pass

		return False

	def save_state(self):
		path = _state_file_path()

		with self._lock:
			downloads = {}
			for d_id, it in self._items.items():
				if it.state == STATUS_COMPLETED:
					continue
				downloads[str(d_id)] = it.to_persist_dict()

			payload = {
				"version": 2,
				"next_download_id": self._next_id,
				"downloads": downloads,
			}

		try:
			with open(path, "w", encoding="utf-8") as f:
				json.dump(payload, f, indent=4, ensure_ascii=False)
		except Exception as e:
			logging.error(f"Failed to save state: {e}")

	def load_state(self):
		path = _state_file_path()
		if not os.path.exists(path):
			return

		try:
			with open(path, "r", encoding="utf-8") as f:
				loaded = json.load(f)
		except Exception as e:
			logging.error(f"Failed to load state: {e}")
			return

		if not loaded:
			return

		if isinstance(loaded, dict) and "downloads" not in loaded:
			downloads_dict = loaded
			next_id = None
		else:
			downloads_dict = loaded.get("downloads", {}) or {}
			next_id = loaded.get("next_download_id")

		items: Dict[int, DownloadItem] = {}
		max_id = 0

		for k, v in downloads_dict.items():
			try:
				d_id = int(k)
			except Exception:
				continue
			max_id = max(max_id, d_id)

			if "id" not in v:
				params = v.get("params", {}) if isinstance(v, dict) else {}
				item = DownloadItem(
					id=d_id,
					url=v.get("url") or params.get("url", ""),
					quality_str=params.get("quality_str", "best"),
					remove_watermark=bool(params.get("remove_watermark", True)),
				)
				item.title = v.get("title") or _("Unknown Video")
				status_text = v.get("status", "")
				item.state = guess_state_from_status_text(status_text)
				item.statusText = status_text or f"{item.title} - {item.state}"
				item.retry_count = int(v.get("retry_count", 0))
				item.completed = bool(v.get("completed", False))
				item.manual_stop = bool(v.get("manual_stop", False))
				item.file_path = v.get("file_path")
				item.current_filename = v.get("current_filename")
				item.progress = v.get("progress")
			else:
				item = DownloadItem.from_persist_dict(v)

			if not is_finished_status(item.state):
				item.state = STATUS_INTERRUPTED
				item.statusText = f"{item.title} - {STATUS_INTERRUPTED}"
				item.progress = None
				item.process = None

			items[d_id] = item

		with self._lock:
			self._items = items
			if isinstance(next_id, int) and next_id > max_id:
				self._next_id = next_id
			else:
				self._next_id = max_id + 1

	def mark_all_interrupted_and_terminate_processes(self):
		with self._lock:
			for it in self._items.values():
				proc = it.process
				if proc:
					try:
						proc.terminate()
						proc.wait(timeout=1)
					except Exception:
						pass
				it.process = None
				if not is_finished_status(it.state):
					it.state = STATUS_INTERRUPTED
					it.statusText = f"{it.title} - {STATUS_INTERRUPTED}"
					it.progress = None
					it.updated_at = time.time()

		self.save_state()

	def _signal_queue_update(self):
		if self._on_queue_updated:
			try:
				self._on_queue_updated()
			except Exception:
				pass

	def _notify_item_updated(self, d_id: int):
		if not self._on_item_updated:
			return
		snap = self.get_snapshot(d_id)
		if snap is None:
			return
		try:
			self._on_item_updated(d_id, snap)
		except Exception:
			pass

	def _process_queue(self):
		if self._is_updating():
			return

		while True:
			with self._lock:
				if self.get_active_count() >= self.MAX_CONCURRENT:
					break
				if not self._queue:
					break
				d_id = self._queue.popleft()
				item = self._items.get(d_id)
				if not item:
					continue
				if item.completed or is_finished_status(item.state):
					continue
				item.state = STATUS_STARTING
				item.statusText = f"{item.title} - {STATUS_STARTING}..."
				item.updated_at = time.time()

			self._notify_item_updated(d_id)
			threading.Thread(target=self._download_worker, args=(d_id,), daemon=True).start()

		self._signal_queue_update()

	def _download_worker(self, d_id: int):
		last_ui_time = 0.0
		last_ui_percent = -1

		def throttled_update(status_text: str, percent: Optional[float] = None, state: Optional[str] = None):
			nonlocal last_ui_time, last_ui_percent
			now = time.monotonic()

			if percent is None:
				with self._lock:
					it = self._items.get(d_id)
					if not it:
						return
					if state:
						it.state = state
					it.statusText = status_text
					it.progress = None
					it.updated_at = time.time()
				self._notify_item_updated(d_id)
				return

			p_int = int(percent)
			if p_int == last_ui_percent and (now - last_ui_time) < 0.25:
				return

			last_ui_percent = p_int
			last_ui_time = now

			with self._lock:
				it = self._items.get(d_id)
				if not it:
					return
				if state:
					it.state = state
				it.statusText = status_text
				it.progress = float(percent)
				it.updated_at = time.time()

			self._notify_item_updated(d_id)

		with self._lock:
			item = self._items.get(d_id)
			if not item:
				return
			url = item.url
			quality_str = item.quality_str
			remove_watermark = item.remove_watermark

		title = None
		final_filepath = ""
		download_success = False
		last_lines: List[str] = []

		try:
			with self._lock:
				item = self._items.get(d_id)
				if not item:
					return
				need_title = (not item.title) or (item.title == _("Resolving..."))

			if need_title:
				try:
					yt_dlp_path = downloader.get_yt_dlp_path()
					startupinfo = subprocess.STARTUPINFO()
					startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
					result = subprocess.run(
						[yt_dlp_path, "--get-title", "--skip-download", "--no-warnings", url],
						capture_output=True,
						text=True,
						startupinfo=startupinfo,
						check=False,
						timeout=30,
						encoding="utf-8",
						errors="replace",
					)
					if result.returncode == 0 and result.stdout.strip():
						title = result.stdout.strip()
					else:
						title = _("TikTok Video")
				except Exception:
					title = _("TikTok Video")

				with self._lock:
					item = self._items.get(d_id)
					if item:
						item.title = title
						item.updated_at = time.time()

			with self._lock:
				item = self._items.get(d_id)
				if not item:
					return
				title = item.title or _("TikTok Video")

			display_title = title if len(title) <= 30 else title[:27] + "..."

			throttled_update(f"{display_title} - {STATUS_DOWNLOADING}...", None, state=STATUS_DOWNLOADING)

			download_path = ""
			try:
				if config:
					download_path = config.conf["tiktokDownloader"]["downloadPath"]
			except Exception:
				download_path = ""
			if not download_path:
				download_path = _default_download_path()

			if not os.path.exists(download_path):
				try:
					os.makedirs(download_path)
				except Exception:
					download_path = _default_download_path()
					os.makedirs(download_path, exist_ok=True)

			def progress_hook(text: str):
				throttled_update(f"{display_title} - {text}", None)

			proc = downloader.download_video_with_process(
				url=url,
				output_path=download_path,
				quality_str=quality_str,
				progress_hook=progress_hook,
				remove_watermark=remove_watermark,
			)

			with self._lock:
				item = self._items.get(d_id)
				if not item:
					try:
						proc.terminate()
					except Exception:
						pass
					return
				item.process = proc
				item.updated_at = time.time()

			for raw_line in proc.stdout:
				with self._lock:
					item = self._items.get(d_id)
					if not item:
						break
					if item.manual_stop:
						break

				line = (raw_line or "").strip()
				if not line:
					continue

				last_lines.append(line)
				if len(last_lines) > 30:
					last_lines.pop(0)

				if line.startswith("NVDA_TTDL_FILEPATH:"):
					final_filepath = line.split("NVDA_TTDL_FILEPATH:", 1)[1].strip()
					continue

				if line.startswith("NVDA_TTDL_PROGRESS:"):
					payload = line.split("NVDA_TTDL_PROGRESS:", 1)[1].strip()
					parts = payload.split("|")
					if parts:
						pct_str = (parts[0] or "").replace("%", "").strip()
						try:
							pct = float(pct_str)
						except Exception:
							pct = None

						if pct is not None:
							total = parts[1].strip() if len(parts) > 1 else ""
							speed = parts[2].strip() if len(parts) > 2 else ""
							eta = parts[3].strip() if len(parts) > 3 else ""

							status_bits = [f"{pct:.1f}%"]
							if total and total != "~":
								status_bits.append(total)
							if speed and speed.lower() != "unknown":
								status_bits.append(speed)
							if eta and eta.lower() != "unknown":
								status_bits.append(f"ETA: {eta}")

							throttled_update(f"{display_title} - " + " | ".join(status_bits), pct, state=STATUS_DOWNLOADING)
					continue

				if "[download]" in line:
					if "Destination:" in line:
						try:
							current_filename = line.split("Destination:", 1)[1].strip()
							with self._lock:
								item = self._items.get(d_id)
								if item:
									item.current_filename = current_filename
						except Exception:
							pass
						continue

					if "has already been downloaded" in line:
						download_success = True
						continue

				if "[Merger]" in line or "Merging formats into" in line:
					throttled_update(f"{display_title} - {STATUS_MERGING}...", None, state=STATUS_MERGING)

			proc.wait()

			with self._lock:
				item = self._items.get(d_id)
				if not item:
					return
				if item.manual_stop:
					return

			if proc.returncode == 0 or download_success:
				resolved_path = None
				if final_filepath and os.path.exists(final_filepath):
					resolved_path = final_filepath
				else:
					with self._lock:
						item = self._items.get(d_id)
						current_filename = item.current_filename if item else None
					if current_filename:
						potential = current_filename
						if not os.path.isabs(potential):
							potential = os.path.join(download_path, potential)
						mp4_path = os.path.splitext(potential)[0] + ".mp4"
						if os.path.exists(mp4_path):
							resolved_path = mp4_path
						elif os.path.exists(potential):
							resolved_path = potential

				with self._lock:
					item = self._items.get(d_id)
					if not item:
						return
					item.completed = True
					item.state = STATUS_COMPLETED
					item.statusText = f"{item.title} - {STATUS_COMPLETED}"
					item.progress = 100.0
					item.file_path = resolved_path
					item.process = None
					item.updated_at = time.time()

				self._notify_item_updated(d_id)
				self._signal_queue_update()

				try:
					if config:
						config.conf["tiktokDownloader"]["totalDownloads"] += 1
				except Exception:
					pass

				if self._play_sound:
					try:
						self._play_sound(True)
					except Exception:
						pass

				self.save_state()
				self._process_queue()
				return

			err_tail = "\n".join(last_lines[-8:])
			raise Exception(f"Download failed. Exit code: {proc.returncode}\n{err_tail}")

		except Exception as e:
			logging.error(f"Download error {d_id}: {e}")

			with self._lock:
				item = self._items.get(d_id)
				if not item:
					self._process_queue()
					return
				if item.manual_stop or item.completed:
					self._process_queue()
					return

				max_retries = 2
				try:
					if config:
						max_retries = int(config.conf["tiktokDownloader"]["autoRetryAttempts"])
				except Exception:
					max_retries = 2

				if item.retry_count < max_retries:
					item.retry_count += 1
					item.state = STATUS_RETRYING
					item.statusText = f"{item.title} - {STATUS_RETRYING}... ({item.retry_count}/{max_retries})"
					item.progress = None
					item.updated_at = time.time()
					if d_id not in self._queue:
						self._queue.append(d_id)
				else:
					item.state = STATUS_ERROR
					item.statusText = f"{STATUS_ERROR}: {item.title}"
					item.progress = None
					item.process = None
					item.updated_at = time.time()

			self._notify_item_updated(d_id)
			self._signal_queue_update()
			self.save_state()

			snap = self.get_snapshot(d_id)
			if snap and (snap.get("state") == STATUS_ERROR) and self._play_sound:
				try:
					self._play_sound(False)
				except Exception:
					pass

			self._process_queue()