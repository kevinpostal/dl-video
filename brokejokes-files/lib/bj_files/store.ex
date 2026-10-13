defmodule BjFiles.Store do
  @moduledoc """
  Flat directory of uploaded files named `<random id>.<ext>`.

  Names are generated here, never taken from the client, so a stored name is
  always safe to join onto the data directory.
  """

  @name ~r/\A[A-Za-z0-9_-]{8,64}(\.[a-z0-9]{1,10})?\z/

  # Only media is stored: anything a browser renders as a document (html, svg,
  # xml, pdf...) would run script on this origin.
  @media ~w(.mp4 .m4v .mov .webm .mkv .avi .3gp .mpg .mpeg .ts .flv .ogv .gif .m4a .mp3 .aac .wav .flac .ogg .opus .jpg .jpeg .png .webp)

  def dir, do: Application.fetch_env!(:bj_files, :data_dir)

  @doc """
  Moves an uploaded temp file into the store; returns the stored name, or
  `{:error, :unsupported_type}` unless the filename has a media extension.
  """
  def put(tmp_path, original_filename) do
    ext = extension(original_filename)

    if ext in @media, do: store(tmp_path, random_id() <> ext), else: {:error, :unsupported_type}
  end

  defp store(tmp_path, name) do
    dest = Path.join(dir(), name)

    # Plug deletes its temp file when the request ends; copy instead of rename
    # because the temp dir may sit on another filesystem than the data volume.
    case File.rename(tmp_path, dest) do
      :ok -> {:ok, name}
      {:error, :exdev} -> with :ok <- File.cp(tmp_path, dest), do: {:ok, name}
      {:error, reason} -> {:error, reason}
    end
  end

  @doc "Absolute path for a stored name, or :error when the name is invalid or missing."
  def path(name) do
    if Regex.match?(@name, name) do
      path = Path.join(dir(), name)
      if File.regular?(path), do: {:ok, path}, else: :error
    else
      :error
    end
  end

  defp random_id, do: :crypto.strong_rand_bytes(9) |> Base.url_encode64(padding: false)

  defp extension(filename) do
    ext = filename |> to_string() |> Path.extname() |> String.downcase()
    if Regex.match?(~r/\A\.[a-z0-9]{1,10}\z/, ext), do: ext, else: ""
  end
end
