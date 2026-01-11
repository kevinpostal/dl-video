"""Download speed chart component using plotext."""

from collections import deque
from datetime import datetime

from textual.app import ComposeResult
from textual.containers import Container
from textual.widgets import Static

try:
    from textual_plotext import PlotextPlot
    HAS_PLOTEXT = True
except ImportError:
    HAS_PLOTEXT = False


class SpeedChart(Container):
    """Real-time download speed chart."""

    DEFAULT_CSS = """
    SpeedChart {
        height: 10;
        width: 100%;
        background: $surface-darken-1;
    }
    
    SpeedChart PlotextPlot {
        height: 100%;
        width: 100%;
    }
    
    SpeedChart .no-plotext {
        color: $text-muted;
        text-align: center;
        content-align: center middle;
        height: 100%;
    }
    """

    def __init__(self, max_points: int = 60, **kwargs) -> None:
        """Initialize the speed chart.
        
        Args:
            max_points: Maximum number of data points to display.
            **kwargs: Additional arguments passed to Container.
        """
        super().__init__(**kwargs)
        self._max_points = max_points
        self._speeds: deque[float] = deque(maxlen=max_points)
        self._times: deque[int] = deque(maxlen=max_points)
        self._start_time: datetime | None = None
        self._plot: PlotextPlot | None = None

    def compose(self) -> ComposeResult:
        if HAS_PLOTEXT:
            self._plot = PlotextPlot()
            yield self._plot
        else:
            yield Static("Speed chart requires textual-plotext", classes="no-plotext")

    def on_mount(self) -> None:
        """Initialize the plot."""
        if self._plot:
            self._update_plot()

    def add_speed(self, speed_mbps: float) -> None:
        """Add a speed measurement.
        
        Args:
            speed_mbps: Download speed in MB/s.
        """
        if not HAS_PLOTEXT or not self._plot:
            return
        
        if self._start_time is None:
            self._start_time = datetime.now()
        
        elapsed = int((datetime.now() - self._start_time).total_seconds())
        self._times.append(elapsed)
        self._speeds.append(speed_mbps)
        self._update_plot()

    def _update_plot(self) -> None:
        """Update the plot with current data."""
        if not self._plot:
            return
        
        plt = self._plot.plt
        plt.clear_figure()
        plt.theme("dark")
        
        if self._speeds:
            times = list(self._times)
            speeds = list(self._speeds)
            plt.plot(times, speeds, marker="braille")
            plt.xlabel("Time (s)")
            plt.ylabel("MB/s")
            
            # Show current and peak speed
            current = speeds[-1] if speeds else 0
            peak = max(speeds) if speeds else 0
            plt.title(f"Speed: {current:.1f} MB/s | Peak: {peak:.1f} MB/s")
        else:
            plt.title("Download Speed")
            plt.xlabel("Time (s)")
            plt.ylabel("MB/s")
        
        self._plot.refresh()

    def reset(self) -> None:
        """Reset the chart for a new download."""
        self._speeds.clear()
        self._times.clear()
        self._start_time = None
        if self._plot:
            self._update_plot()

    def clear(self) -> None:
        """Clear the chart completely."""
        self.reset()
