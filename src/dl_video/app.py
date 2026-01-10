"""Main Textual application for dl-video."""

from collections.abc import Iterable
from pathlib import Path

from textual import events
from textual.app import App, ComposeResult, SystemCommand
from textual.binding import Binding
from textual.containers import Container, Horizontal, Vertical
from textual.screen import ModalScreen, Screen
from textual.widgets import Button, Footer, Header, Input, Label, Select, Static, Switch
from textual.worker import Worker, WorkerState

from dl_video.components import InputForm, JobsPanel, LogHistoryPanel, SettingsPanel
from dl_video.models import Config, Job, OperationResult, OperationState
from dl_video.services.converter import ConversionError, VideoConverter
from dl_video.services.downloader import DownloadError, VideoDownloader
from dl_video.services.uploader import FileUploader, UploadError
from dl_video.utils.config import ConfigManager
from dl_video.utils.file_ops import open_file_in_folder, open_folder
from dl_video.utils.history import HistoryManager, HistoryRecord
from dl_video.utils.slugifier import Slugifier


class OverwriteConfirmScreen(ModalScreen[bool]):
    """Modal screen for confirming file overwrite."""

    DEFAULT_CSS = """
    OverwriteConfirmScreen {
        align: center middle;
    }
    
    OverwriteConfirmScreen > Container {
        width: 60;
        height: auto;
        border: thick $primary;
        background: $surface;
        padding: 1 2;
    }
    
    OverwriteConfirmScreen .title {
        text-style: bold;
        margin-bottom: 1;
    }
    
    OverwriteConfirmScreen .message {
        margin-bottom: 1;
    }
    
    OverwriteConfirmScreen .buttons {
        height: auto;
        align: center middle;
    }
    
    OverwriteConfirmScreen Button {
        margin: 0 1;
    }
    """

    BINDINGS = [
        Binding("escape", "cancel", "Cancel"),
        Binding("enter", "confirm", "Confirm"),
    ]

    def __init__(self, filename: str) -> None:
        super().__init__()
        self._filename = filename

    def compose(self) -> ComposeResult:
        with Container():
            yield Label("File Already Exists", classes="title")
            yield Label(
                f"The file '{self._filename}' already exists. Do you want to overwrite it?",
                classes="message",
            )
            with Horizontal(classes="buttons"):
                yield Button("Overwrite", id="confirm-btn", variant="warning")
                yield Button("Cancel", id="cancel-btn", variant="default")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "confirm-btn":
            self.dismiss(True)
        else:
            self.dismiss(False)

    def action_cancel(self) -> None:
        self.dismiss(False)

    def action_confirm(self) -> None:
        self.dismiss(True)


class UploadPromptScreen(ModalScreen[bool]):
    """Modal screen for prompting upload after download."""

    DEFAULT_CSS = """
    UploadPromptScreen {
        align: center middle;
    }
    
    UploadPromptScreen > Container {
        width: 60;
        height: auto;
        border: thick $primary;
        background: $surface;
        padding: 1 2;
    }
    
    UploadPromptScreen .title {
        text-style: bold;
        margin-bottom: 1;
    }
    
    UploadPromptScreen .message {
        margin-bottom: 1;
    }
    
    UploadPromptScreen .buttons {
        height: auto;
        align: center middle;
    }
    
    UploadPromptScreen Button {
        margin: 0 1;
    }
    """

    BINDINGS = [
        Binding("escape", "cancel", "Cancel"),
        Binding("y", "confirm", "Yes"),
        Binding("n", "cancel", "No"),
    ]

    def __init__(self, filename: str) -> None:
        super().__init__()
        self._filename = filename

    def compose(self) -> ComposeResult:
        with Container():
            yield Label("Upload to upload.beer?", classes="title")
            yield Label(
                f"Would you like to upload '{self._filename}' to upload.beer?",
                classes="message",
            )
            with Horizontal(classes="buttons"):
                yield Button("Yes (Y)", id="confirm-btn", variant="primary")
                yield Button("No (N)", id="cancel-btn", variant="default")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "confirm-btn":
            self.dismiss(True)
        else:
            self.dismiss(False)

    def action_cancel(self) -> None:
        self.dismiss(False)

    def action_confirm(self) -> None:
        self.dismiss(True)


