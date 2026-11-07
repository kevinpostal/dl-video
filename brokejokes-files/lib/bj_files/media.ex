defmodule BjFiles.Media do
  @moduledoc """
  Share-ready metadata and derivatives for stored originals.

  For every stored name, `prepare/3` probes the original by content (never by
  extension or client MIME type), validates it, and publishes into the private
  directory `data_dir/.previews/<name>/`:

    * `meta.json` - schema-versioned metadata (see `load/1`)
    * `poster.jpg` - JPEG still at exactly the advertised `width`x`height`
    * `preview.mp4` - when the original itself is not share-safe: H.264
      (Baseline/Main/High, yuv420p, BT.709 SDR) + AAC, `+faststart`, long edge
      <= 1280, even dimensions, never upscaled, at most
      `:media_preview_max_bytes` (default 19 MiB, below Telegram's 20 MB fetch
      limit) as measured on disk

  The original is only read, never modified. Artifacts are built in a scratch
  directory and published by a single directory rename, so readers see either
  nothing or a complete, verified set. Any failure leaves nothing behind.

  Video preview selection, cheapest first:

    1. the original itself, when it already is a faststart MP4 passing the
       compatibility gate (H.264 Baseline/Main/High <= level 4.2, yuv420p, SDR,
       no rotation, square pixels, <= 1920x1080, <= 60 fps, AAC-LC <= 2 ch or no
       audio) within the byte budget
    2. a lossless stream-copy remux to faststart MP4 of such a stream
    3. an x264 encode; single pass CRF 23 capped by VBV when the duration leaves
       ample bitrate, otherwise two-pass ABR at the bitrate the budget allows;
       one tighter two-pass retry if the measured file is still over budget

  The whole duration is always kept. When the budget cannot give the video at
  least 200 kbit/s over the full duration (at the default 19 MiB budget: about
  579 s with audio at 64 kbit/s, 765 s without audio) preparation fails with `:unsupported_media` instead
  of trimming or advertising an unwatchable preview.

  HDR (PQ/HLG) and BT.2020 sources are converted to BT.709 SDR with real tone
  mapping (zscale + tonemap) and rejected as `:unsupported_media` when the
  ffmpeg build lacks those filters; Dolby Vision without a compatible base
  layer is rejected.

  Limits enforced from the probe before anything is decoded: video frames at
  most 8192 px per edge and 8192x4320 px total, images 16384 px per edge and
  64 megapixels, finite positive duration for audio/video.

  Error reasons: `:busy` (admission full), `:timeout` (`:media_timeout_ms`
  wall clock for the whole preparation), `:invalid_media` (not decodable or
  verification of the output failed), `:unsupported_media` (recognized but
  outside the limits above), `:media_tools_unavailable`, `:invalid_name`,
  `:not_found`, `{:io, reason}`.
  """

  require Logger

  alias BjFiles.Media.{Command, Gate, Jobs, Probe}
  alias BjFiles.Store

  @schema "bj_files.media"
  @version 1

  # Same shape BjFiles.Store generates; keeps every derived path inside .previews.
  @name ~r/\A[A-Za-z0-9_-]{8,64}(\.[a-z0-9]{1,10})?\z/

  @preview_edge 1280
  @passthrough_long 1920
  @passthrough_short 1080
  @passthrough_level 42
  @h264_profiles ["Constrained Baseline", "Baseline", "Main", "High"]
  @min_video_kbps 200
  @max_video_kbps 5000
  @crf_min_kbps 1500
  @max_video_edge 8192
  @max_video_pixels 8192 * 4320
  @max_image_edge 16_384
  @max_image_pixels 64_000_000
  @max_meta_bytes 64 * 1024

  @x264_preset "medium"

  # --- paths -----------------------------------------------------------------

  @doc false
  def previews_dir, do: Path.join(Path.expand(Store.dir()), ".previews")

  @doc false
  def jobs_dir, do: Path.join(previews_dir(), ".jobs")

  @doc false
  def valid_name?(name), do: is_binary(name) and Regex.match?(@name, name)

  # --- public API ------------------------------------------------------------

  @doc """
  Synchronously prepares `name` (stored at `path`) under admission control.
  Returns the published metadata, or `{:error, reason}` with nothing published.
  Never touches the original.
  """
  @spec prepare(Path.t(), String.t(), String.t()) :: {:ok, map()} | {:error, term()}
  def prepare(path, name, original_filename) do
    with :ok <- check_name(name),
         :ok <- Gate.acquire() do
      try do
        prepare_admitted(path, name, original_filename)
      after
        Gate.release()
      end
    end
  end

  @doc """
  Admits an asynchronous preparation (see `BjFiles.Media.Jobs`). `:ok` means a
  durable pending marker exists and `status/1` will settle to ready or failed.
  """
  @spec enqueue(Path.t(), String.t(), String.t()) :: :ok | {:error, term()}
  def enqueue(path, name, original_filename) do
    with :ok <- check_name(name), do: Jobs.enqueue(path, name, original_filename)
  end

  @doc """
  `{:ok, metadata}` when ready, `:processing` while an admitted job runs,
  `{:error, :invalid_media | :unsupported_media | :timeout | :processing_failed}`
  after a failed upload preparation, `:error` when unknown.
  """
  @spec status(String.t()) :: {:ok, map()} | :processing | {:error, atom()} | :error
  def status(name) do
    if valid_name?(name) do
      with :error <- load(name), :error <- Jobs.failure(name) do
        if Jobs.pending?(name), do: :processing, else: :error
      end
    else
      :error
    end
  end

  @doc """
  Published metadata for `name`, only when its schema/version is current, it is
  internally consistent and every artifact it references exists (a passthrough
  original must still have the size that was verified). String keys: `schema`,
  `version`, `name`, `title`, `original_filename`, `kind` (video|image|audio),
  `width`, `height` (the advertised asset size: preview size when `preview`,
  otherwise poster size; nil when neither), `duration` (seconds, nil for
  images), `preview`, `poster` (booleans), `preview_bytes`, `preview_source`
  (original|derived|nil), `created_at`.
  """
  @spec load(String.t()) :: {:ok, map()} | :error
  def load(name) do
    with true <- valid_name?(name),
         path = Path.join([previews_dir(), name, "meta.json"]),
         {:ok, %File.Stat{type: :regular, size: size}} when size <= @max_meta_bytes <- File.stat(path),
         {:ok, json} <- File.read(path),
         {:ok, %{} = meta} <- Jason.decode(json),
         true <- valid_meta?(meta, name),
         true <- artifacts_present?(name, meta) do
      {:ok, meta}
    else
      _ -> :error
    end
  end

  @doc "Absolute path of a ready poster (JPEG) or preview (MP4), else `:error`."
  @spec asset(String.t(), :poster | :preview) :: {:ok, Path.t()} | :error
  def asset(name, kind) when kind in [:poster, :preview] do
    case load(name) do
      {:ok, meta} -> asset_path(name, meta, kind)
      :error -> :error
    end
  end

  defp asset_path(name, %{"poster" => true}, :poster), do: {:ok, Path.join([previews_dir(), name, "poster.jpg"])}
  defp asset_path(name, %{"preview" => true, "preview_source" => "derived"}, :preview), do: {:ok, Path.join([previews_dir(), name, "preview.mp4"])}

  defp asset_path(name, %{"preview" => true, "preview_source" => "original"}, :preview) do
    with {:ok, path} <- Store.path(name), do: {:ok, Path.expand(path)}
  end

  defp asset_path(_name, _meta, _kind), do: :error

  @doc """
  Prepares every stored original lacking valid ready metadata (missing,
  corrupt, stale schema or missing artifacts). Already-ready items are skipped,
  so it is safe to rerun. Items of in-flight or failed uploads are left to the
  job system. Failures are reported and never delete an original. Run inside
  the live node so it shares admission with uploads:

      bin/bj_files rpc "BjFiles.Media.backfill() |> IO.inspect()"
  """
  @spec backfill() :: %{ready: non_neg_integer(), skipped: non_neg_integer(), failed: [{String.t(), term()}]}
  def backfill do
    names = Store.dir() |> File.ls!() |> Enum.sort()

    result =
      Enum.reduce(names, %{ready: 0, skipped: 0, failed: []}, fn name, acc ->
        with {:ok, path} <- Store.path(name),
             :error <- load(name),
             false <- Jobs.pending?(name),
             :error <- Jobs.failure(name) do
          case prepare_waiting(path, name, name) do
            {:ok, _meta} ->
              Logger.info("backfill #{name}: ready")
              %{acc | ready: acc.ready + 1}

            {:error, reason} ->
              Logger.warning("backfill #{name}: #{inspect(reason)}")
              %{acc | failed: [{name, reason} | acc.failed]}
          end
        else
          {:ok, _} -> %{acc | skipped: acc.skipped + 1}
          _ -> acc
        end
      end)

    %{result | failed: Enum.reverse(result.failed)}
  end

  # Backfill shares the gate with live uploads; wait for a slot rather than fail.
  defp prepare_waiting(path, name, filename) do
    deadline = now() + timeout_ms() + 60_000
    prepare_waiting(path, name, filename, deadline)
  end

  defp prepare_waiting(path, name, filename, deadline) do
    case prepare(path, name, filename) do
      {:error, :busy} ->
        if now() < deadline do
          Process.sleep(1_000)
          prepare_waiting(path, name, filename, deadline)
        else
          {:error, :busy}
        end

      other ->
        other
    end
  end

  @doc false
  # Removes scratch directories left by a VM that died mid-preparation.
  def cleanup_stale do
    case File.ls(previews_dir()) do
      {:ok, entries} ->
        for entry <- entries, String.starts_with?(entry, ".tmp-"), do: File.rm_rf(Path.join(previews_dir(), entry))
        :ok

      _ ->
        :ok
    end
  end

  @doc false
  # Body of prepare/3 for a process that already holds the gate.
  def prepare_admitted(path, name, original_filename) do
    result =
      with :ok <- check_name(name),
           {:ok, tools} <- tools(),
           {:ok, %File.Stat{type: :regular, size: size}} <- stat(path) do
        work = Path.join(previews_dir(), ".tmp-#{name}-#{random()}")
        Gate.put_work_dir(work)

        try do
          build(work, Path.expand(path), size, name, original_filename, tools)
        after
          File.rm_rf(work)
        end
      end

    case result do
      {:ok, meta} ->
        Logger.info("media #{name}: #{meta["kind"]} ready, preview=#{meta["preview_source"] || "none"} poster=#{meta["poster"]}")

      {:error, reason} ->
        Logger.warning("media #{name}: preparation failed: #{inspect(reason)}")
    end

    result
  end

  defp stat(path) do
    case File.stat(path) do
      {:ok, %File.Stat{type: :regular}} = ok -> ok
      _ -> {:error, :not_found}
    end
  end

  defp build(work, original, size, name, filename, tools) do
    out = Path.join(work, "out")
    src = Path.join(work, "source")

    ctx = %{
      ffmpeg: tools.ffmpeg,
      ffprobe: tools.ffprobe,
      work: work,
      out: out,
      src: src,
      original: original,
      size: size,
      budget: Application.get_env(:bj_files, :media_preview_max_bytes, 19 * 1024 * 1024),
      threads: Integer.to_string(max(Application.get_env(:bj_files, :media_threads, 2), 1)),
      deadline: now() + timeout_ms()
    }

    # The extension-less symlink makes ffmpeg detect the format by content only.
    with :ok <- io(File.mkdir_p(out)),
         :ok <- io(File.ln_s(original, src)),
         {:ok, info} <- Probe.run(ctx.ffprobe, src, ctx.deadline),
         {:ok, media} <- derive(ctx, info),
         meta = metadata(name, filename, media),
         :ok <- publish(ctx, name, meta) do
      {:ok, meta}
    end
  end

  # --- classification ----------------------------------------------------------

  defp derive(ctx, info) do
    cond do
      Probe.image_format?(info) or still_gif?(info) -> image(ctx, info)
      Probe.video_streams(info) != [] -> video(ctx, info)
      Probe.audio_streams(info) != [] -> audio(ctx, info)
      true -> {:error, :invalid_media}
    end
  end

  defp still_gif?(info) do
    with "gif" <- Probe.format_name(info),
         [s | _] <- Probe.video_streams(info) do
      s["nb_frames"] in ["1", nil] and (Probe.duration(info, s) || 0.0) < 0.1
    else
      _ -> false
    end
  end

  defp image(ctx, info) do
    with [stream | _] <- Probe.video_streams(info) ++ Probe.cover_streams(info),
         {w, h} = Probe.display_size(stream),
         :ok <- check_dims(w, h, @max_image_edge, @max_image_pixels),
         {:ok, {pw, ph}} <- poster(ctx, stream["index"], nil, fit_filter(@preview_edge, false)) do
      {:ok, %{kind: "image", width: pw, height: ph, duration: nil, preview: nil, poster: true}}
    else
      [] -> {:error, :invalid_media}
      error -> error
    end
  end

  defp audio(ctx, info) do
    [stream | _] = Probe.audio_streams(info)

    with dur when is_float(dur) <- Probe.duration(info, stream) || {:error, :invalid_media},
         :ok <- decode_check(ctx, stream["index"]),
         {:ok, poster} <- cover(ctx, Probe.cover_streams(info)) do
      {w, h} = poster || {nil, nil}
      {:ok, %{kind: "audio", width: w, height: h, duration: dur, preview: nil, poster: poster != nil}}
    end
  end

  # Cover art is optional for audio: a broken picture just means no poster.
  defp cover(_ctx, []), do: {:ok, nil}

  defp cover(ctx, [stream | _]) do
    {w, h} = Probe.display_size(stream)

    with :ok <- check_dims(w, h, @max_image_edge, @max_image_pixels),
         {:ok, dims} <- poster(ctx, stream["index"], nil, fit_filter(@preview_edge, false)) do
      {:ok, dims}
    else
      {:error, :timeout} -> {:error, :timeout}
      _ -> {:ok, nil}
    end
  end

  # Decodes the first seconds strictly: a file that merely probes is not enough.
  defp decode_check(ctx, index) do
    args = head(ctx) ++ ["-xerror", "-t", "10"] ++ Probe.input_args(ctx.src) ++ ["-map", "0:#{index}", "-f", "null", "-"]
    ffmpeg(ctx, args, :invalid_media)
  end

  defp video(ctx, info) do
    [v | _] = Probe.video_streams(info)
    a = List.first(Probe.audio_streams(info))
    {w, h} = Probe.display_size(v)

    with :ok <- check_dims(w, h, @max_video_edge, @max_video_pixels),
         dur when is_float(dur) <- Probe.duration(info, v) || {:error, :invalid_media},
         :ok <- color_supported(ctx, v),
         {:ok, preview} <- video_preview(ctx, info, v, a, dur),
         vf = color_chain(v) <> "scale=#{preview.width}:#{preview.height},setsar=1",
         {:ok, dims} <- poster(ctx, v["index"], min(1.0, dur / 3), vf),
         true <- dims == {preview.width, preview.height} || {:error, :invalid_media} do
      {:ok,
       %{
         kind: "video",
         width: preview.width,
         height: preview.height,
         duration: preview.duration,
         preview: preview,
         poster: true
       }}
    end
  end

  defp check_dims(w, h, edge, pixels) do
    cond do
      not (is_integer(w) and is_integer(h) and w > 0 and h > 0) -> {:error, :invalid_media}
      w > edge or h > edge or w * h > pixels -> {:error, :unsupported_media}
      true -> :ok
    end
  end

  defp color_supported(ctx, v) do
    cond do
      Probe.dolby_vision_only?(v) -> {:error, :unsupported_media}
      Probe.wide_or_hdr?(v) and not Probe.tone_mapping?(ctx.ffmpeg) -> {:error, :unsupported_media}
      true -> :ok
    end
  end

  # Real conversion to BT.709 SDR in linear light; tone mapping only for PQ/HLG.
  defp color_chain(v) do
    cond do
      Probe.hdr_transfer?(v) ->
        "zscale=t=linear:npl=100,format=gbrpf32le,zscale=p=bt709,tonemap=tonemap=hable:desat=0," <>
          "zscale=t=bt709:m=bt709:r=tv,format=yuv420p,"

      Probe.wide_or_hdr?(v) ->
        "zscale=t=linear,format=gbrpf32le,zscale=p=bt709,zscale=t=bt709:m=bt709:r=tv,format=yuv420p,"

      true ->
        ""
    end
  end

  defp color_tags(v) do
    if Probe.wide_or_hdr?(v),
      do: ["-color_primaries", "bt709", "-color_trc", "bt709", "-colorspace", "bt709", "-color_range", "tv"],
      else: []
  end

  # Fits within edge x edge, keeps aspect ratio, never upscales.
  defp fit_filter(edge, even) do
    base = "scale=w='min(#{edge},iw)':h='min(#{edge},ih)':force_original_aspect_ratio=decrease"
    if even, do: base <> ":force_divisible_by=2,setsar=1", else: base <> ",setsar=1"
  end

  # --- video preview -------------------------------------------------------------

  defp video_preview(ctx, info, v, a, dur) do
    cond do
      direct?(ctx, info, v, a) ->
        {w, h} = Probe.display_size(v)
        {:ok, %{source: "original", width: w, height: h, duration: dur, bytes: ctx.size}}

      compatible?(v, a) and ctx.size <= ctx.budget ->
        case remux(ctx, v, a, dur) do
          {:ok, preview} -> {:ok, preview}
          {:error, :timeout} -> {:error, :timeout}
          {:error, _} -> encode(ctx, v, a, dur)
        end

      true ->
        encode(ctx, v, a, dur)
    end
  end

  # Players that only understand plain progressive MP4 H.264/AAC must be able to play it.
  defp compatible?(v, a) do
    {w, h} = Probe.display_size(v)
    fps = Probe.frame_rate(v)
    level = Probe.int(v["level"])

    v["codec_name"] == "h264" and v["profile"] in @h264_profiles and is_integer(level) and level > 0 and
      level <= @passthrough_level and v["pix_fmt"] == "yuv420p" and not Probe.wide_or_hdr?(v) and
      Probe.rotation(v) == 0 and Probe.square_pixels?(v) and max(w, h) <= @passthrough_long and
      min(w, h) <= @passthrough_short and is_float(fps) and fps > 0 and fps <= 60.5 and
      (a == nil or (a["codec_name"] == "aac" and a["profile"] == "LC" and Probe.int(a["channels"]) in [1, 2]))
  end

  defp direct?(ctx, info, v, a) do
    Probe.format_name(info) == "mov" and get_in(info, [:format, "tags", "major_brand"]) not in [nil, "qt  "] and
      length(Probe.video_streams(info)) == 1 and Probe.cover_streams(info) == [] and
      length(Probe.audio_streams(info)) <= 1 and compatible?(v, a) and ctx.size <= ctx.budget and
      Probe.faststart?(ctx.original)
  end

  defp remux(ctx, v, a, dur) do
    target = Path.join(ctx.out, "preview.mp4")

    args =
      head(ctx) ++
        Probe.input_args(ctx.src) ++
        maps(v, a) ++ ["-c", "copy"] ++ mux_args(target)

    with :ok <- ffmpeg(ctx, args, :invalid_media),
         {:ok, preview} <- verify_preview(ctx, target, a != nil, dur, false),
         :ok <- within_budget(ctx, preview, target) do
      {:ok, preview}
    else
      {:error, :timeout} ->
        {:error, :timeout}

      {:error, reason} ->
        File.rm(target)
        {:error, reason}
    end
  end

  defp encode(ctx, v, a, dur) do
    total_kbps = ctx.budget * 8 * 0.96 / dur / 1000
    audio_kbps = cond do
      a == nil -> 0
      total_kbps >= 1200 -> 128
      true -> 64
    end

    video_kbps = trunc(total_kbps - audio_kbps)

    if video_kbps < @min_video_kbps do
      Logger.warning("media: #{dur}s does not fit #{ctx.budget} bytes at >= #{@min_video_kbps} kbit/s video")
      {:error, :unsupported_media}
    else
      kbps = min(video_kbps, @max_video_kbps)

      edge =
        cond do
          kbps >= 1200 -> @preview_edge
          kbps >= 600 -> 854
          true -> 640
        end

      mode = if kbps >= @crf_min_kbps, do: :crf, else: :two_pass
      p = %{v: v, a: a, dur: dur, edge: edge, audio_kbps: audio_kbps}

      case encode_pass(ctx, p, mode, kbps) do
        {:over, bytes} ->
          retry = trunc(kbps * ctx.budget / bytes * 0.9)

          if retry >= @min_video_kbps do
            case encode_pass(ctx, p, :two_pass, retry) do
              {:over, _} -> {:error, :unsupported_media}
              other -> other
            end
          else
            {:error, :unsupported_media}
          end

        other ->
          other
      end
    end
  end

  defp encode_pass(ctx, p, mode, kbps) do
    target = Path.join(ctx.out, "preview.mp4")
    File.rm(target)
    vf = color_chain(p.v) <> fit_filter(p.edge, true) <> ",format=yuv420p"

    video =
      ["-map", "0:#{p.v["index"]}", "-vf", vf, "-c:v", "libx264", "-preset", @x264_preset, "-profile:v", "high"] ++
        ["-pix_fmt", "yuv420p", "-fpsmax", "60", "-threads", ctx.threads] ++ color_tags(p.v)

    audio =
      case p.a do
        nil -> ["-an"]
        a -> ["-map", "0:#{a["index"]}", "-c:a", "aac", "-b:a", "#{p.audio_kbps}k", "-ac", "2", "-ar", "48000"]
      end

    input = head(ctx) ++ Probe.input_args(ctx.src)
    rate = ["-maxrate", "#{kbps}k", "-bufsize", "#{kbps * 2}k"]
    log = ["-passlogfile", Path.join(ctx.work, "x264")]

    steps =
      case mode do
        :crf ->
          [input ++ video ++ ["-crf", "23"] ++ rate ++ audio ++ mux_args(target)]

        :two_pass ->
          two = ["-b:v", "#{kbps}k", "-maxrate", "#{trunc(kbps * 1.5)}k", "-bufsize", "#{kbps * 2}k"]

          [
            input ++ video ++ two ++ ["-pass", "1"] ++ log ++ ["-an", "-f", "null", "-"],
            input ++ video ++ two ++ ["-pass", "2"] ++ log ++ audio ++ mux_args(target)
          ]
      end

    with :ok <- run_steps(ctx, steps),
         {:ok, preview} <- verify_preview(ctx, target, p.a != nil, p.dur, true) do
      case within_budget(ctx, preview, target) do
        :ok -> {:ok, preview}
        {:error, :over_budget} -> {:over, preview.bytes}
      end
    end
  end

  defp run_steps(_ctx, []), do: :ok

  defp run_steps(ctx, [args | rest]) do
    with :ok <- ffmpeg(ctx, args, :invalid_media), do: run_steps(ctx, rest)
  end

  defp within_budget(ctx, preview, target) do
    if preview.bytes <= ctx.budget do
      :ok
    else
      File.rm(target)
      {:error, :over_budget}
    end
  end

  defp maps(v, nil), do: ["-map", "0:#{v["index"]}", "-an"]
  defp maps(v, a), do: ["-map", "0:#{v["index"]}", "-map", "0:#{a["index"]}"]

  defp mux_args(target) do
    ["-sn", "-dn", "-map_metadata", "-1", "-map_chapters", "-1", "-movflags", "+faststart", "-f", "mp4", "file:" <> target]
  end

  # Re-probes the produced file: what is advertised is what was measured.
  defp verify_preview(ctx, path, audio?, source_duration, derived?) do
    with {:ok, %File.Stat{size: bytes}} when bytes > 0 <- File.stat(path),
         {:ok, info} <- Probe.run(ctx.ffprobe, path, ctx.deadline),
         "mov" <- Probe.format_name(info),
         [v] <- Probe.video_streams(info),
         true <- v["codec_name"] == "h264" and v["pix_fmt"] == "yuv420p" and v["profile"] in @h264_profiles,
         true <- not Probe.wide_or_hdr?(v) and Probe.rotation(v) == 0,
         {w, h} when is_integer(w) and is_integer(h) and w > 0 and h > 0 <- Probe.display_size(v),
         true <- not derived? or (rem(w, 2) == 0 and rem(h, 2) == 0 and max(w, h) <= @preview_edge),
         true <- audio_ok?(Probe.audio_streams(info), audio?),
         dur when is_float(dur) <- Probe.duration(info, v),
         true <- dur >= source_duration - max(1.0, source_duration * 0.05),
         true <- Probe.faststart?(path) do
      {:ok, %{source: "derived", width: w, height: h, duration: dur, bytes: bytes}}
    else
      {:error, :timeout} ->
        {:error, :timeout}

      other ->
        Logger.warning("media: preview verification failed: #{inspect(other, limit: 5)}")
        {:error, :invalid_media}
    end
  end

  defp audio_ok?([a], true), do: a["codec_name"] == "aac"
  defp audio_ok?([], false), do: true
  defp audio_ok?(_, _), do: false

  # --- poster --------------------------------------------------------------------

  defp poster(ctx, index, seek, vf) do
    target = Path.join(ctx.out, "poster.jpg")

    case poster_at(ctx, index, seek, vf, target) do
      {:error, :timeout} -> {:error, :timeout}
      {:error, _} when seek != nil -> poster_at(ctx, index, nil, vf, target)
      other -> other
    end
  end

  defp poster_at(ctx, index, seek, vf, target) do
    File.rm(target)
    ss = if seek, do: ["-ss", :erlang.float_to_binary(seek / 1, decimals: 3)], else: []

    args =
      head(ctx) ++
        ss ++
        Probe.input_args(ctx.src) ++
        ["-map", "0:#{index}", "-frames:v", "1", "-vf", vf, "-c:v", "mjpeg", "-q:v", "3"] ++
        ["-threads", ctx.threads, "-map_metadata", "-1", "-f", "image2", "-update", "1", "file:" <> target]

    with :ok <- ffmpeg(ctx, args, :invalid_media),
         {:ok, %File.Stat{size: bytes}} when bytes > 0 <- File.stat(target),
         {:ok, info} <- Probe.run(ctx.ffprobe, target, ctx.deadline, :jpeg),
         [%{"codec_name" => "mjpeg"} = s] <- Probe.video_streams(info),
         {w, h} when is_integer(w) and is_integer(h) and w > 0 and h > 0 <- {Probe.int(s["width"]), Probe.int(s["height"])} do
      {:ok, {w, h}}
    else
      {:error, :timeout} -> {:error, :timeout}
      _ -> {:error, :invalid_media}
    end
  end

  # --- ffmpeg ----------------------------------------------------------------------

  defp head(ctx) do
    ["-nostdin", "-hide_banner", "-v", "error", "-y", "-filter_threads", "1", "-threads", ctx.threads]
  end

  defp ffmpeg(ctx, args, failure) do
    case Command.run(ctx.ffmpeg, args, deadline: ctx.deadline, cd: ctx.work, output: :tail, max_output: 4096) do
      {:ok, _} ->
        :ok

      {:error, :timeout} ->
        {:error, :timeout}

      {:error, {:exit, status, tail}} ->
        Logger.warning("media: ffmpeg exited #{status}: #{String.slice(tail, -1000, 1000)}")
        {:error, failure}

      {:error, other} ->
        Logger.warning("media: ffmpeg failed: #{inspect(other)}")
        {:error, failure}
    end
  end

  defp tools do
    ffmpeg = Application.get_env(:bj_files, :ffmpeg_path) || System.find_executable("ffmpeg")
    ffprobe = Application.get_env(:bj_files, :ffprobe_path) || System.find_executable("ffprobe")

    if is_binary(ffmpeg) and is_binary(ffprobe) and File.regular?(ffmpeg) and File.regular?(ffprobe),
      do: {:ok, %{ffmpeg: ffmpeg, ffprobe: ffprobe}},
      else: {:error, :media_tools_unavailable}
  end

  # --- metadata ----------------------------------------------------------------------

  defp metadata(name, filename, media) do
    preview = media.preview

    %{
      "schema" => @schema,
      "version" => @version,
      "name" => name,
      "title" => title(filename, name),
      "original_filename" => clean(basename(filename), 255),
      "kind" => media.kind,
      "width" => media.width,
      "height" => media.height,
      "duration" => media.duration && Float.round(media.duration / 1, 3),
      "preview" => preview != nil,
      "poster" => media.poster,
      "preview_bytes" => preview && preview.bytes,
      "preview_source" => preview && preview.source,
      "created_at" => DateTime.utc_now() |> DateTime.truncate(:second) |> DateTime.to_iso8601()
    }
  end

  defp title(filename, name) do
    case filename |> basename() |> Path.rootname() |> clean(120) do
      "" -> Path.rootname(name)
      title -> title
    end
  end

  defp basename(filename), do: filename |> to_string() |> String.split(["/", "\\"]) |> List.last()

  # Valid UTF-8, no control/format characters (bidi overrides, zero-width), single spaces.
  defp clean(text, max) do
    text
    |> String.replace_invalid()
    |> String.replace(~r/\p{C}/u, "")
    |> String.replace(~r/\s+/u, " ")
    |> String.trim()
    |> String.slice(0, max)
  end

  defp publish(ctx, name, meta) do
    final = Path.join(previews_dir(), name)

    with :ok <- io(File.write(Path.join(ctx.out, "meta.json"), Jason.encode!(meta), [:sync])),
         :ok <- io(if(File.exists?(final), do: File.rename(final, Path.join(ctx.work, "old")), else: :ok)) do
      io(File.rename(ctx.out, final))
    end
  end

  defp valid_meta?(meta, name) do
    preview = meta["preview"]
    poster = meta["poster"]
    {w, h} = {meta["width"], meta["height"]}

    meta["schema"] == @schema and meta["version"] == @version and meta["name"] == name and
      is_binary(meta["title"]) and meta["kind"] in ["video", "image", "audio"] and is_boolean(preview) and
      is_boolean(poster) and (is_nil(meta["duration"]) or is_number(meta["duration"])) and
      if(preview or poster, do: is_integer(w) and w > 0 and is_integer(h) and h > 0, else: is_nil(w) and is_nil(h)) and
      if(preview,
        do: is_integer(meta["preview_bytes"]) and meta["preview_source"] in ["original", "derived"],
        else: is_nil(meta["preview_bytes"]) and is_nil(meta["preview_source"])
      ) and (meta["kind"] != "video" or preview)
  end

  defp artifacts_present?(name, meta) do
    dir = Path.join(previews_dir(), name)

    poster_ok = not meta["poster"] or File.regular?(Path.join(dir, "poster.jpg"))

    preview_ok =
      case meta["preview_source"] do
        nil -> true
        "derived" -> file_size(Path.join(dir, "preview.mp4")) == meta["preview_bytes"]
        "original" -> match?({:ok, _}, Store.path(name)) and file_size(Path.join(Store.dir(), name)) == meta["preview_bytes"]
      end

    poster_ok and preview_ok
  end

  defp file_size(path) do
    case File.stat(path) do
      {:ok, %File.Stat{type: :regular, size: size}} -> size
      _ -> nil
    end
  end

  # --- helpers -------------------------------------------------------------------------

  defp check_name(name), do: if(valid_name?(name), do: :ok, else: {:error, :invalid_name})

  defp io(:ok), do: :ok
  defp io({:error, reason}), do: {:error, {:io, reason}}

  defp random, do: :crypto.strong_rand_bytes(6) |> Base.url_encode64(padding: false)

  @doc false
  def timeout_ms, do: Application.get_env(:bj_files, :media_timeout_ms, 600_000)

  defp now, do: System.monotonic_time(:millisecond)
end
