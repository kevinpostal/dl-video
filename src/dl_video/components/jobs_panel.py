"""Jobs panel component for showing multiple concurrent operations."""

from textual.app import ComposeResult
from textual.containers import Container, Horizontal, Vertical, VerticalScroll
from textual.message import Message
from textual.reactive import reactive
from textual.widgets import Button, Label, ProgressBar, Static

from dl_video.models import Job, OperationState


class JobRow(Horizontal):
    """A single job row showing progress."""

    def __init__(self, job: Job) -> None:
        super().__init__(id=f"job-{job.id}", classes="job-row")
        self._job = job

    def compose(self) -> ComposeResult:
        yield Static(self._job.display_name, classes="job-name")
        yield ProgressBar(total=100, show_eta=False, show_percentage=True, classes="job-progress")
        yield Static("", classes="job-status")
        yield Button("✕", classes="job-cancel-btn", variant="error")

    def update_from_job(self, job: Job) -> None:
        """Update the row from job state."""
        self._job = job
        
        # Update name if we have title now
        name_widget = self.query_one(".job-name", Static)
        name_widget.update(job.display_name)
        
        # Update progress
        progress_bar = self.query_one(".job-progress", ProgressBar)
        progress_bar.progress = job.progress
        
        # Update status with step info
        status_widget = self.query_one(".job-status", Static)
        
        # Calculate total steps and current step
        total_steps = 1  # Download always
        if job.include_conversion:
            total_steps += 1
        if job.include_upload:
            total_steps += 1
        
        step_info = {
            OperationState.FETCHING_METADATA: (0, "🔍"),
            OperationState.DOWNLOADING: (1, "⬇"),
            OperationState.CONVERTING: (2, "⚙"),
            OperationState.UPLOADING: (3 if job.include_conversion else 2, "⬆"),
            OperationState.COMPLETED: (0, "✓"),
            OperationState.CANCELLED: (0, "⏹"),
            OperationState.ERROR: (0, "✗"),
        }
        
        step, icon = step_info.get(job.state, (0, ""))
        
        if job.is_active and step > 0:
            # Show step counter for active download/convert/upload
            status_widget.update(f"{step}/{total_steps} {icon}")
        else:
            status_widget.update(icon)
        
        # Update cancel button
        cancel_btn = self.query_one(".job-cancel-btn", Button)
        cancel_btn.disabled = not job.is_active
        
        # Style based on state
        self.remove_class("completed", "error", "cancelled")
        if job.state == OperationState.COMPLETED:
            self.add_class("completed")
        elif job.state == OperationState.ERROR:
            self.add_class("error")
        elif job.state == OperationState.CANCELLED:
            self.add_class("cancelled")


class JobsPanel(Container):
    """Panel showing all active and recent jobs."""

    class CancelRequested(Message):
        """Message sent when cancel is requested for a job."""

        def __init__(self, job_id: str) -> None:
            self.job_id = job_id
            super().__init__()

    def __init__(self) -> None:
        """Initialize the jobs panel."""
        super().__init__()
        self._jobs: dict[str, Job] = {}

    def compose(self) -> ComposeResult:
        """Compose the jobs panel layout."""
        yield VerticalScroll(id="jobs-list")

    def add_job(self, job: Job) -> None:
        """Add a new job to the panel."""
        self._jobs[job.id] = job
        jobs_list = self.query_one("#jobs-list", VerticalScroll)
        row = JobRow(job)
        jobs_list.mount(row, before=0)
        self.remove_class("hidden")

    def update_job(self, job: Job) -> None:
        """Update an existing job."""
        self._jobs[job.id] = job
        try:
            row = self.query_one(f"#job-{job.id}", JobRow)
            row.update_from_job(job)
        except Exception:
            pass
        
        # Auto-remove completed jobs after a delay (keep last 3)
        self._cleanup_old_jobs()

    def _cleanup_old_jobs(self) -> None:
        """Remove old finished jobs, keeping only recent ones."""
        finished_jobs = [j for j in self._jobs.values() if j.is_finished]
        active_jobs = [j for j in self._jobs.values() if j.is_active]
        
        # Keep max 3 finished jobs
        if len(finished_jobs) > 3:
            # Remove oldest finished jobs
            for job in finished_jobs[3:]:
                self.remove_job(job.id)
        
        # Hide panel if no jobs
        if not active_jobs and not finished_jobs:
            self.add_class("hidden")

    def remove_job(self, job_id: str) -> None:
        """Remove a job from the panel."""
        if job_id in self._jobs:
            del self._jobs[job_id]
        try:
            row = self.query_one(f"#job-{job_id}", JobRow)
            row.remove()
        except Exception:
            pass

    def get_job(self, job_id: str) -> Job | None:
        """Get a job by ID."""
        return self._jobs.get(job_id)

    def get_active_jobs(self) -> list[Job]:
        """Get all active jobs."""
        return [j for j in self._jobs.values() if j.is_active]

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle cancel button press."""
        if "job-cancel-btn" in event.button.classes:
            # Find the job ID from parent
            row = event.button.parent
            if row and row.id and row.id.startswith("job-"):
                job_id = row.id[4:]  # Remove "job-" prefix
                self.post_message(self.CancelRequested(job_id))

    def on_mount(self) -> None:
        """Hide panel initially."""
        self.add_class("hidden")
