import globalPluginHandler
import addonHandler
import wx
from . import dialogs
from . import downloader
from .constants import *
import os
import logging
import api
import controlTypes
import threading
import subprocess
import config
import gui
import tones
from gui import guiHelper, settingsDialogs
from urllib.parse import urlparse
import scriptHandler

try:
	from UIAHandler import handler
	from UIAHandler import UIA
except ImportError:
	handler = None
	UIA = None

addonHandler.initTranslation()

confspec = {
	"tiktokDownloader": {
		"downloadPath": "string(default='')",
		"lastQuality": "string(default='best')",
		"playSounds": "boolean(default=True)",
		"autoRetryAttempts": "integer(default=2)",
		"removeWatermark": "boolean(default=True)",
		"totalDownloads": "integer(default=0)",
	}
}
config.conf.spec.update(confspec)


def playSound(success=True):
	if config.conf["tiktokDownloader"]["playSounds"]:
		try:
			if success:
				tones.beep(1000, 100)
				wx.CallLater(150, tones.beep, 1500, 100)
			else:
				tones.beep(200, 200)
		except:
			pass


class TikTokDownloaderSettingsPanel(settingsDialogs.SettingsPanel):
	title = _("TikTok Downloader")

	def makeSettings(self, settingsSizer):
		sHelper = guiHelper.BoxSizerHelper(self, sizer=settingsSizer)

		download_path = config.conf["tiktokDownloader"]["downloadPath"]
		if not download_path:
			download_path = os.path.join(os.path.expanduser("~"), "Downloads")

		self.pathEntry = sHelper.addLabeledControl(_("Download Folder:"), wx.TextCtrl)
		self.pathEntry.Value = download_path

		browseBtn = wx.Button(self, label=_("Browse..."))
		browseBtn.Bind(wx.EVT_BUTTON, self.onBrowse)
		sHelper.addItem(browseBtn)

		self.chkPlaySounds = wx.CheckBox(self, label=_("Play sound notifications"))
		self.chkPlaySounds.Value = config.conf["tiktokDownloader"]["playSounds"]
		sHelper.addItem(self.chkPlaySounds)

		self.chkRemoveWatermark = wx.CheckBox(self, label=_("Try to remove watermark by default"))
		self.chkRemoveWatermark.Value = config.conf["tiktokDownloader"]["removeWatermark"]
		sHelper.addItem(self.chkRemoveWatermark)

		self.autoRetryCtrl = sHelper.addLabeledControl(
			_("Auto-retry attempts (0 to disable):"),
			wx.SpinCtrl,
			min=0,
			max=10,
			initial=config.conf["tiktokDownloader"]["autoRetryAttempts"]
		)

		totalDownloads = config.conf["tiktokDownloader"]["totalDownloads"]
		statsLabel = wx.StaticText(self, label=_("Total videos downloaded: {}").format(totalDownloads))
		sHelper.addItem(statsLabel)

		resetStatsBtn = wx.Button(self, label=_("Reset Statistics"))
		resetStatsBtn.Bind(wx.EVT_BUTTON, self.onResetStats)
		sHelper.addItem(resetStatsBtn)

		updateBtn = wx.Button(self, label=_("Check for yt-dlp Updates"))
		updateBtn.Bind(wx.EVT_BUTTON, self.onCheckUpdates)
		sHelper.addItem(updateBtn)

	def onResetStats(self, event):
		config.conf["tiktokDownloader"]["totalDownloads"] = 0
		wx.MessageBox(_("Statistics have been reset."), _("Reset"), wx.OK | wx.ICON_INFORMATION)

	def onCheckUpdates(self, event):
		threading.Thread(target=self._run_manual_update, daemon=True).start()

	def _run_manual_update(self):
		plugin = None
		for p in globalPluginHandler.runningPlugins:
			if isinstance(p, GlobalPlugin):
				plugin = p
				break

		if plugin:
			result = plugin._silent_update(manual=True)
			wx.CallAfter(wx.MessageBox, result, _("Update Check"), wx.OK | wx.ICON_INFORMATION)
		else:
			wx.CallAfter(wx.MessageBox, _("Plugin instance not found."), _("Error"), wx.OK | wx.ICON_ERROR)

	def onBrowse(self, event):
		dlg = wx.DirDialog(self, _("Choose Download Folder"), self.pathEntry.Value)
		if dlg.ShowModal() == wx.ID_OK:
			self.pathEntry.Value = dlg.GetPath()
		dlg.Destroy()

	def onSave(self):
		config.conf["tiktokDownloader"]["downloadPath"] = self.pathEntry.Value
		config.conf["tiktokDownloader"]["playSounds"] = self.chkPlaySounds.Value
		config.conf["tiktokDownloader"]["removeWatermark"] = self.chkRemoveWatermark.Value
		config.conf["tiktokDownloader"]["autoRetryAttempts"] = self.autoRetryCtrl.Value


