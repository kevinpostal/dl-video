import Config

config :bj_files,
  port: 4000,
  data_dir: Path.expand("../tmp/data", __DIR__),
  public_url: "http://localhost:4000",
  upload_token: "dev-token",
  max_upload_bytes: 500 * 1024 * 1024

config :logger, :default_formatter, format: "$time [$level] $message\n"

if config_env() == :test do
  config :bj_files,
    server: false,
    data_dir: Path.join(System.tmp_dir!(), "bj_files_test"),
    public_url: "https://files.example.com",
    upload_token: "test-token",
    max_upload_bytes: 1024

  config :logger, level: :warning
end
