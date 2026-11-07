defmodule BjFiles.Media.Jobs do
  @moduledoc """
  Asynchronous preparation of new uploads with durable state.

  `enqueue/3` admits a job only when `BjFiles.Media.Gate` has a free slot
  (there is no queue: a full gate is `{:error, :busy}`), then writes
  `.previews/.jobs/<name>.pending` (fsynced) before returning `:ok`. Every
  admitted job settles exactly once:

    * success - `BjFiles.Media.prepare/3` published ready metadata; the
      pending marker is removed
    * failure, crash or watchdog kill (`:media_timeout_ms` + 30 s) - a
      `<name>.failed` marker records a public reason (`invalid_media`,
      `unsupported_media`, `timeout`, `processing_failed`), the original and
      any partial artifacts are deleted, the pending marker is removed

  Workers are linked to this coordinator, which traps exits: a worker crash
  never takes it down, and if the coordinator itself dies its workers die too
  (the gate then kills their ffmpeg processes and frees capacity). On start,
  pending markers left by a previous VM are re-admitted while capacity allows;
  the rest are failed explicitly, so nothing stays pending forever. Failed
  markers older than 7 days are pruned at start.
  """
  use GenServer
  require Logger

  alias BjFiles.Media
  alias BjFiles.Media.Gate
  alias BjFiles.Store

  @public_reasons ~w(invalid_media unsupported_media timeout processing_failed)
  @failed_retention_s 7 * 24 * 3600
  @watchdog_grace_ms 30_000

  def start_link(_opts), do: GenServer.start_link(__MODULE__, :ok, name: __MODULE__)

  @spec enqueue(Path.t(), String.t(), String.t()) :: :ok | {:error, term()}
  def enqueue(path, name, original_filename) do
    GenServer.call(__MODULE__, {:enqueue, path, name, to_string(original_filename)})
  end

  @doc "Whether an upload of `name` was admitted and has not settled yet."
  @spec pending?(String.t()) :: boolean()
  def pending?(name), do: Media.valid_name?(name) and File.regular?(marker(name, :pending))

  @doc "`{:error, public_reason}` when the upload of `name` failed, else `:error`."
  @spec failure(String.t()) :: {:error, atom()} | :error
  def failure(name) do
    with true <- Media.valid_name?(name),
         {:ok, json} <- File.read(marker(name, :failed)),
         {:ok, %{"reason" => reason}} when reason in @public_reasons <- Jason.decode(json) do
      {:error, String.to_existing_atom(reason)}
    else
      _ -> :error
    end
  end

  # --- server ------------------------------------------------------------------

  @impl true
  def init(:ok) do
    Process.flag(:trap_exit, true)
    {:ok, %{jobs: %{}}, {:continue, :recover}}
  end

  @impl true
  def handle_continue(:recover, state) do
    prune_failed()

    state =
      Enum.reduce(pending_names(), state, fn name, state ->
        filename = pending_filename(name)

        with {:ok, path} <- Store.path(name),
             {:ok, state} <- start(state, path, name, filename, false) do
          Logger.info("media job #{name}: resumed after restart")
          state
        else
          reason ->
            Logger.warning("media job #{name}: cannot resume after restart (#{inspect(reason)})")
            settle_failure(name, :processing_failed)
            state
        end
      end)

    {:noreply, state}
  end

  @impl true
  def handle_call({:enqueue, path, name, filename}, _from, state) do
    cond do
      not Media.valid_name?(name) ->
        {:reply, {:error, :invalid_name}, state}

      Enum.any?(state.jobs, fn {_, job} -> job.name == name end) or pending?(name) ->
        {:reply, {:error, :already_pending}, state}

      true ->
        case start(state, path, name, filename, true) do
          {:ok, state} -> {:reply, :ok, state}
          {:error, reason} -> {:reply, {:error, reason}, state}
        end
    end
  end

  @impl true
  def handle_info({:EXIT, pid, reason}, state) do
    case Map.pop(state.jobs, pid) do
      {nil, _} ->
        {:noreply, state}

      {job, jobs} ->
        Process.cancel_timer(job.timer)
        Gate.release(pid)
        settle(job, result(reason, job))
        {:noreply, %{state | jobs: jobs}}
    end
  end

  def handle_info({:watchdog, pid}, state) do
    case state.jobs do
      %{^pid => job} ->
        Logger.warning("media job #{job.name}: watchdog kill")
        Process.exit(pid, :kill)
        {:noreply, put_in(state.jobs[pid], %{job | timed_out: true})}

      _ ->
        {:noreply, state}
    end
  end

  def handle_info(_msg, state), do: {:noreply, state}

  # --- jobs ----------------------------------------------------------------------

  defp start(state, path, name, filename, write_marker?) do
    pid =
      spawn_link(fn ->
        receive do
          :go -> exit({:shutdown, {:prepared, Media.prepare_admitted(path, name, filename)}})
        end
      end)

    with :ok <- Gate.acquire(pid),
         :ok <- if(write_marker?, do: write_pending(name, filename), else: :ok) do
      send(pid, :go)
      timer = Process.send_after(self(), {:watchdog, pid}, Media.timeout_ms() + @watchdog_grace_ms)
      {:ok, put_in(state.jobs[pid], %{name: name, timer: timer, timed_out: false})}
    else
      error ->
        Process.unlink(pid)
        Process.exit(pid, :kill)
        Gate.release(pid)
        error
    end
  end

  defp result({:shutdown, {:prepared, {:ok, _meta}}}, _job), do: :ok
  defp result({:shutdown, {:prepared, {:error, reason}}}, _job), do: {:error, reason}
  defp result(_reason, %{timed_out: true}), do: {:error, :timeout}

  defp result(reason, job) do
    Logger.error("media job #{job.name}: worker crashed: #{inspect(reason, limit: 10)}")
    {:error, :processing_failed}
  end

  defp settle(job, :ok) do
    File.rm(marker(job.name, :pending))
    Logger.info("media job #{job.name}: ready")
  end

  defp settle(job, {:error, reason}) do
    # A worker killed right after publishing still produced a ready upload.
    case Media.load(job.name) do
      {:ok, _} -> settle(job, :ok)
      :error -> settle_failure(job.name, public_reason(reason))
    end
  end

  # Failed marker first, so status never reports an unknown name in between.
  defp settle_failure(name, reason) do
    write_marker(marker(name, :failed), %{"version" => 1, "reason" => Atom.to_string(reason), "failed_at" => now_iso()})
    File.rm_rf(Path.join(Media.previews_dir(), name))
    File.rm(marker(name, :pending))
    File.rm(Path.join(Store.dir(), name))
    Logger.warning("media job #{name}: failed (#{reason}); original removed")
  end

  defp public_reason(reason) when reason in [:invalid_media, :unsupported_media, :timeout], do: reason
  defp public_reason(_), do: :processing_failed

  # --- markers -------------------------------------------------------------------

  defp marker(name, :pending), do: Path.join(Media.jobs_dir(), name <> ".pending")
  defp marker(name, :failed), do: Path.join(Media.jobs_dir(), name <> ".failed")

  defp write_pending(name, filename) do
    write_marker(marker(name, :pending), %{"version" => 1, "original_filename" => String.replace_invalid(filename), "created_at" => now_iso()})
  end

  # Write + fsync a temp file, then rename: the marker is either absent or whole.
  defp write_marker(path, map) do
    tmp = path <> ".tmp"

    with :ok <- File.mkdir_p(Path.dirname(path)),
         :ok <- File.write(tmp, Jason.encode!(map), [:sync]),
         :ok <- File.rename(tmp, path) do
      :ok
    else
      {:error, reason} ->
        File.rm(tmp)
        {:error, {:io, reason}}
    end
  end

  defp pending_names do
    case File.ls(Media.jobs_dir()) do
      {:ok, entries} ->
        for entry <- Enum.sort(entries),
            String.ends_with?(entry, ".pending"),
            name = String.replace_suffix(entry, ".pending", ""),
            Media.valid_name?(name),
            do: name

      _ ->
        []
    end
  end

  defp pending_filename(name) do
    with {:ok, json} <- File.read(marker(name, :pending)),
         {:ok, %{"original_filename" => filename}} when is_binary(filename) <- Jason.decode(json) do
      filename
    else
      _ -> name
    end
  end

  defp prune_failed do
    cutoff = System.os_time(:second) - @failed_retention_s

    with {:ok, entries} <- File.ls(Media.jobs_dir()) do
      for entry <- entries, String.ends_with?(entry, [".failed", ".tmp"]) do
        path = Path.join(Media.jobs_dir(), entry)

        # Leftover temp markers are always garbage at start; failures expire.
        case File.stat(path, time: :posix) do
          {:ok, %File.Stat{mtime: mtime}} ->
            if String.ends_with?(entry, ".tmp") or mtime < cutoff, do: File.rm(path)

          _ ->
            :ok
        end
      end
    end

    :ok
  end

  defp now_iso, do: DateTime.utc_now() |> DateTime.truncate(:second) |> DateTime.to_iso8601()
end