class GlobalPlugin(globalPluginHandler.GlobalPlugin):
	scriptCategory = _("TikTok Downloader")

	def __init__(self):
		super(GlobalPlugin, self).__init__()
		logging.info("TikTok Downloader Addon Loaded")

		settingsDialogs.NVDASettingsDialog.categoryClasses.append(TikTokDownloaderSettingsPanel)

		self.dlg = None
		self.downloads = {}
		self.next_download_id = 0
		self.is_updating = False

		self.download_queue = []
		self.MAX_CONCURRENT = 3

		self.createMenu()

		threading.Thread(target=self._silent_update, daemon=True).start()

		self.load_state()

	def createMenu(self):
		self.toolsMenu = gui.mainFrame.sysTrayIcon.toolsMenu
		self.menuItem = self.toolsMenu.Append(wx.ID_ANY, _("TikTok Downloader..."), _("Open TikTok Downloader"))
		gui.mainFrame.sysTrayIcon.Bind(wx.EVT_MENU, self.script_openDownloader, self.menuItem)

	def terminate(self):
		try:
			settingsDialogs.NVDASettingsDialog.categoryClasses.remove(TikTokDownloaderSettingsPanel)
		except:
			pass

		try:
			if self.menuItem:
				self.toolsMenu.Remove(self.menuItem)
		except:
			pass

		if self.dlg:
			try:
				self.dlg.Destroy()
			except:
				pass

		for d_id, data in self.downloads.items():
			if data.get('process'):
				try:
					data['process'].terminate()
					data['process'].wait(timeout=1)
				except:
					pass
			status = data.get('status', '')
			if STATUS_COMPLETED not in status and STATUS_ERROR not in status and STATUS_STOPPED not in status:
				data['status'] = STATUS_INTERRUPTED

		self.save_state()

		super(GlobalPlugin, self).terminate()

	def save_state(self):
		state_file = os.path.join(os.path.expanduser("~"), "nvda_tiktok_downloader_state.json")
		data_to_save = {}
		for d_id, data in self.downloads.items():
			if STATUS_COMPLETED in data.get('status', ''):
				continue

			item = data.copy()
			if 'process' in item:
				del item['process']
			data_to_save[d_id] = item

		try:
			import json
			with open(state_file, 'w', encoding='utf-8') as f:
				json.dump(data_to_save, f, indent=4)
		except Exception as e:
			logging.error(f"Failed to save state: {e}")

	def load_state(self):
		state_file = os.path.join(os.path.expanduser("~"), "nvda_tiktok_downloader_state.json")
		if not os.path.exists(state_file):
			return

		try:
			import json
			with open(state_file, 'r', encoding='utf-8') as f:
				saved_data = json.load(f)

			if not saved_data:
				return

			max_id = 0
			for d_id_str, data in saved_data.items():
				d_id = int(d_id_str)
				if d_id > max_id:
					max_id = d_id

				data['process'] = None
				status = data.get('status', '')
				if STATUS_ERROR not in status and STATUS_STOPPED not in status and STATUS_COMPLETED not in status:
					data['status'] = STATUS_INTERRUPTED

				self.downloads[d_id] = data

			self.next_download_id = max_id + 1
		except Exception as e:
			logging.error(f"Failed to load state: {e}")

	def _silent_update(self, manual=False):
		self.is_updating = True
		status_msg = _("Update check failed.")
		try:
			yt_dlp_path = downloader.get_yt_dlp_path()
			if os.path.exists(yt_dlp_path):
				logging.info("Checking for yt-dlp updates...")
				startupinfo = subprocess.STARTUPINFO()
				startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW

				proc = subprocess.run(
					[yt_dlp_path, "-U"],
					capture_output=True,
					text=True,
					startupinfo=startupinfo,
					check=False,
					encoding='utf-8',
					errors='replace',
					timeout=120
				)

				output = proc.stdout + "\n" + proc.stderr
				logging.info(f"Update Output: {output}")

				if "up-to-date" in output or "is up to date" in output:
					status_msg = _("yt-dlp is up to date.")
				elif "Updating to version" in output:
					try:
						ver = output.split("Updating to version")[1].split()[0]
						status_msg = _("Updated yt-dlp to version {}.").format(ver)
					except:
						status_msg = _("Updated yt-dlp to latest version.")
				else:
					status_msg = _("Update Info: {}").format(output.strip()[:100])

		except Exception as e:
			logging.error(f"Auto-update failed: {e}")
			status_msg = _("Update failed: {}").format(str(e))
		finally:
			self.is_updating = False
			wx.CallAfter(self._process_queue)

		return status_msg

	@scriptHandler.script(
		description=_("Opens the TikTok Downloader dialog"),
		gesture="kb:NVDA+shift+t",
	)
	def script_openDownloader(self, gesture):
		logging.info("Opening Downloader GUI")
		url = self.get_video_url()
		wx.CallAfter(self._showGui, url)

	@scriptHandler.script(
		description=_("Quick download TikTok video from clipboard"),
		gesture="kb:NVDA+shift+control+t",
	)
	def script_quickDownload(self, gesture):
		url = self.get_video_url()
		if url and self._is_valid_tiktok_url(url):
			if not self.is_url_downloading(url):
				quality = config.conf["tiktokDownloader"]["lastQuality"]
				remove_watermark = config.conf["tiktokDownloader"]["removeWatermark"]
				self.start_download(url, quality, remove_watermark=remove_watermark)
				import ui
				ui.message(_("Download started from clipboard"))
			else:
				import ui
				ui.message(_("This URL is already being downloaded"))
		else:
			import ui
			ui.message(_("No valid TikTok URL found in clipboard"))

	@scriptHandler.script(
		description=_("Opens the TikTok Downloader settings"),
	)
	def script_openSettings(self, gesture):
		wx.CallAfter(gui.mainFrame._popupSettingsDialog, settingsDialogs.NVDASettingsDialog, TikTokDownloaderSettingsPanel)

	@scriptHandler.script(
		description=_("Opens the download folder"),
	)
	def script_openDownloadFolder(self, gesture):
		download_path = config.conf["tiktokDownloader"]["downloadPath"]
		if not download_path:
			download_path = os.path.join(os.path.expanduser("~"), "Downloads")
		if os.path.exists(download_path):
			os.startfile(download_path)
		else:
			import ui
			ui.message(_("Download folder does not exist"))

	def _is_valid_tiktok_url(self, url):
		if not url:
			return False
		try:
			u = url.strip()
			if "://" not in u:
				u = "https://" + u
			parsed = urlparse(u)
			host = (parsed.hostname or "").lower()
			valid_hosts = ["tiktok.com", "www.tiktok.com", "m.tiktok.com", "vm.tiktok.com", "vt.tiktok.com"]
			return host in valid_hosts
		except:
			return False

	def get_video_url(self):
		url = ""

		if handler and UIA:
			try:
				focus = api.getFocusObject()
				if hasattr(focus, 'appModule') and focus.appModule.appName in ["chrome", "msedge", "firefox", "brave", "opera"]:
					def is_address_bar(obj):
						try:
							if obj.role == controlTypes.Role.EDIT:
								name = (obj.name or "").lower()
								if "address" in name or "search" in name or "location" in name or "url" in name:
									val = obj.value or ""
									if self._is_valid_tiktok_url(val):
										return True
						except:
							pass
						return False

					curr = focus
					while curr and curr.role != controlTypes.Role.WINDOW:
						curr = curr.parent

					window = curr
					if window:
						queue = [window]
						count = 0
						while queue and count < 500:
							node = queue.pop(0)
							count += 1

							if is_address_bar(node):
								url = node.value
								logging.info(f"Found URL via UIA: {url}")
								return url

							try:
								child = node.firstChild
								while child:
									queue.append(child)
									child = child.next
							except:
								pass
			except Exception as e:
				logging.debug(f"UIA URL fetch failed: {type(e).__name__}: {e}")

		if not url:
			try:
				if wx.TheClipboard.Open():
					try:
						if wx.TheClipboard.IsSupported(wx.DataFormat(wx.DF_TEXT)):
							data = wx.TextDataObject()
							wx.TheClipboard.GetData(data)
							text = data.GetText()
							if self._is_valid_tiktok_url(text):
								url = text
								logging.info(f"Found URL via Clipboard: {url}")
					finally:
						wx.TheClipboard.Close()
			except:
				pass

		return url

	def _showGui(self, url=""):
		if self.dlg:
			try:
				self.dlg.Raise()
				self.dlg.SetFocus()
				if url:
					self.dlg.txt_url.Value = url
				return
			except:
				self.dlg = None

		self.dlg = dialogs.DownloaderDialog(None, self, url)
		self.dlg.Show()
		self.dlg.Raise()
		self.dlg.SetFocus()

	def is_url_downloading(self, url):
		for data in self.downloads.values():
			if data.get('url') == url:
				status = data.get('status', '')
				if is_active_status(status):
					return True
		return False

	def get_active_count(self):
		count = 0
		for data in self.downloads.values():
			status = data.get('status', '')
			if STATUS_DOWNLOADING in status or STATUS_STARTING in status or STATUS_MERGING in status:
				count += 1
		return count

	def get_queued_count(self):
		return len(self.download_queue)

	def start_download(self, url, quality_str, known_title=None, remove_watermark=True):
		d_id = self.next_download_id
		self.next_download_id += 1

		initial_title = known_title if known_title else _("Resolving...")

		self.downloads[d_id] = {
			'title': initial_title,
			'status': STATUS_QUEUED,
			'process': None,
			'url': url,
			'file_path': None,
			'retry_count': 0,
			'completed': False,
			'manual_stop': False,
			'params': {
				'url': url,
				'quality_str': quality_str,
				'known_title': known_title,
				'remove_watermark': remove_watermark,
			}
		}

		if self.dlg:
			wx.CallAfter(self.dlg.add_download_item, d_id, self.downloads[d_id]['title'])
			wx.CallAfter(self.dlg.update_queue_status)

		self.download_queue.append(d_id)
		self._process_queue()

		return d_id

	def _process_queue(self):
		if self.is_updating:
			return

		active_count = self.get_active_count()

		while active_count < self.MAX_CONCURRENT and self.download_queue:
			d_id = self.download_queue.pop(0)
			if d_id in self.downloads:
				data = self.downloads[d_id]
				if data.get('completed', False):
					continue
				if is_finished_status(data.get('status', '')):
					continue
				self._start_actual_download(d_id)
				active_count += 1

		if self.dlg:
			wx.CallAfter(self.dlg.update_queue_status)

	def _start_actual_download(self, d_id):
		if d_id not in self.downloads:
			return

		data = self.downloads[d_id]

		if data.get('completed', False):
			return

		params = data['params']

		self._update_ui_status(d_id, f"{data['title']} - {STATUS_STARTING}...")

		thread = threading.Thread(
			target=self._run_download_thread,
			args=(d_id, params['url'], params['quality_str'], params.get('known_title'), params.get('remove_watermark', True)),
			daemon=True
		)
		thread.start()

	def _run_download_thread(self, d_id, url, quality_str, known_title=None, remove_watermark=True):
		if d_id not in self.downloads:
			return

		if self.downloads[d_id].get('completed', False):
			return

		title = known_title if known_title else _("Unknown Video")
		display_title = title
		download_success = False

		try:
			if not known_title:
				yt_dlp_path = downloader.get_yt_dlp_path()
				try:
					startupinfo = subprocess.STARTUPINFO()
					startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
					result = subprocess.run(
						[yt_dlp_path, "--get-title", "--skip-download", "--no-warnings", url],
						capture_output=True,
						text=True,
						startupinfo=startupinfo,
						check=False,
						timeout=30,
						encoding='utf-8',
						errors='replace'
					)
					if result.returncode == 0 and result.stdout.strip():
						title = result.stdout.strip()
					else:
						title = _("TikTok Video")
				except Exception as e:
					logging.error(f"Title fetch error: {e}")
					title = _("TikTok Video")

			display_title = title
			if len(display_title) > 30:
				display_title = display_title[:27] + "..."

			if d_id in self.downloads:
				self.downloads[d_id]['title'] = title
			self._update_ui_status(d_id, f"{display_title} - {STATUS_DOWNLOADING}...")

			download_path = config.conf["tiktokDownloader"]["downloadPath"]
			if not download_path:
				download_path = os.path.join(os.path.expanduser("~"), "Downloads")

			try:
				if not os.path.exists(download_path):
					os.makedirs(download_path)
			except Exception as e:
				logging.error(f"Failed to create download directory '{download_path}': {e}")
				download_path = os.path.join(os.path.expanduser("~"), "Downloads")
				if not os.path.exists(download_path):
					os.makedirs(download_path)

			def progress_hook(status):
				self._update_ui_status(d_id, f"{display_title} - {status}")

			process = downloader.download_video_with_process(
				url, download_path, quality_str, progress_hook, remove_watermark
			)

			if d_id in self.downloads:
				self.downloads[d_id]['process'] = process

			last_lines = []
			current_filename = ""
			final_filepath = ""

			for line in process.stdout:
				if d_id not in self.downloads:
					break

				if self.downloads[d_id].get('manual_stop', False):
					break

				line = line.strip()
				if not line:
					continue

				last_lines.append(line)
				if len(last_lines) > 20:
					last_lines.pop(0)

				if "[download]" in line:
					if "Destination:" in line:
						parts = line.split("Destination:")
						if len(parts) > 1:
							current_filename = parts[1].strip()
							if d_id in self.downloads:
								self.downloads[d_id]['current_filename'] = current_filename
						continue

					if "has already been downloaded" in line:
						download_success = True
						continue

					percent = None
					speed = ""
					eta = ""
					size = ""

					try:
						parts = line.split()
						for i, part in enumerate(parts):
							if "%" in part:
								try:
									percent = float(part.replace("%", ""))
								except:
									pass
							elif part == "of" and i + 1 < len(parts):
								size = parts[i + 1]
							elif part == "at" and i + 1 < len(parts):
								speed = parts[i + 1]
							elif part == "ETA" and i + 1 < len(parts):
								eta = parts[i + 1]
					except:
						pass

					if percent is not None:
						status_parts = [f"{percent:.1f}%"]
						if size and size != "~":
							status_parts.append(size)
						if speed and speed != "Unknown":
							status_parts.append(speed)
						if eta and eta != "Unknown":
							status_parts.append(f"ETA: {eta}")
						status_msg = f"{display_title} - " + " | ".join(status_parts)
						self._update_ui_status(d_id, status_msg, percent)

				elif "[Merger]" in line or "Merging formats into" in line:
					self._update_ui_status(d_id, f"{display_title} - {STATUS_MERGING}...", None)

				if 'Merging formats into "' in line:
					try:
						start_idx = line.index('Merging formats into "') + len('Merging formats into "')
						end_idx = line.rindex('"')
						if end_idx > start_idx:
							final_filepath = line[start_idx:end_idx]
					except:
						pass

				if "[download] " in line and " has already been downloaded" in line:
					download_success = True

			process.wait()

			if d_id not in self.downloads:
				return

			if self.downloads[d_id].get('manual_stop', False):
				return

			if process.returncode == 0 or download_success:
				self.downloads[d_id]['completed'] = True
				self.downloads[d_id]['status'] = STATUS_COMPLETED
				self._update_ui_status(d_id, f"{title} - {STATUS_COMPLETED}", 100)

				if final_filepath and os.path.exists(final_filepath):
					self.downloads[d_id]['file_path'] = final_filepath
				elif current_filename:
					potential_path = current_filename
					if not os.path.isabs(potential_path):
						potential_path = os.path.join(download_path, current_filename)
					mp4_path = os.path.splitext(potential_path)[0] + ".mp4"
					if os.path.exists(mp4_path):
						self.downloads[d_id]['file_path'] = mp4_path
					elif os.path.exists(potential_path):
						self.downloads[d_id]['file_path'] = potential_path

				try:
					config.conf["tiktokDownloader"]["totalDownloads"] += 1
				except:
					pass

				try:
					import ui
					ui.message(_("Download complete: {}").format(title))
				except:
					pass

				try:
					playSound(success=True)
				except:
					pass

				self.save_state()
				wx.CallAfter(self._process_queue)
				return

			else:
				error_details = "\n".join(last_lines[-5:])
				raise Exception(f"Download failed. Exit code: {process.returncode}\nOutput:\n{error_details}")

		except Exception as e:
			if d_id not in self.downloads:
				wx.CallAfter(self._process_queue)
				return

			if self.downloads[d_id].get('completed', False):
				wx.CallAfter(self._process_queue)
				return

			if self.downloads[d_id].get('manual_stop', False):
				wx.CallAfter(self._process_queue)
				return

			logging.error(f"Download error {d_id}: {e}")

			max_retries = config.conf["tiktokDownloader"]["autoRetryAttempts"]
			current_retries = self.downloads[d_id].get('retry_count', 0)

			if current_retries < max_retries:
				self.downloads[d_id]['retry_count'] = current_retries + 1
				retry_msg = f"{STATUS_RETRYING}... ({current_retries + 1}/{max_retries})"
				self.downloads[d_id]['status'] = retry_msg
				self._update_ui_status(d_id, f"{display_title} - {retry_msg}")

				if d_id not in self.download_queue:
					self.download_queue.append(d_id)
			else:
				self.downloads[d_id]['status'] = STATUS_ERROR
				self._update_ui_status(d_id, f"{STATUS_ERROR}: {display_title}")
				try:
					playSound(success=False)
				except:
					pass

			self.save_state()
			wx.CallAfter(self._process_queue)

	def _update_ui_status(self, d_id, status_text, percent=None):
		if d_id not in self.downloads:
			return
		self.downloads[d_id]['status'] = status_text
		if self.dlg:
			wx.CallAfter(self.dlg.update_status, d_id, status_text, percent)

	def retry_download(self, d_id):
		if d_id not in self.downloads:
			return

		data = self.downloads[d_id]

		data['status'] = STATUS_QUEUED
		data['retry_count'] = 0
		data['manual_stop'] = False
		data['completed'] = False
		self._update_ui_status(d_id, f"{data['title']} - {STATUS_QUEUED}")

		if d_id not in self.download_queue:
			self.download_queue.append(d_id)

		self._process_queue()

	def stop_download(self, d_id):
		if d_id not in self.downloads:
			return

		data = self.downloads[d_id]

		if d_id in self.download_queue:
			self.download_queue.remove(d_id)

		data['manual_stop'] = True

		proc = data.get('process')
		if proc:
			try:
				if proc.poll() is None:
					proc.terminate()
					try:
						proc.wait(timeout=2)
					except:
						proc.kill()
			except:
				pass

		download_path = config.conf["tiktokDownloader"]["downloadPath"]
		if not download_path:
			download_path = os.path.join(os.path.expanduser("~"), "Downloads")

		temp_path = os.path.join(os.path.expanduser("~"), "AppData", "Local", "Temp", "nvda_tiktok_downloader")

		filename = data.get('current_filename')
		downloader.cleanup_partial_files(download_path, data.get('title', ''), filename)
		downloader.cleanup_partial_files(temp_path, data.get('title', ''), filename)

		self.downloads[d_id]['status'] = STATUS_STOPPED
		self._update_ui_status(d_id, f"{data.get('title', 'Unknown')} - {STATUS_STOPPED}")
		self.save_state()

		wx.CallAfter(self._process_queue)

	def stop_all_downloads(self):
		ids_to_stop = []
		for d_id, data in self.downloads.items():
			status = data.get('status', '')
			if not is_finished_status(status):
				ids_to_stop.append(d_id)

		for d_id in ids_to_stop:
			self.stop_download(d_id)

	def remove_download(self, d_id):
		if d_id not in self.downloads:
			return

		data = self.downloads[d_id]
		proc = data.get('process')
		if proc:
			try:
				if proc.poll() is None:
					self.stop_download(d_id)
			except:
				pass

		if d_id in self.downloads:
			del self.downloads[d_id]

		if d_id in self.download_queue:
			self.download_queue.remove(d_id)

		self.save_state()

		if self.dlg:
			wx.CallAfter(self.dlg.remove_download_item, d_id)

	def clear_completed(self):
		to_remove = []
		for d_id, data in list(self.downloads.items()):
			if STATUS_COMPLETED in data.get('status', ''):
				to_remove.append(d_id)

		for d_id in to_remove:
			if d_id in self.downloads:
				del self.downloads[d_id]
			if self.dlg:
				wx.CallAfter(self.dlg.remove_download_item, d_id)

		self.save_state()
		return len(to_remove)

	def open_file_location(self, d_id):
		if d_id not in self.downloads:
			return False

		data = self.downloads[d_id]
		file_path = data.get('file_path')

		if file_path and os.path.exists(file_path):
			try:
				subprocess.run(['explorer', '/select,', file_path], check=False)
				return True
			except:
				pass

		download_path = config.conf["tiktokDownloader"]["downloadPath"]
		if not download_path:
			download_path = os.path.join(os.path.expanduser("~"), "Downloads")

		if os.path.exists(download_path):
			try:
				os.startfile(download_path)
				return True
			except:
				pass

		return False