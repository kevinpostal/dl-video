defmodule BjFiles.Application do
  @moduledoc false
  use Application

  @impl true
  def start(_type, _args) do
    File.mkdir_p!(BjFiles.Store.dir())

    children =
      if Application.get_env(:bj_files, :server, true) do
        [{Bandit, plug: BjFiles.Router, port: Application.fetch_env!(:bj_files, :port)}]
      else
        []
      end

    Supervisor.start_link(children, strategy: :one_for_one, name: BjFiles.Supervisor)
  end
end
