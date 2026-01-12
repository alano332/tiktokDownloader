import globalPluginHandler
import addonHandler
import wx
from . import dialogs
from . import downloader
from .manager import DownloadManager
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
import time

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
		except Exception:
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

		if TikTokDownloaderSettingsPanel not in settingsDialogs.NVDASettingsDialog.categoryClasses:
			settingsDialogs.NVDASettingsDialog.categoryClasses.append(TikTokDownloaderSettingsPanel)

		self.dlg = None
		self.is_updating = False

		self.manager = DownloadManager(
			max_concurrent=3,
			on_item_added=self._on_item_added,
			on_item_updated=self._on_item_updated,
			on_item_removed=self._on_item_removed,
			on_queue_updated=self._on_queue_updated,
			is_updating_callable=lambda: self.is_updating,
			play_sound_callable=playSound,
		)

		self.createMenu()

		self.manager.load_state()

		threading.Thread(target=self._startup_update_check, daemon=True).start()

	def createMenu(self):
		self.toolsMenu = gui.mainFrame.sysTrayIcon.toolsMenu
		self.menuItem = self.toolsMenu.Append(wx.ID_ANY, _("TikTok Downloader..."), _("Open TikTok Downloader"))
		gui.mainFrame.sysTrayIcon.Bind(wx.EVT_MENU, self.script_openDownloader, self.menuItem)

	def terminate(self):
		try:
			settingsDialogs.NVDASettingsDialog.categoryClasses.remove(TikTokDownloaderSettingsPanel)
		except Exception:
			pass

		try:
			if self.menuItem:
				self.toolsMenu.Remove(self.menuItem)
		except Exception:
			pass

		if self.dlg:
			try:
				self.dlg.Destroy()
			except Exception:
				pass

		self.manager.mark_all_interrupted_and_terminate_processes()

		super(GlobalPlugin, self).terminate()

	def _on_item_added(self, d_id, data):
		if self.dlg:
			wx.CallAfter(self.dlg.add_download_item, d_id, data.get("title", ""), data.get("status", STATUS_QUEUED))
			wx.CallAfter(self.dlg.update_queue_status)

	def _on_item_updated(self, d_id, data):
		if self.dlg:
			status = data.get("status", "")
			percent = data.get("progress")
			wx.CallAfter(self.dlg.update_status, d_id, status, percent)
			wx.CallAfter(self.dlg.update_queue_status)
		self.manager.save_state()

	def _on_item_removed(self, d_id):
		if self.dlg:
			wx.CallAfter(self.dlg.remove_download_item, d_id)

	def _on_queue_updated(self):
		if self.dlg:
			wx.CallAfter(self.dlg.update_queue_status)

	def _startup_update_check(self):
		time.sleep(5)
		for _ in range(12):
			if self.get_active_count() == 0 and self.get_queued_count() == 0:
				self._silent_update(manual=False)
				return
			time.sleep(5)

	def _silent_update(self, manual=False):
		if self.get_active_count() > 0:
			return _("Cannot update yt-dlp while downloads are active. Please stop downloads and try again.") if manual else _(
				"Skipped yt-dlp update check because downloads are active."
			)

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
					encoding="utf-8",
					errors="replace",
					timeout=120
				)

				output = (proc.stdout or "") + "\n" + (proc.stderr or "")
				logging.info(f"Update Output: {output}")

				if "up-to-date" in output or "is up to date" in output:
					status_msg = _("yt-dlp is up to date.")
				elif "Updating to version" in output:
					try:
						ver = output.split("Updating to version")[1].split()[0]
						status_msg = _("Updated yt-dlp to version {}.").format(ver)
					except Exception:
						status_msg = _("Updated yt-dlp to latest version.")
				else:
					status_msg = _("Update Info: {}").format(output.strip()[:200])
			else:
				status_msg = _("yt-dlp executable not found.")
		except Exception as e:
			logging.error(f"Auto-update failed: {e}")
			status_msg = _("Update failed: {}").format(str(e))
		finally:
			self.is_updating = False

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
		download_path = config.conf["tiktokDownloader"]["downloadPath"] or os.path.join(os.path.expanduser("~"), "Downloads")
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
		except Exception:
			return False

	def get_video_url(self):
		url = ""

		if handler and UIA:
			try:
				focus = api.getFocusObject()
				if hasattr(focus, "appModule") and focus.appModule.appName in ["chrome", "msedge", "firefox", "brave", "opera"]:
					start = time.monotonic()

					def is_address_bar(obj):
						try:
							if obj.role == controlTypes.Role.EDIT:
								name = (obj.name or "").lower()
								if any(k in name for k in ("address", "search", "location", "url")):
									val = obj.value or ""
									return self._is_valid_tiktok_url(val)
						except Exception:
							pass
						return False

					curr = focus
					while curr and curr.role != controlTypes.Role.WINDOW:
						curr = curr.parent
					window = curr

					if window:
						queue = [window]
						visited = 0
						while queue and visited < 300 and (time.monotonic() - start) < 0.25:
							node = queue.pop(0)
							visited += 1

							if is_address_bar(node):
								url = node.value
								return url

							try:
								child = node.firstChild
								while child:
									queue.append(child)
									child = child.next
							except Exception:
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
					finally:
						wx.TheClipboard.Close()
			except Exception:
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
			except Exception:
				self.dlg = None

		self.dlg = dialogs.DownloaderDialog(None, self, url)
		self.dlg.Show()
		self.dlg.Raise()
		self.dlg.SetFocus()

	def iter_downloads_snapshot(self):
		return self.manager.iter_snapshot()

	def get_download_snapshot(self, d_id):
		return self.manager.get_snapshot(d_id)

	def is_url_downloading(self, url):
		return self.manager.is_url_downloading(url)

	def get_active_count(self):
		return self.manager.get_active_count()

	def get_queued_count(self):
		return self.manager.get_queued_count()

	def _get_download_path(self):
		return config.conf["tiktokDownloader"]["downloadPath"] or os.path.join(os.path.expanduser("~"), "Downloads")

	def start_download(self, url, quality_str, known_title=None, remove_watermark=True):
		return self.manager.start_download(url, quality_str, known_title=known_title, remove_watermark=remove_watermark)

	def retry_download(self, d_id):
		self.manager.retry_download(d_id)

	def stop_download(self, d_id):
		self.manager.stop_download(d_id, self._get_download_path())

	def stop_all_downloads(self):
		self.manager.stop_all(self._get_download_path())

	def remove_download(self, d_id):
		self.manager.remove_download(d_id, self._get_download_path())

	def clear_completed(self):
		return self.manager.clear_completed()

	def open_file_location(self, d_id):
		return self.manager.open_file_location(d_id, self._get_download_path())