class SettingsScreen(ModalScreen[None]):
    """Modal screen for settings."""

    DEFAULT_CSS = """
    SettingsScreen {
        align: center middle;
    }
    
    SettingsScreen > Container {
        width: 50;
        height: auto;
        border: thick $accent;
        background: $surface;
        padding: 1 2;
    }
    
    SettingsScreen .title {
        text-style: bold;
        margin-bottom: 1;
        color: $accent;
    }
    
    SettingsScreen .setting-row {
        height: 3;
        margin: 0;
    }
    
    SettingsScreen .setting-row Switch {
        margin-right: 1;
    }
    
    SettingsScreen .setting-row Label {
        padding-top: 1;
    }
    
    SettingsScreen .setting-row Select {
        width: 14;
        margin-left: 1;
    }
    
    SettingsScreen .dir-label {
        color: $text-muted;
        height: 1;
        margin-top: 1;
    }
    
    SettingsScreen #download-dir {
        margin: 0;
        height: 3;
    }
    
    SettingsScreen .buttons {
        height: auto;
        align: center middle;
        margin-top: 1;
    }
    """

    BINDINGS = [
        Binding("escape", "close", "Close"),
    ]

    BROWSER_OPTIONS = [
        ("None", ""),
        ("Chrome", "chrome"),
        ("Firefox", "firefox"),
        ("Safari", "safari"),
        ("Edge", "edge"),
        ("Brave", "brave"),
    ]

    def __init__(self, config: "Config") -> None:
        super().__init__()
        self._config = config

    def compose(self) -> ComposeResult:
        with Container():
            yield Label("⚙ Settings", classes="title")
            with Horizontal(classes="setting-row"):
                yield Switch(value=self._config.auto_upload, id="auto-upload")
                yield Label("Auto-upload to upload.beer")
            with Horizontal(classes="setting-row"):
                yield Switch(value=self._config.skip_conversion, id="skip-conversion")
                yield Label("Skip ffmpeg conversion")
            with Horizontal(classes="setting-row"):
                yield Label("Cookies from: ")
                yield Select(
                    self.BROWSER_OPTIONS,
                    value=self._config.cookies_browser or "",
                    id="cookies-browser",
                    allow_blank=False,
                )
            yield Label("Download folder:", classes="dir-label")
            yield Input(
                value=str(self._config.download_dir),
                id="download-dir",
            )
            with Horizontal(classes="buttons"):
                yield Button("Done", id="close-btn", variant="primary")

    def on_switch_changed(self, event) -> None:
        if isinstance(event.switch, Switch):
            if event.switch.id == "auto-upload":
                self._config.auto_upload = event.value
            elif event.switch.id == "skip-conversion":
                self._config.skip_conversion = event.value
            self._notify_change()

    def on_select_changed(self, event) -> None:
        if event.select.id == "cookies-browser":
            value = event.value if event.value else None
            self._config.cookies_browser = value
            self._notify_change()

    def on_input_changed(self, event: Input.Changed) -> None:
        if event.input.id == "download-dir":
            try:
                self._config.download_dir = Path(event.value).expanduser()
                self._notify_change()
            except Exception:
                pass

    def _notify_change(self) -> None:
        self.post_message(SettingsPanel.ConfigChanged(self._config))

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "close-btn":
            self.dismiss(None)

    def action_close(self) -> None:
        self.dismiss(None)



