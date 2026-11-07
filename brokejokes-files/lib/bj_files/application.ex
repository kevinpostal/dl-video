defmodule BjFiles.Application do
  @moduledoc false
  use Application

  @impl true
  def start(_type, _args) do
    File.mkdir_p!(BjFiles.Store.dir())
    BjFiles.Media.cleanup_stale()

    server =
      if Application.get_env(:bj_files, :server, true) do
        [{Bandit, plug: BjFiles.Router, port: Application.fetch_env!(:bj_files, :port)}]
      else
        []
      end

    # If the gate dies, restart Jobs too: live workers must not outlive admission tracking.
    children = [BjFiles.Media.Gate, BjFiles.Media.Jobs | server]

    Supervisor.start_link(children, strategy: :rest_for_one, name: BjFiles.Supervisor)
  end
end
