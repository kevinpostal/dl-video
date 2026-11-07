defmodule BjFiles.Share do
  @moduledoc """
  Public URLs, the ready API payload and the page view model for a stored name.

  Every absolute URL is built from the configured `public_url`, never from the
  request's Host header. Derivatives are only advertised once
  `BjFiles.Media.asset/2` can actually serve them.
  """

  # Same shape as the names `BjFiles.Store` generates; used where the original
  # may legitimately be gone (status of a failed upload).
  @name ~r/\A[A-Za-z0-9_-]{8,64}(\.[a-z0-9]{1,10})?\z/

  @video_exts ~w(.mp4 .m4v .mov .webm .mkv .avi .3gp .mpg .mpeg .ts .flv .ogv)
  @image_exts ~w(.gif .jpg .jpeg .png .webp)
  @audio_exts ~w(.m4a .mp3 .aac .wav .flac .ogg .opus)

  # Formats a browser can usually render straight from the original, used only
  # for legacy files that predate metadata.
  @inline_video_exts ~w(.mp4 .m4v .mov .webm)

  def valid_name?(name) when is_binary(name), do: Regex.match?(@name, name)
  def valid_name?(_), do: false

  def base_url, do: :bj_files |> Application.fetch_env!(:public_url) |> String.trim_trailing("/")

  def share_path(name), do: "/s/" <> name
  def original_path(name), do: "/f/" <> name
  def download_path(name), do: "/d/" <> name
  def preview_path(name), do: "/v/" <> name <> ".mp4"
  def poster_path(name), do: "/p/" <> name <> ".jpg"
  def embed_path(name), do: "/embed/" <> name

  def url(path), do: base_url() <> path
  def status_url(name), do: url("/status/" <> name)

  @doc "Final JSON returned by the upload and status APIs once a name is ready."
  def ready_payload(name, meta) do
    %{
      url: url(share_path(name)),
      download_url: url(original_path(name)),
      preview_url: if(meta["preview"] == true and asset_ready?(name, :preview), do: url(preview_path(name))),
      name: name
    }
  end

  @doc """
  Absolute path of a published derivative. Requires the original to still be
  stored so orphaned artifacts are never served.
  """
  def asset(name, kind) when kind in [:preview, :poster] do
    with {:ok, _original} <- BjFiles.Store.path(name),
         {:ok, path} <- BjFiles.Media.asset(name, kind),
         true <- File.regular?(path) do
      {:ok, path}
    else
      _ -> :error
    end
  end

  defp asset_ready?(name, kind), do: match?({:ok, _}, asset(name, kind))

  @doc "View model for a name with ready metadata."
  def ready_view(name, original_path, meta) do
    kind = if meta["kind"] in ~w(video image audio), do: meta["kind"], else: kind_from_ext(name)
    {width, height} = dims(meta["width"], meta["height"])

    %{
      state: :ready,
      name: name,
      title: title(meta["title"], kind),
      kind: kind,
      width: width,
      height: height,
      duration: duration(meta["duration"]),
      preview?: meta["preview"] == true and asset_ready?(name, :preview),
      poster?: meta["poster"] == true and asset_ready?(name, :poster),
      original_inline?: kind in ["image", "audio"],
      original_bytes: file_size(original_path)
    }
  end

  @doc "View model for an original stored before metadata existed (or whose backfill failed)."
  def legacy_view(name, original_path) do
    kind = kind_from_ext(name)
    ext = Path.extname(name)

    %{
      state: :legacy,
      name: name,
      title: title(nil, kind),
      kind: kind,
      width: nil,
      height: nil,
      duration: nil,
      preview?: false,
      poster?: false,
      original_inline?: kind in ["image", "audio"] or ext in @inline_video_exts,
      original_bytes: file_size(original_path)
    }
  end

  @doc """
  `content-disposition` for downloading the original. The filename comes from
  sanitised metadata (or the stored name) and is reduced to a quoted ASCII form
  plus an RFC 8187 `filename*`, so nothing raw reaches the header.
  """
  def attachment_disposition(name, title) do
    ext = Path.extname(name)
    stem = clean_filename(title) || Path.rootname(name)
    ascii = ascii_filename(stem) || Path.rootname(name)
    encoded = URI.encode(stem <> ext, &URI.char_unreserved?/1)

    ~s(attachment; filename="#{ascii}#{ext}"; filename*=UTF-8''#{encoded})
  end

  defp clean_filename(title) when is_binary(title) do
    cleaned =
      title
      |> String.replace(~r/[\p{C}\/\\:*?"<>|;]+/u, " ")
      |> String.replace(~r/\s+/u, " ")
      |> String.trim()
      |> String.trim_leading(".")
      |> String.slice(0, 120)
      |> String.trim()

    if cleaned == "", do: nil, else: cleaned
  end

  defp clean_filename(_), do: nil

  defp ascii_filename(stem) do
    ascii =
      stem
      |> :unicode.characters_to_nfd_binary()
      |> String.replace(~r/\p{Mn}/u, "")
      |> String.replace(~r/[^A-Za-z0-9 ._()\-]+/, "_")
      |> String.trim("_")
      |> String.trim()

    if ascii == "", do: nil, else: ascii
  end

  defp kind_from_ext(name) do
    ext = name |> Path.extname() |> String.downcase()

    cond do
      ext in @video_exts -> "video"
      ext in @image_exts -> "image"
      ext in @audio_exts -> "audio"
      true -> "file"
    end
  end

  defp title(title, kind) do
    case clean_title(title) do
      nil -> "Shared " <> kind
      cleaned -> cleaned
    end
  end

  defp clean_title(title) when is_binary(title) do
    cleaned =
      title
      |> String.replace(~r/\p{C}+/u, " ")
      |> String.replace(~r/\s+/u, " ")
      |> String.trim()
      |> String.slice(0, 200)

    if cleaned == "", do: nil, else: cleaned
  end

  defp clean_title(_), do: nil

  defp dims(w, h) when is_integer(w) and is_integer(h) and w > 0 and h > 0, do: {w, h}
  defp dims(_, _), do: {nil, nil}

  defp duration(d) when is_number(d) and d > 0, do: d
  defp duration(_), do: nil

  defp file_size(path) do
    case File.stat(path) do
      {:ok, %File.Stat{size: size}} -> size
      _ -> nil
    end
  end
end
