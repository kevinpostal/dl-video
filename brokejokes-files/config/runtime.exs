import Config

if config_env() == :prod do
  config :bj_files,
    port: String.to_integer(System.get_env("PORT", "4000")),
    data_dir: System.get_env("DATA_DIR", "/data"),
    public_url: System.fetch_env!("PUBLIC_URL"),
    upload_token: System.fetch_env!("UPLOAD_TOKEN"),
    max_upload_bytes: String.to_integer(System.get_env("MAX_UPLOAD_BYTES", "524288000"))
end
