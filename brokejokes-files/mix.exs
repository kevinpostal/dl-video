defmodule BjFiles.MixProject do
  use Mix.Project

  def project do
    [
      app: :bj_files,
      version: "0.1.0",
      elixir: "~> 1.17",
      start_permanent: Mix.env() == :prod,
      deps: deps(),
      releases: [bj_files: [include_executables_for: [:unix]]]
    ]
  end

  def application do
    [extra_applications: [:logger, :crypto], mod: {BjFiles.Application, []}]
  end

  defp deps do
    [
      {:bandit, "~> 1.5"},
      {:plug, "~> 1.16"},
      {:jason, "~> 1.4"}
    ]
  end
end
