import Config

if config_env() == :prod do
  config :bj_files,
    port: String.to_integer(System.get_env("PORT", "4000")),
    data_dir: System.get_env("DATA_DIR", "/data"),
    public_url: System.fetch_env!("PUBLIC_URL"),
    upload_token: System.fetch_env!("UPLOAD_TOKEN"),
    max_upload_bytes: String.to_integer(System.get_env("MAX_UPLOAD_BYTES", "524288000")),
    media_max_concurrency: String.to_integer(System.get_env("MEDIA_MAX_CONCURRENCY", "1")),
    media_timeout_ms: String.to_integer(System.get_env("MEDIA_TIMEOUT_SECONDS", "600")) * 1000,
    media_threads: String.to_integer(System.get_env("MEDIA_THREADS", "2"))
end
