defmodule BjFiles.Media.Probe do
  @moduledoc """
  ffprobe wrapper and the facts the preparation pipeline needs about a file.

  Untrusted input hardening, applied to every ffprobe/ffmpeg input:

    * the input is opened through the `file` protocol only
      (`-protocol_whitelist file`), so no network or pipe access
    * the demuxer must be one of `demuxers/0`: self-contained media formats
      only, no playlists or reference formats (hls, dash, concat, ffconcat, ...)
    * MOV/MP4 external data references stay at their disabled defaults
      (`enable_drefs=0`, `use_absolute_path=0`)
    * callers hand ffmpeg an extension-less symlink, so detection is by
      content, never by the client's filename
  """

  alias BjFiles.Media.Command

  @demuxers ~w(mov mp4 m4a 3gp 3g2 mj2 matroska webm avi mpegts mpeg flv ogg mp3 aac wav flac gif png_pipe jpeg_pipe webp_pipe)
  @image_formats ~w(png_pipe jpeg_pipe webp_pipe)
  @max_json 4 * 1024 * 1024

  def demuxers, do: Enum.join(@demuxers, ",")

  @doc "Input options that must precede every `-i` of untrusted media."
  # max_pixels bounds what any decoder may allocate per frame, even if the
  # container lied about the size the probe-time limits were checked against.
  def input_args(path) do
    ["-max_pixels", "64000000", "-protocol_whitelist", "file", "-format_whitelist", demuxers(), "-i", "file:" <> path]
  end

  @doc """
  Runs ffprobe. `{:error, :invalid_media}` when the file is not a supported,
  readable media file; `{:error, :timeout}` past the deadline.
  """
  def run(ffprobe, path, deadline, format \\ nil) when format in [nil, :jpeg] do
    # Generated .jpg files otherwise select image2 by suffix. Force the
    # self-contained JPEG demuxer rather than enabling image2 for untrusted input.
    format_args = if format == :jpeg, do: ["-f", "jpeg_pipe"], else: []
    args =
      ["-v", "quiet", "-show_error", "-show_format", "-show_streams", "-print_format", "json"] ++
        format_args ++ input_args(path)

    case Command.run(ffprobe, args, deadline: deadline, output: :all, max_output: @max_json, stderr: false) do
      {:ok, json} -> decode(json)
      {:error, :timeout} -> {:error, :timeout}
      {:error, _} -> {:error, :invalid_media}
    end
  end

  defp decode(json) do
    case Jason.decode(json) do
      {:ok, %{"error" => _}} -> {:error, :invalid_media}
      {:ok, %{"format" => %{} = format, "streams" => streams}} when is_list(streams) -> {:ok, %{format: format, streams: streams}}
      _ -> {:error, :invalid_media}
    end
  end

  @doc "Demuxer name ffprobe settled on (first entry of a list such as `mov,mp4,...`)."
  def format_name(%{format: f}), do: f |> Map.get("format_name", "") |> String.split(",") |> hd()

  def image_format?(info), do: format_name(info) in @image_formats

  @doc "Video streams that are real pictures over time (not embedded cover art)."
  def video_streams(%{streams: s}), do: Enum.filter(s, &(&1["codec_type"] == "video" and not attached_pic?(&1)))

  def cover_streams(%{streams: s}), do: Enum.filter(s, &(&1["codec_type"] == "video" and attached_pic?(&1)))

  def audio_streams(%{streams: s}), do: Enum.filter(s, &(&1["codec_type"] == "audio"))

  defp attached_pic?(stream), do: get_in(stream, ["disposition", "attached_pic"]) == 1

  @doc "Finite positive duration in seconds from the container, else the stream; nil if unknown."
  def duration(%{format: f}, stream \\ nil) do
    [f["duration"], stream && stream["duration"]]
    |> Enum.map(&number/1)
    |> Enum.find(&(is_float(&1) and &1 > 0 and &1 < 1.0e7))
  end

  def number(nil), do: nil
  def number(n) when is_number(n), do: n / 1

  def number(s) when is_binary(s) do
    case Float.parse(s) do
      {f, ""} -> f
      _ -> nil
    end
  end

  def int(n) when is_integer(n), do: n
  def int(_), do: nil

  @doc "Display rotation in degrees (0, 90, 180, 270) from the display matrix."
  def rotation(stream) do
    side =
      stream
      |> Map.get("side_data_list", [])
      |> Enum.find_value(fn sd -> is_map(sd) && number(sd["rotation"]) end)

    deg = side || number(get_in(stream, ["tags", "rotate"])) || 0.0
    rem(rem(round(deg), 360) + 360, 360)
  end

  @doc "Frame size as shown to the viewer (rotation applied)."
  def display_size(stream) do
    {w, h} = {int(stream["width"]), int(stream["height"])}
    if rotation(stream) in [90, 270], do: {h, w}, else: {w, h}
  end

  @doc "True for PQ/HLG transfer or BT.2020 primaries: needs real conversion to BT.709 SDR."
  def wide_or_hdr?(stream) do
    stream["color_transfer"] in ["smpte2084", "arib-std-b67"] or
      stream["color_primaries"] in ["bt2020"] or
      stream["color_space"] in ["bt2020nc", "bt2020c", "ictcp"]
  end

  def hdr_transfer?(stream), do: stream["color_transfer"] in ["smpte2084", "arib-std-b67"]

  @doc "Dolby Vision without a backwards-compatible base layer (profile 5) cannot be converted."
  def dolby_vision_only?(stream) do
    stream
    |> Map.get("side_data_list", [])
    |> Enum.any?(fn sd ->
      is_map(sd) and to_string(sd["side_data_type"]) =~ "DOVI" and sd["dv_bl_signal_compatibility_id"] == 0
    end)
  end

  def frame_rate(stream) do
    with s when is_binary(s) <- stream["avg_frame_rate"],
         [n, d] <- String.split(s, "/"),
         {n, ""} <- Integer.parse(n),
         {d, ""} when d > 0 <- Integer.parse(d) do
      n / d
    else
      _ -> nil
    end
  end

  def square_pixels?(stream), do: stream["sample_aspect_ratio"] in [nil, "1:1", "0:1"]

  @doc """
  Whether ISO-BMFF top-level boxes put `moov` before `mdat` (progressive
  playback without range requests). Reads box headers only, bounded.
  """
  def faststart?(path) do
    case File.open(path, [:read, :binary]) do
      {:ok, io} ->
        try do
          {:ok, %File.Stat{size: size}} = File.stat(path)
          scan_boxes(io, 0, size, 64)
        after
          File.close(io)
        end

      _ ->
        false
    end
  end

  defp scan_boxes(_io, _pos, _size, 0), do: false

  defp scan_boxes(io, pos, size, budget) do
    case :file.pread(io, pos, 16) do
      {:ok, <<len::32, type::binary-size(4), rest::binary>>} ->
        box_len =
          case {len, rest} do
            {1, <<large::64>>} -> large
            {0, _} -> size - pos
            _ -> len
          end

        cond do
          type == "moov" -> true
          type == "mdat" -> false
          box_len < 8 -> false
          true -> scan_boxes(io, pos + box_len, size, budget - 1)
        end

      _ ->
        false
    end
  end

  @doc """
  Whether the ffmpeg build has the filters for real HDR -> SDR tone mapping
  (zscale + tonemap). Checked once per VM.
  """
  def tone_mapping?(ffmpeg) do
    key = {__MODULE__, :tone_mapping, ffmpeg}

    case :persistent_term.get(key, :unknown) do
      :unknown ->
        deadline = System.monotonic_time(:millisecond) + 10_000

        available =
          case Command.run(ffmpeg, ["-hide_banner", "-filters"], deadline: deadline, output: :all, max_output: 1024 * 1024) do
            {:ok, out} -> out =~ ~r/^\s*\S+\s+zscale\s/m and out =~ ~r/^\s*\S+\s+tonemap\s/m
            _ -> false
          end

        :persistent_term.put(key, available)
        available

      known ->
        known
    end
  end
end
