defmodule BjFiles.Media.Gate do
  @moduledoc """
  Admission control for media preparation.

  At most `:media_max_concurrency` (default 1) processes hold the gate; further
  requests get `{:error, :busy}` instead of queueing. Each holder is monitored:
  when it exits for any reason its tracked ffmpeg/ffprobe OS processes are
  killed, its scratch directory is removed and its slot is freed, so a crashed
  or killed preparation cannot leak capacity, CPU or disk.
  """
  use GenServer

  alias BjFiles.Media.Command

  def start_link(_opts), do: GenServer.start_link(__MODULE__, :ok, name: __MODULE__)

  @doc "Admits `pid` (default: caller) if a slot is free."
  @spec acquire(pid()) :: :ok | {:error, :busy}
  def acquire(pid \\ self()), do: GenServer.call(__MODULE__, {:acquire, pid})

  @doc "Frees `pid`'s slot after it finished normally; its scratch dir is not touched."
  @spec release(pid()) :: :ok
  def release(pid \\ self()), do: GenServer.call(__MODULE__, {:release, pid})

  @doc "Records the caller's scratch directory, removed if the caller dies holding the gate."
  @spec put_work_dir(Path.t()) :: :ok
  def put_work_dir(dir), do: GenServer.call(__MODULE__, {:work_dir, self(), dir})

  @doc "Records an OS process run by the caller, killed if the caller dies holding the gate."
  @spec track(pos_integer()) :: :ok
  def track(os_pid), do: call_if_running({:track, self(), os_pid})

  @spec untrack(pos_integer()) :: :ok
  def untrack(os_pid), do: call_if_running({:untrack, self(), os_pid})

  @doc "Number of currently admitted holders."
  @spec busy() :: non_neg_integer()
  def busy, do: GenServer.call(__MODULE__, :busy)

  # Command.run is usable outside an admitted preparation (and in a release
  # `eval` without the application); tracking is then simply skipped.
  defp call_if_running(msg) do
    if Process.whereis(__MODULE__), do: GenServer.call(__MODULE__, msg), else: :ok
  end

  @impl true
  def init(:ok), do: {:ok, %{}}

  @impl true
  def handle_call({:acquire, pid}, _from, holders) do
    cond do
      Map.has_key?(holders, pid) ->
        {:reply, {:error, :busy}, holders}

      map_size(holders) >= limit() ->
        {:reply, {:error, :busy}, holders}

      true ->
        ref = Process.monitor(pid)
        {:reply, :ok, Map.put(holders, pid, %{ref: ref, dir: nil, os_pids: MapSet.new()})}
    end
  end

  def handle_call({:release, pid}, _from, holders) do
    case Map.pop(holders, pid) do
      {nil, holders} ->
        {:reply, :ok, holders}

      {holder, holders} ->
        Process.demonitor(holder.ref, [:flush])
        Enum.each(holder.os_pids, &Command.kill/1)
        {:reply, :ok, holders}
    end
  end

  def handle_call({:work_dir, pid, dir}, _from, holders) do
    {:reply, :ok, update(holders, pid, &%{&1 | dir: dir})}
  end

  def handle_call({:track, pid, os_pid}, _from, holders) do
    {:reply, :ok, update(holders, pid, &%{&1 | os_pids: MapSet.put(&1.os_pids, os_pid)})}
  end

  def handle_call({:untrack, pid, os_pid}, _from, holders) do
    {:reply, :ok, update(holders, pid, &%{&1 | os_pids: MapSet.delete(&1.os_pids, os_pid)})}
  end

  def handle_call(:busy, _from, holders), do: {:reply, map_size(holders), holders}

  @impl true
  def handle_info({:DOWN, _ref, :process, pid, _reason}, holders) do
    case Map.pop(holders, pid) do
      {nil, holders} ->
        {:noreply, holders}

      {holder, holders} ->
        Enum.each(holder.os_pids, &Command.kill/1)
        if holder.dir, do: File.rm_rf(holder.dir)
        {:noreply, holders}
    end
  end

  defp update(holders, pid, fun) do
    case holders do
      %{^pid => holder} -> Map.put(holders, pid, fun.(holder))
      _ -> holders
    end
  end

  defp limit, do: max(Application.get_env(:bj_files, :media_max_concurrency, 1), 1)
end