class DLVideoApp(App):
    """Main Textual application for video downloading."""

    TITLE = "dl-video"
    CSS_PATH = "app.tcss"

    BINDINGS = [
        Binding("ctrl+q", "quit", "Quit", show=True),
        Binding("escape", "cancel_all", "Cancel All", show=True),
        Binding("ctrl+o", "open_folder", "Open Folder", show=True),
        Binding("ctrl+c", "copy_last_url", "Copy URL", show=True),
        Binding("ctrl+p", "command_palette", "Commands", show=True),
        Binding("ctrl+l", "clear_log", "Clear Log", show=False),
        Binding("tab", "focus_next", show=False),
        Binding("shift+tab", "focus_previous", show=False),
    ]

    def __init__(self, initial_url: str | None = None) -> None:
        super().__init__()
        self.initial_url = initial_url
        self._config_manager = ConfigManager()
        self._config = self._config_manager.load()
        self._history_manager = HistoryManager()
        self._slugifier = Slugifier()
        self._last_output_path: Path | None = None
        self._last_upload_url: str | None = None
        
        # Track jobs and their workers
        self._jobs: dict[str, Job] = {}
        self._job_workers: dict[str, Worker] = {}
        self._job_services: dict[str, dict] = {}  # Services per job for cancellation

    def compose(self) -> ComposeResult:
        yield Header()
        with Vertical(id="main-container"):
            yield InputForm(initial_url=self.initial_url)
            yield JobsPanel()
            yield LogHistoryPanel()
        yield Footer()

    def on_mount(self) -> None:
        log_panel = self.query_one(LogHistoryPanel)
        log_panel.log_info("Welcome to dl-video!")
        log_panel.log_info("Enter a video URL and press Enter. You can queue multiple downloads.")
        
        # Load history into UI
        for record in self._history_manager.get_all():
            log_panel.add_entry(
                filename=record.filename,
                file_path=Path(record.file_path),
                source_url=record.source_url,
                upload_url=record.upload_url,
                file_size=record.file_size,
                from_history=True,
            )

    def get_system_commands(self, screen: Screen) -> Iterable[SystemCommand]:
        yield from super().get_system_commands(screen)
        yield SystemCommand("Settings", "Open settings", self.action_open_settings)
        yield SystemCommand("Open download folder", "Open the download folder", self.action_open_folder)
        yield SystemCommand("Clear log", "Clear all log messages", self.action_clear_log)
        yield SystemCommand("Clear history", "Clear all download history", self.action_clear_history)
        if self._last_output_path and self._last_output_path.exists():
            yield SystemCommand(
                "Reveal last download",
                f"Show {self._last_output_path.name} in file manager",
                self.action_open_folder,
            )

    def action_open_settings(self) -> None:
        self.push_screen(SettingsScreen(self._config))

    def on_paste(self, event: events.Paste) -> None:
        text = event.text.strip()
        if text and (text.startswith("http://") or text.startswith("https://")):
            try:
                input_form = self.query_one(InputForm)
                url_input = input_form.query_one("#url-input", Input)
                url_input.value = text
                url_input.focus()
                event.prevent_default()
            except Exception:
                pass

    def action_quit(self) -> None:
        self._cancel_all_jobs()
        self._save_config()
        self.exit()

    def action_cancel_all(self) -> None:
        """Cancel all running jobs."""
        active_jobs = [j for j in self._jobs.values() if j.is_active]
        if active_jobs:
            self._cancel_all_jobs()
            log_panel = self.query_one(LogHistoryPanel)
            log_panel.log_warning(f"Cancelled {len(active_jobs)} job(s)")

    def action_open_folder(self) -> None:
        log_panel = self.query_one(LogHistoryPanel)
        if self._last_output_path and self._last_output_path.exists():
            if open_file_in_folder(self._last_output_path):
                log_panel.log_info(f"Opened folder: {self._last_output_path.parent}")
            else:
                log_panel.log_warning("Could not open file manager")
        elif self._config.download_dir.exists():
            if open_folder(self._config.download_dir):
                log_panel.log_info(f"Opened folder: {self._config.download_dir}")
            else:
                log_panel.log_warning("Could not open file manager")
        else:
            log_panel.log_warning("Download directory does not exist yet")

    def action_clear_log(self) -> None:
        log_panel = self.query_one(LogHistoryPanel)
        log_panel.clear()

    def action_copy_last_url(self) -> None:
        """Copy the last upload URL to clipboard."""
        if self._last_upload_url:
            self.copy_to_clipboard(self._last_upload_url)
            self.notify("URL copied!", severity="information")
        else:
            self.notify("No upload URL to copy", severity="warning")

    def action_clear_history(self) -> None:
        """Clear all download history."""
        self._history_manager.clear()
        log_panel = self.query_one(LogHistoryPanel)
        log_panel.clear_history()
        self.notify("History cleared", severity="information")

    def _cancel_all_jobs(self) -> None:
        """Cancel all running jobs."""
        for job_id in list(self._jobs.keys()):
            self._cancel_job(job_id)

    def _cancel_job(self, job_id: str) -> None:
        """Cancel a specific job."""
        if job_id not in self._jobs:
            return
        
        job = self._jobs[job_id]
        if not job.is_active:
            return
        
        # Cancel worker
        if job_id in self._job_workers:
            worker = self._job_workers[job_id]
            if worker.state == WorkerState.RUNNING:
                worker.cancel()
        
        # Cancel services
        if job_id in self._job_services:
            services = self._job_services[job_id]
            for service in services.values():
                if hasattr(service, 'cancel'):
                    service.cancel()
            del self._job_services[job_id]
        
        # Update job state and remove from UI
        job.state = OperationState.CANCELLED
        job.status_message = "Cancelled"
        
        # Remove cancelled job from panel
        jobs_panel = self.query_one(JobsPanel)
        jobs_panel.remove_job(job_id)
        del self._jobs[job_id]

    def _save_config(self) -> None:
        try:
            self._config_manager.save(self._config)
        except Exception:
            pass

    def on_input_form_download_requested(self, event: InputForm.DownloadRequested) -> None:
        self._start_job(event.url, event.filename)

    def on_jobs_panel_cancel_requested(self, event: JobsPanel.CancelRequested) -> None:
        self._cancel_job(event.job_id)
        log_panel = self.query_one(LogHistoryPanel)
        log_panel.log_warning(f"Job cancelled")

    def on_settings_panel_config_changed(self, event: SettingsPanel.ConfigChanged) -> None:
        self._config = event.config
        self._save_config()

    def on_log_history_panel_entry_selected(self, event: LogHistoryPanel.EntrySelected) -> None:
        log_panel = self.query_one(LogHistoryPanel)
        entry = event.entry
        if entry.upload_url:
            self.copy_to_clipboard(entry.upload_url)
            log_panel.log_info(f"Copied URL: {entry.upload_url}")
            self.notify("URL copied to clipboard!", severity="information")
        elif entry.file_path.exists():
            if open_file_in_folder(entry.file_path):
                log_panel.log_info(f"Revealed: {entry.file_path.name}")
            else:
                log_panel.log_warning("Could not open file manager")

    def on_log_history_panel_url_clicked(self, event: LogHistoryPanel.UrlClicked) -> None:
        """Handle URL click in log - copy to clipboard."""
        self.copy_to_clipboard(event.url)
        self.notify("URL copied to clipboard!", severity="information")

    def _start_job(self, url: str, custom_filename: str | None) -> None:
        """Start a new download job."""
        # Create job
        job = Job(
            url=url,
            custom_filename=custom_filename,
            state=OperationState.FETCHING_METADATA,
            status_message="Starting...",
            include_conversion=not self._config.skip_conversion,
            include_upload=self._config.auto_upload,
        )
        self._jobs[job.id] = job
        
        # Create services for this job
        self._job_services[job.id] = {
            'downloader': VideoDownloader(cookies_browser=self._config.cookies_browser),
            'converter': VideoConverter(),
            'uploader': FileUploader(),
        }
        
        # Add to UI
        jobs_panel = self.query_one(JobsPanel)
        jobs_panel.add_job(job)
        
        # Clear input form for next URL
        input_form = self.query_one(InputForm)
        input_form.clear()
        
        # Log
        log_panel = self.query_one(LogHistoryPanel)
        log_panel.log_info(f"Starting download: {url[:50]}...")
        
        # Start worker
        worker = self.run_worker(
            self._job_workflow(job.id),
            name=f"job_{job.id}",
            exclusive=False,  # Allow multiple concurrent workers
        )
        self._job_workers[job.id] = worker

    def _update_job_ui(self, job: Job) -> None:
        """Update the job in the UI."""
        jobs_panel = self.query_one(JobsPanel)
        jobs_panel.update_job(job)

    async def _job_workflow(self, job_id: str) -> OperationResult:
        """Execute the download workflow for a job."""
        job = self._jobs[job_id]
        services = self._job_services[job_id]
        downloader = services['downloader']
        converter = services['converter']
        uploader = services['uploader']
        
        log_panel = self.query_one(LogHistoryPanel)
        output_path: Path | None = None
        upload_url: str | None = None
        temp_files: list[Path] = []

        try:
            # Phase 1: Fetch metadata
            job.state = OperationState.FETCHING_METADATA
            job.status_message = "Fetching info..."
            self._update_job_ui(job)
            
            metadata = await downloader.get_metadata(job.url)
            job.title = metadata.title
            log_panel.log_success(f"Found: {metadata.title}")
            self._update_job_ui(job)
            
            # Determine filename
            if job.custom_filename:
                filename = self._slugifier.slugify(job.custom_filename)
            else:
                filename = self._slugifier.slugify(metadata.title)
            
            # Prepare output path
            output_dir = self._config.download_dir
            output_dir.mkdir(parents=True, exist_ok=True)
            output_path = output_dir / f"{filename}.mp4"
            
            # Check for existing file
            if output_path.exists():
                should_overwrite = await self._confirm_overwrite(output_path.name)
                if not should_overwrite:
                    job.state = OperationState.CANCELLED
                    job.status_message = "Skipped (file exists)"
                    self._update_job_ui(job)
                    return OperationResult(success=False, error_message="Cancelled by user")
            
            # Phase 2: Download
            job.state = OperationState.DOWNLOADING
            job.progress = 0
            self._update_job_ui(job)
            
            def download_progress(progress: float) -> None:
                job.progress = progress
                self._update_job_ui(job)
            
            downloaded_path = await downloader.download(job.url, output_path, download_progress)
            temp_files.append(downloaded_path)
            log_panel.log_success(f"Downloaded: {downloaded_path.name}")
            
            # Phase 3: Convert (if enabled)
            if job.include_conversion and downloaded_path.suffix.lower() != ".mp4":
                job.state = OperationState.CONVERTING
                job.progress = 0
                self._update_job_ui(job)
                
                converted_path = downloaded_path.with_suffix(".mp4")
                
                def convert_progress(progress: float) -> None:
                    job.progress = progress
                    self._update_job_ui(job)
                
                converted_path = await converter.convert(downloaded_path, converted_path, convert_progress)
                temp_files.append(converted_path)
                log_panel.log_success(f"Converted: {converted_path.name}")
                
                try:
                    downloaded_path.unlink()
                    temp_files.remove(downloaded_path)
                except Exception:
                    pass
                
                output_path = converted_path
            else:
                output_path = downloaded_path
            
            # Get file size
            file_size = output_path.stat().st_size if output_path.exists() else None
            
            # Phase 4: Upload
            should_upload = job.include_upload
            if not should_upload:
                should_upload = await self._prompt_upload(output_path.name)
            
            if should_upload:
                job.state = OperationState.UPLOADING
                job.progress = 0
                self._update_job_ui(job)
                
                def upload_progress(progress: float) -> None:
                    job.progress = progress
                    self._update_job_ui(job)
                
                upload_url = await uploader.upload(output_path, upload_progress)
                log_panel.log_success(f"Uploaded: {upload_url}", url=upload_url)
                self.copy_to_clipboard(upload_url)
                self._last_upload_url = upload_url
            
            # Success!
            job.state = OperationState.COMPLETED
            job.progress = 100
            job.output_path = output_path
            job.upload_url = upload_url
            job.file_size = file_size
            
            # Remove from jobs panel
            jobs_panel = self.query_one(JobsPanel)
            jobs_panel.remove_job(job_id)
            
            log_panel.log_success(f"Completed: {output_path.name}")
            self.bell()
            self.notify(f"Downloaded: {output_path.name}", title="Complete", severity="information")
            
            self._last_output_path = output_path
            
            # Add to history UI
            log_panel.add_entry(
                filename=output_path.name,
                file_path=output_path,
                source_url=job.url,
                upload_url=upload_url,
                file_size=file_size,
            )
            
            # Persist to history file
            self._history_manager.add(HistoryRecord.create(
                filename=output_path.name,
                source_url=job.url,
                file_path=output_path,
                file_size=file_size,
                upload_url=upload_url,
            ))
            
            temp_files.clear()
            return OperationResult(success=True, output_path=output_path, upload_url=upload_url, file_size=file_size)

        except (DownloadError, ConversionError, UploadError) as e:
            job.state = OperationState.ERROR
            job.error_message = str(e)
            self._update_job_ui(job)
            log_panel.log_error(str(e))
            self.bell()
            self.notify(str(e), title="Error", severity="error")
            for f in temp_files:
                try:
                    f.unlink()
                except Exception:
                    pass
            return OperationResult(success=False, error_message=str(e))

        except Exception as e:
            job.state = OperationState.ERROR
            job.error_message = str(e)
            self._update_job_ui(job)
            log_panel.log_error(f"Unexpected error: {e}")
            self.bell()
            for f in temp_files:
                try:
                    f.unlink()
                except Exception:
                    pass
            return OperationResult(success=False, error_message=str(e))

        finally:
            # Cleanup services
            if job_id in self._job_services:
                del self._job_services[job_id]
            if job_id in self._job_workers:
                del self._job_workers[job_id]

    async def _confirm_overwrite(self, filename: str) -> bool:
        return await self.push_screen_wait(OverwriteConfirmScreen(filename))

    async def _prompt_upload(self, filename: str) -> bool:
        return await self.push_screen_wait(UploadPromptScreen(filename))
