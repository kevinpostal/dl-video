defmodule BjFiles.Media.Command do
  @moduledoc """
  Runs one external executable with an argument list (never a shell), a hard
  wall-clock deadline and a bounded amount of captured output.

  The OS process is killed when the deadline passes or its output exceeds the
  cap. While it runs, its OS pid is registered with `BjFiles.Media.Gate`, which
  kills it if the calling process dies first.
  """

  alias BjFiles.Media.Gate

  @doc """
  Options:

    * `:deadline` (required) - `System.monotonic_time(:millisecond)` value after
      which the process is killed and `{:error, :timeout}` returned
    * `:output` - `:all` keeps everything and fails with `:output_too_large`
      past `:max_output`; `:tail` (default) keeps only the last `:max_output` bytes
    * `:max_output` - byte cap, default 16 KiB
    * `:stderr` - merge stderr into the captured output (default `true`); when
      `false` stderr is inherited from the VM
    * `:cd` - working directory for the process
  """
  @spec run(Path.t(), [String.t()], keyword()) ::
          {:ok, binary()}
          | {:error, :timeout | :output_too_large | {:exit, non_neg_integer(), binary()}}
  def run(executable, args, opts) when is_list(args) do
    deadline = Keyword.fetch!(opts, :deadline)
    mode = Keyword.get(opts, :output, :tail)
    max = Keyword.get(opts, :max_output, 16 * 1024)
    stderr = if Keyword.get(opts, :stderr, true), do: [:stderr_to_stdout], else: []
    cd = if dir = Keyword.get(opts, :cd), do: [cd: dir], else: []

    if deadline - now() <= 0 do
      {:error, :timeout}
    else
      port =
        Port.open(
          {:spawn_executable, executable},
          [:binary, :exit_status, :use_stdio, :hide, args: args] ++ stderr ++ cd
        )

      {:os_pid, os_pid} = Port.info(port, :os_pid)
      Gate.track(os_pid)

      try do
        collect(port, os_pid, deadline, mode, max, [], 0)
      after
        Gate.untrack(os_pid)
      end
    end
  end

  defp collect(port, os_pid, deadline, mode, max, acc, size) do
    if now() >= deadline do
      stop(port, os_pid)
      {:error, :timeout}
    else
      receive do
        {^port, {:data, data}} ->
          size = size + byte_size(data)

          cond do
            mode == :all and size > max ->
              stop(port, os_pid)
              {:error, :output_too_large}

            mode == :tail and size > 2 * max ->
              # Collapse occasionally so memory stays O(max) however much is written.
              tail = last_bytes(IO.iodata_to_binary([acc, data]), max)
              collect(port, os_pid, deadline, mode, max, [tail], byte_size(tail))

            true ->
              collect(port, os_pid, deadline, mode, max, [acc, data], size)
          end

        {^port, {:exit_status, 0}} ->
          {:ok, output(acc, mode, max)}

        {^port, {:exit_status, status}} ->
          {:error, {:exit, status, last_bytes(IO.iodata_to_binary(acc), max)}}
      after
        max(deadline - now(), 0) ->
          stop(port, os_pid)
          {:error, :timeout}
      end
    end
  end

  defp output(acc, :all, _max), do: IO.iodata_to_binary(acc)
  defp output(acc, :tail, max), do: last_bytes(IO.iodata_to_binary(acc), max)

  defp last_bytes(bin, max) when byte_size(bin) <= max, do: bin
  defp last_bytes(bin, max), do: binary_part(bin, byte_size(bin) - max, max)

  defp stop(port, os_pid) do
    kill(os_pid)

    try do
      Port.close(port)
    rescue
      ArgumentError -> :ok
    end

    flush(port)
  end

  defp flush(port) do
    receive do
      {^port, _} -> flush(port)
    after
      0 -> :ok
    end
  end

  @doc "Sends SIGKILL to an OS process; a process that already exited is ignored."
  @spec kill(pos_integer()) :: :ok
  def kill(os_pid) when is_integer(os_pid) and os_pid > 0 do
    case System.find_executable("kill") do
      nil -> :ok
      kill -> System.cmd(kill, ["-KILL", Integer.to_string(os_pid)], stderr_to_stdout: true)
    end

    :ok
  end

  defp now, do: System.monotonic_time(:millisecond)
end
