import Config

config :bj_files,
  port: 4000,
  data_dir: Path.expand("../tmp/data", __DIR__),
  public_url: "http://localhost:4000",
  upload_token: "dev-token",
  max_upload_bytes: 500 * 1024 * 1024,
  # Media preparation (BjFiles.Media): admitted concurrent preparations (no
  # queue beyond this: extra uploads get 503 busy), wall clock per preparation,
  # ffmpeg/x264 threads, and the hard byte cap of a video preview.
  media_max_concurrency: 1,
  media_timeout_ms: 600_000,
  media_threads: 2,
  media_preview_max_bytes: 19 * 1024 * 1024,
  # nil = look up ffmpeg/ffprobe on PATH
  ffmpeg_path: nil,
  ffprobe_path: nil

config :logger, :default_formatter, format: "$time [$level] $message\n"

if config_env() == :test do
  config :bj_files,
    server: false,
    data_dir: Path.join(System.tmp_dir!(), "bj_files_test"),
    public_url: "https://files.example.com",
    upload_token: "test-token",
    max_upload_bytes: 1024,
    media_timeout_ms: 120_000

  config :logger, level: :warning
end
