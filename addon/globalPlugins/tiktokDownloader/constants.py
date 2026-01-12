STATUS_QUEUED = "Queued"
STATUS_STARTING = "Starting"
STATUS_DOWNLOADING = "Downloading"
STATUS_MERGING = "Merging"
STATUS_COMPLETED = "Completed"
STATUS_ERROR = "Error"
STATUS_STOPPED = "Stopped"
STATUS_INTERRUPTED = "Interrupted"
STATUS_RETRYING = "Retrying"

ACTIVE_STATUSES = [STATUS_QUEUED, STATUS_STARTING, STATUS_DOWNLOADING, STATUS_MERGING, STATUS_RETRYING]
FINISHED_STATUSES = [STATUS_COMPLETED, STATUS_ERROR, STATUS_STOPPED, STATUS_INTERRUPTED]


def is_active_status(status):
	if not status:
		return False
	for s in ACTIVE_STATUSES:
		if status == s or (isinstance(status, str) and s in status):
			return True
	return False


def is_finished_status(status):
	if not status:
		return False
	for s in FINISHED_STATUSES:
		if status == s or (isinstance(status, str) and s in status):
			return True
	return False


def guess_state_from_status_text(statusText: str) -> str:
	if not statusText:
		return STATUS_INTERRUPTED

	for s in FINISHED_STATUSES:
		if s in statusText:
			return s

	for s in ACTIVE_STATUSES:
		if s in statusText:
			return s

	return STATUS_INTERRUPTED