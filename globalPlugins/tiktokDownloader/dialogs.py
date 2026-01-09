import wx
import re
import config
import ui
import os
from .constants import *


class DownloaderDialog(wx.Dialog):
	QUALITY_OPTIONS = [
		("best", _("Best")),
		("1080", "1080p"),
		("720", "720p"),
		("480", "480p"),
		("360", "360p"),
	]

	def __init__(self, parent, plugin_instance, url=""):
		super().__init__(parent, title=_("TikTok Downloader"), size=(650, 600))
		self.plugin = plugin_instance
		self.Center()
		self.Raise()
		self.SetFocus()

		panel = wx.Panel(self)
		vbox = wx.BoxSizer(wx.VERTICAL)

		lbl_url = wx.StaticText(panel, label=_("Enter TikTok video link:"))
		self.txt_url = wx.TextCtrl(panel, value=url)
		self.txt_url.SetName(_("Enter TikTok video link"))
		vbox.Add(lbl_url, flag=wx.LEFT|wx.TOP, border=10)
		vbox.Add(self.txt_url, flag=wx.EXPAND|wx.LEFT|wx.RIGHT|wx.BOTTOM, border=10)

		hbox_options = wx.BoxSizer(wx.HORIZONTAL)

		quality_box = wx.BoxSizer(wx.VERTICAL)
		lbl_quality = wx.StaticText(panel, label=_("Quality:"))
		self.quality_keys = [q[0] for q in self.QUALITY_OPTIONS]
		self.quality_labels = [q[1] for q in self.QUALITY_OPTIONS]
		self.choice_quality = wx.Choice(panel, choices=self.quality_labels)
		self.choice_quality.SetName(_("Quality"))

		last_quality = config.conf["tiktokDownloader"]["lastQuality"]
		try:
			if last_quality in self.quality_keys:
				idx = self.quality_keys.index(last_quality)
				self.choice_quality.SetSelection(idx)
			else:
				self.choice_quality.SetSelection(0)
		except:
			self.choice_quality.SetSelection(0)

		quality_box.Add(lbl_quality, flag=wx.BOTTOM, border=5)
		quality_box.Add(self.choice_quality, flag=wx.EXPAND)
		hbox_options.Add(quality_box, proportion=1, flag=wx.RIGHT, border=10)

		watermark_box = wx.BoxSizer(wx.VERTICAL)
		self.chk_watermark = wx.CheckBox(panel, label=_("Try to remove watermark"))
		self.chk_watermark.SetValue(config.conf["tiktokDownloader"]["removeWatermark"])
		watermark_box.Add(self.chk_watermark, flag=wx.TOP, border=20)
		hbox_options.Add(watermark_box, proportion=1)

		vbox.Add(hbox_options, flag=wx.EXPAND|wx.LEFT|wx.RIGHT, border=10)

		hbox_buttons = wx.BoxSizer(wx.HORIZONTAL)

		self.btn_download = wx.Button(panel, label=_("Add to Download Queue"))
		self.btn_download.Bind(wx.EVT_BUTTON, self.on_download)
		hbox_buttons.Add(self.btn_download, flag=wx.RIGHT, border=5)

		self.btn_open_folder = wx.Button(panel, label=_("Open Download Folder"))
		self.btn_open_folder.Bind(wx.EVT_BUTTON, self.on_open_folder)
		hbox_buttons.Add(self.btn_open_folder)

		vbox.Add(hbox_buttons, flag=wx.ALIGN_CENTER|wx.ALL, border=10)

		self.lbl_queue_status = wx.StaticText(panel, label="")
		vbox.Add(self.lbl_queue_status, flag=wx.LEFT|wx.BOTTOM, border=10)

		lbl_list = wx.StaticText(panel, label=_("Downloads:"))
		vbox.Add(lbl_list, flag=wx.LEFT, border=10)

		self.list_downloads = wx.ListCtrl(panel, style=wx.LC_REPORT | wx.LC_SINGLE_SEL)
		self.list_downloads.SetName(_("Downloads List"))
		self.list_downloads.InsertColumn(0, _("Status"), width=500)
		self.list_downloads.InsertColumn(1, _("Progress"), width=80)
		self.list_downloads.Bind(wx.EVT_LIST_ITEM_SELECTED, self.on_list_selection)
		self.list_downloads.Bind(wx.EVT_LIST_ITEM_DESELECTED, self.on_list_selection)
		self.list_downloads.Bind(wx.EVT_KEY_DOWN, self.on_list_key)
		self.list_downloads.Bind(wx.EVT_LIST_ITEM_ACTIVATED, self.on_list_activated)

		vbox.Add(self.list_downloads, proportion=1, flag=wx.EXPAND|wx.LEFT|wx.RIGHT|wx.BOTTOM, border=10)

		hbox_controls = wx.BoxSizer(wx.HORIZONTAL)

		self.btn_retry = wx.Button(panel, label=_("Retry"))
		self.btn_retry.Bind(wx.EVT_BUTTON, self.on_retry)
		self.btn_retry.Enable(False)

		self.btn_stop = wx.Button(panel, label=_("Stop"))
		self.btn_stop.Bind(wx.EVT_BUTTON, self.on_stop)
		self.btn_stop.Enable(False)

		self.btn_remove = wx.Button(panel, label=_("Remove"))
		self.btn_remove.Bind(wx.EVT_BUTTON, self.on_remove)
		self.btn_remove.Enable(False)

		self.btn_open_location = wx.Button(panel, label=_("Open File Location"))
		self.btn_open_location.Bind(wx.EVT_BUTTON, self.on_open_location)
		self.btn_open_location.Enable(False)

		hbox_controls.Add(self.btn_retry, flag=wx.RIGHT, border=5)
		hbox_controls.Add(self.btn_stop, flag=wx.RIGHT, border=5)
		hbox_controls.Add(self.btn_remove, flag=wx.RIGHT, border=5)
		hbox_controls.Add(self.btn_open_location)

		vbox.Add(hbox_controls, flag=wx.ALIGN_CENTER|wx.BOTTOM, border=10)

		hbox_batch = wx.BoxSizer(wx.HORIZONTAL)

		self.btn_clear_completed = wx.Button(panel, label=_("Clear Completed"))
		self.btn_clear_completed.Bind(wx.EVT_BUTTON, self.on_clear_completed)

		self.btn_stop_all = wx.Button(panel, label=_("Stop All"))
		self.btn_stop_all.Bind(wx.EVT_BUTTON, self.on_stop_all)

		hbox_batch.Add(self.btn_clear_completed, flag=wx.RIGHT, border=5)
		hbox_batch.Add(self.btn_stop_all)

		vbox.Add(hbox_batch, flag=wx.ALIGN_CENTER|wx.BOTTOM, border=10)

		self.gauge = wx.Gauge(panel, range=100, size=(250, 25))
		vbox.Add(self.gauge, flag=wx.EXPAND|wx.LEFT|wx.RIGHT|wx.BOTTOM, border=10)

		self.lbl_status = wx.StaticText(panel, label="")
		vbox.Add(self.lbl_status, flag=wx.LEFT|wx.BOTTOM, border=10)

		self.btn_close = wx.Button(panel, id=wx.ID_CANCEL, label=_("Close"))
		self.btn_close.Bind(wx.EVT_BUTTON, self.on_close)
		vbox.Add(self.btn_close, flag=wx.ALIGN_CENTER|wx.BOTTOM, border=10)

		panel.SetSizer(vbox)

		self.Bind(wx.EVT_CHAR_HOOK, self.on_escape)
		self.Bind(wx.EVT_CLOSE, self.on_close)

		self.list_map = []
		self.refresh_list()
		self.update_queue_status()

	def get_selected_quality_key(self):
		idx = self.choice_quality.GetSelection()
		if idx >= 0 and idx < len(self.quality_keys):
			return self.quality_keys[idx]
		return "best"

	def refresh_list(self):
		self.list_downloads.DeleteAllItems()
		self.list_map = []

		for d_id, data in self.plugin.downloads.items():
			self.add_download_item(d_id, data['title'], data.get('status', ''))

		self.update_button_states()

	def add_download_item(self, d_id, title, status=None):
		if status is None:
			status = STATUS_STARTING
		idx = self.list_downloads.InsertItem(self.list_downloads.GetItemCount(), status)
		self.list_downloads.SetItem(idx, 1, "0%")
		self.list_map.append(d_id)

	def remove_download_item(self, d_id):
		if d_id in self.list_map:
			idx = self.list_map.index(d_id)
			self.list_downloads.DeleteItem(idx)
			self.list_map.pop(idx)
			self.update_button_states()
			self.update_queue_status()

	def update_status(self, d_id, status_text, percent=None):
		if d_id not in self.list_map:
			return

		idx = self.list_map.index(d_id)
		self.list_downloads.SetItemText(idx, status_text)

		if percent is not None:
			self.list_downloads.SetItem(idx, 1, f"{int(percent)}%")
		elif STATUS_COMPLETED in status_text:
			self.list_downloads.SetItem(idx, 1, "100%")

		sel = self.list_downloads.GetFirstSelected()
		if sel == idx:
			self.lbl_status.SetLabel(status_text)
			if percent is not None:
				self.gauge.SetValue(int(percent))
			elif STATUS_COMPLETED in status_text:
				self.gauge.SetValue(100)
			elif STATUS_STARTING in status_text:
				self.gauge.SetValue(0)
			self.update_button_states()

		self.update_queue_status()

	def update_queue_status(self):
		active = self.plugin.get_active_count()
		queued = self.plugin.get_queued_count()
		total = config.conf["tiktokDownloader"]["totalDownloads"]

		status = _("Active: {} | Queued: {} | Total Downloaded: {}").format(active, queued, total)
		self.lbl_queue_status.SetLabel(status)

	def on_list_selection(self, event):
		self.update_button_states()

		idx = self.list_downloads.GetFirstSelected()
		if idx != -1 and idx < len(self.list_map):
			d_id = self.list_map[idx]
			if d_id in self.plugin.downloads:
				data = self.plugin.downloads[d_id]
				self.lbl_status.SetLabel(data.get('status', ''))
				if STATUS_COMPLETED in data.get('status', ''):
					self.gauge.SetValue(100)
				else:
					self.gauge.SetValue(0)

	def on_list_key(self, event):
		key = event.GetKeyCode()
		if key == wx.WXK_DELETE:
			self.on_remove(None)
		else:
			event.Skip()

	def on_list_activated(self, event):
		idx = self.list_downloads.GetFirstSelected()
		if idx != -1 and idx < len(self.list_map):
			d_id = self.list_map[idx]
			if d_id in self.plugin.downloads:
				status = self.plugin.downloads[d_id].get('status', '')
				if STATUS_COMPLETED in status:
					self.plugin.open_file_location(d_id)

	def update_button_states(self):
		idx = self.list_downloads.GetFirstSelected()

		can_retry = False
		can_stop = False
		can_remove = False
		can_open = False

		if idx != -1 and idx < len(self.list_map):
			d_id = self.list_map[idx]
			if d_id in self.plugin.downloads:
				status = self.plugin.downloads[d_id].get('status', '')

				active = is_active_status(status)

				if not active and STATUS_COMPLETED not in status:
					can_retry = True

				if active:
					can_stop = True

				can_remove = True

				if STATUS_COMPLETED in status:
					can_open = True

		self.btn_retry.Enable(can_retry)
		self.btn_stop.Enable(can_stop)
		self.btn_remove.Enable(can_remove)
		self.btn_open_location.Enable(can_open)

	def on_retry(self, event):
		idx = self.list_downloads.GetFirstSelected()
		if idx != -1 and idx < len(self.list_map):
			d_id = self.list_map[idx]
			self.plugin.retry_download(d_id)
			self.update_button_states()

	def on_stop(self, event):
		idx = self.list_downloads.GetFirstSelected()
		if idx != -1 and idx < len(self.list_map):
			d_id = self.list_map[idx]
			self.plugin.stop_download(d_id)
			self.update_button_states()

	def on_remove(self, event):
		idx = self.list_downloads.GetFirstSelected()
		if idx != -1 and idx < len(self.list_map):
			d_id = self.list_map[idx]
			self.plugin.remove_download(d_id)

	def on_open_location(self, event):
		idx = self.list_downloads.GetFirstSelected()
		if idx != -1 and idx < len(self.list_map):
			d_id = self.list_map[idx]
			if not self.plugin.open_file_location(d_id):
				wx.MessageBox(_("Could not find the file location."), _("Error"), wx.OK | wx.ICON_ERROR)

	def on_open_folder(self, event):
		download_path = config.conf["tiktokDownloader"]["downloadPath"]
		if not download_path:
			download_path = os.path.join(os.path.expanduser("~"), "Downloads")
		if os.path.exists(download_path):
			os.startfile(download_path)
		else:
			wx.MessageBox(_("Download folder does not exist."), _("Error"), wx.OK | wx.ICON_ERROR)

	def on_clear_completed(self, event):
		count = self.plugin.clear_completed()
		if count > 0:
			ui.message(_("{} completed downloads cleared.").format(count))
		else:
			ui.message(_("No completed downloads to clear."))
		self.update_queue_status()

	def on_stop_all(self, event):
		self.plugin.stop_all_downloads()
		ui.message(_("All downloads stopped."))
		self.update_button_states()
		self.update_queue_status()

	def on_escape(self, event):
		if event.GetKeyCode() == wx.WXK_ESCAPE:
			self.Close()
		else:
			event.Skip()

	def on_close(self, event):
		self.plugin.dlg = None
		self.Destroy()

	def is_valid_url(self, url):
		if not url:
			return False
		pattern = r'^(https?://)?(www\.|m\.|vm\.|vt\.)?(tiktok\.com)/.+$'
		return re.match(pattern, url.strip()) is not None

	def on_download(self, event):
		url = self.txt_url.GetValue().strip()
		if not url:
			wx.MessageBox(_("Please provide a valid TikTok URL to proceed."), _("Input Required"), wx.OK | wx.ICON_WARNING)
			return

		if not self.is_valid_url(url):
			wx.MessageBox(_("The URL provided does not appear to be a valid TikTok link.\nPlease check the URL and try again."), _("Invalid URL"), wx.OK | wx.ICON_ERROR)
			return

		if self.plugin.is_url_downloading(url):
			wx.MessageBox(_("This URL is already being downloaded."), _("Duplicate Download"), wx.OK | wx.ICON_WARNING)
			return

		quality_key = self.get_selected_quality_key()
		remove_watermark = self.chk_watermark.GetValue()

		config.conf["tiktokDownloader"]["lastQuality"] = quality_key
		config.conf["tiktokDownloader"]["removeWatermark"] = remove_watermark

		self.lbl_status.SetLabel(_("Starting download..."))

		self.plugin.start_download(url, quality_key, remove_watermark=remove_watermark)

		self.txt_url.SetValue("")
		self.txt_url.SetFocus()