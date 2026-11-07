defmodule BjFiles.MediaTest do
  # Real ffmpeg/ffprobe runs against generated media; nothing is mocked.
  use ExUnit.Case, async: false

  alias BjFiles.Media
  alias BjFiles.Media.{Command, Gate, Probe}
  alias BjFiles.Store

  @moduletag :capture_log
  @moduletag timeout: 300_000

  @fixtures Path.join(System.tmp_dir!(), "bj_files_media_fixtures")

  setup_all do
    File.rm_rf!(@fixtures)
    File.mkdir_p!(@fixtures)

    av = ["-f", "lavfi", "-i", "sine=d=2"]

    ffmpeg!(["-f", "lavfi", "-i", "testsrc2=s=640x360:r=25:d=2"] ++ av ++ ~w(-c:v libx264 -profile:v high -pix_fmt yuv420p -c:a aac -shortest -movflags +faststart) ++ [fx("compat.mp4")])
    # Same streams, moov at the end (ffmpeg's default mp4 layout).
    ffmpeg!(["-i", fx("compat.mp4"), "-c", "copy", fx("late_moov.mp4")])
    ffmpeg!(["-display_rotation", "90", "-i", fx("compat.mp4"), "-c", "copy", "-movflags", "+faststart", fx("rotated.mp4")])
    # The smoke case: lossless High 4:4:4 Predictive is yuv420p yet not widely playable.
    ffmpeg!(["-f", "lavfi", "-i", "testsrc2=s=1280x720:r=30:d=2"] ++ av ++ ~w(-c:v libx264 -preset ultrafast -qp 0 -pix_fmt yuv420p -c:a aac -shortest -movflags +faststart) ++ [fx("lossless.mp4")])
    # MPEG-4 Part 2 is never passed through, so this exercises the scaler.
    ffmpeg!(["-f", "lavfi", "-i", "testsrc2=s=641x361:r=25:d=1"] ++ ~w(-c:v mpeg4 -q:v 5) ++ [fx("odd.mkv")])
    ffmpeg!(["-f", "lavfi", "-i", "testsrc2=s=320x240:r=25:d=1"] ++ ~w(-vf setparams=color_primaries=bt2020:color_trc=smpte2084:colorspace=bt2020nc -c:v libx264 -pix_fmt yuv420p10le) ++ [fx("hdr.mp4")])
    ffmpeg!(["-f", "lavfi", "-i", "testsrc2=s=300x200", "-frames:v", "1", fx("image.png")])
    ffmpeg!(av ++ ~w(-c:a aac) ++ [fx("audio.m4a")])

    late = File.read!(fx("late_moov.mp4"))
    File.write!(fx("truncated.mp4"), binary_part(late, 0, div(byte_size(late), 2)))
    File.write!(fx("text.mp4"), "this is not a video\n")
    File.write!(fx("playlist.mp4"), "#EXTM3U\n#EXT-X-TARGETDURATION:1\n#EXTINF:1,\nfile://#{fx("compat.mp4")}\n#EXT-X-ENDLIST\n")
    File.write!(fx("concat.mp4"), "ffconcat version 1.0\nfile '#{fx("compat.mp4")}'\n")
    File.write!(fx("bomb.png"), png_header(20_000, 20_000))
    :ok
  end

  setup do
    File.rm_rf!(Store.dir())
    File.mkdir_p!(Store.dir())
    env = Application.get_all_env(:bj_files)

    on_exit(fn ->
      for {k, v} <- env, do: Application.put_env(:bj_files, k, v)
    end)

    :ok
  end

  # --- video ---------------------------------------------------------------------

  test "a compatible faststart MP4 within budget is its own preview, untouched" do
    {name, path} = store("compat.mp4", ".mp4")
    before = sha(path)

    assert {:ok, meta} = Media.prepare(path, name, "Holiday Clip.mp4")
    assert %{"kind" => "video", "preview" => true, "poster" => true, "preview_source" => "original"} = meta
    assert {meta["width"], meta["height"]} == {640, 360}
    assert meta["preview_bytes"] == File.stat!(path).size
    assert_in_delta meta["duration"], 2.0, 0.1
    assert meta["title"] == "Holiday Clip"

    assert Media.asset(name, :preview) == {:ok, Path.expand(path)}
    {:ok, poster} = Media.asset(name, :poster)
    assert %{"codec_name" => "mjpeg", "width" => 640, "height" => 360} = video_stream(poster)
    assert sha(path) == before
  end

  test "compatible streams with moov at the end are remuxed losslessly to faststart" do
    {name, path} = store("late_moov.mp4", ".mp4")
    before = sha(path)
    refute Probe.faststart?(path)

    assert {:ok, %{"preview_source" => "derived"} = meta} = Media.prepare(path, name, "late.mp4")
    {:ok, preview} = Media.asset(name, :preview)
    assert Probe.faststart?(preview)
    assert File.stat!(preview).size == meta["preview_bytes"]
    # Stream copy: same coded picture size and profile as the source.
    assert %{"profile" => "High", "width" => 640, "height" => 360} = video_stream(preview)
    assert sha(path) == before
  end

  test "an incompatible profile is re-encoded to a playable H.264/AAC faststart MP4" do
    {name, path} = store("lossless.mp4", ".mp4")
    before = sha(path)
    assert %{"profile" => "High 4:4:4 Predictive"} = video_stream(path)

    assert {:ok, meta} = Media.prepare(path, name, "big.mp4")
    assert meta["preview_source"] == "derived"
    {:ok, preview} = Media.asset(name, :preview)
    v = video_stream(preview)
    assert v["codec_name"] == "h264" and v["pix_fmt"] == "yuv420p"
    assert v["profile"] in ["Main", "High", "Constrained Baseline"]
    assert {v["width"], v["height"]} == {meta["width"], meta["height"]}
    assert [%{"codec_name" => "aac"}] = streams(preview, "audio")
    assert Probe.faststart?(preview)
    assert File.stat!(preview).size == meta["preview_bytes"]
    assert meta["preview_bytes"] <= 19 * 1024 * 1024
    assert sha(path) == before
  end

  test "the measured preview never exceeds a tight byte budget and keeps the full duration" do
    Application.put_env(:bj_files, :media_preview_max_bytes, 200_000)
    {name, path} = store("lossless.mp4", ".mp4")
    assert File.stat!(path).size > 200_000

    assert {:ok, meta} = Media.prepare(path, name, "big.mp4")
    {:ok, preview} = Media.asset(name, :preview)
    assert File.stat!(preview).size == meta["preview_bytes"]
    assert meta["preview_bytes"] <= 200_000
    assert_in_delta meta["duration"], 2.0, 0.15
    # 2 s at ~700 kbit/s is downscaled from 1280x720.
    assert max(meta["width"], meta["height"]) < 1280
    assert rem(meta["width"], 2) == 0 and rem(meta["height"], 2) == 0
    {:ok, poster} = Media.asset(name, :poster)
    assert {video_stream(poster)["width"], video_stream(poster)["height"]} == {meta["width"], meta["height"]}
  end

  test "a source whose full duration cannot fit the budget is rejected, not trimmed" do
    Application.put_env(:bj_files, :media_preview_max_bytes, 20_000)
    {name, path} = store("lossless.mp4", ".mp4")

    assert Media.prepare(path, name, "long.mp4") == {:error, :unsupported_media}
    assert_nothing_published(name)
    assert File.regular?(path)
  end

  test "odd dimensions become even without upscaling" do
    {name, path} = store("odd.mkv", ".mkv")

    assert {:ok, meta} = Media.prepare(path, name, "odd.mkv")
    assert {meta["width"], meta["height"]} == {640, 360}
  end

  test "rotated video is advertised with display dimensions" do
    {name, path} = store("rotated.mp4", ".mp4")

    assert {:ok, %{"preview_source" => "derived"} = meta} = Media.prepare(path, name, "phone.mp4")
    assert {meta["width"], meta["height"]} == {360, 640}
    {:ok, preview} = Media.asset(name, :preview)
    v = video_stream(preview)
    assert {v["width"], v["height"]} == {360, 640}
    assert Probe.rotation(v) == 0
  end

  test "HDR is tone mapped to BT.709 SDR, or refused when ffmpeg cannot" do
    {name, path} = store("hdr.mp4", ".mp4")
    ffmpeg = System.find_executable("ffmpeg")

    if Probe.tone_mapping?(ffmpeg) do
      assert {:ok, %{"preview_source" => "derived"}} = Media.prepare(path, name, "hdr.mp4")
      {:ok, preview} = Media.asset(name, :preview)
      v = video_stream(preview)
      assert v["pix_fmt"] == "yuv420p"
      assert v["color_transfer"] == "bt709" and v["color_primaries"] == "bt709"
    else
      assert Media.prepare(path, name, "hdr.mp4") == {:error, :unsupported_media}
      assert_nothing_published(name)
    end
  end

  # --- image / audio -----------------------------------------------------------------

  test "images get a JPEG poster of their real size and no video preview" do
    {name, path} = store("image.png", ".png")

    assert {:ok, meta} = Media.prepare(path, name, "pic.png")
    assert %{"kind" => "image", "preview" => false, "poster" => true, "width" => 300, "height" => 200, "duration" => nil} = meta
    assert Media.asset(name, :preview) == :error
    {:ok, poster} = Media.asset(name, :poster)
    assert %{"codec_name" => "mjpeg", "width" => 300, "height" => 200} = video_stream(poster)
  end

  test "images declaring huge dimensions are refused without allocating the frame" do
    {name, path} = store("bomb.png", ".png")
    assert {:error, reason} = Media.prepare(path, name, "bomb.png")
    assert reason in [:invalid_media, :unsupported_media]
    assert_nothing_published(name)
  end

  test "audio is decoded and described without inventing a preview or poster" do
    {name, path} = store("audio.m4a", ".m4a")

    assert {:ok, meta} = Media.prepare(path, name, "song.m4a")
    assert %{"kind" => "audio", "preview" => false, "poster" => false, "width" => nil, "height" => nil} = meta
    assert_in_delta meta["duration"], 2.0, 0.1
    assert Media.asset(name, :poster) == :error
  end

  # --- rejection ---------------------------------------------------------------------

  test "non-media, truncated and reference formats are invalid regardless of extension" do
    for fixture <- ~w(text.mp4 truncated.mp4 playlist.mp4 concat.mp4) do
      {name, path} = store(fixture, ".mp4")
      before = sha(path)
      assert Media.prepare(path, name, fixture) == {:error, :invalid_media}, fixture
      assert_nothing_published(name)
      assert sha(path) == before
    end
  end

  test "names that could escape the data directory are refused everywhere" do
    {_name, path} = store("compat.mp4", ".mp4")

    for bad <- ["../etc", ".previews", "a/../../etc/passwd", "short", ".jobs", "abcdefgh/..", "abcdefgh.MP4"] do
      assert Media.prepare(path, bad, "x.mp4") == {:error, :invalid_name}
      assert Media.load(bad) == :error
      assert Media.asset(bad, :poster) == :error
      assert Media.status(bad) == :error
    end
  end

  # --- persistence ---------------------------------------------------------------------

  test "ready metadata survives an application restart" do
    {name, path} = store("late_moov.mp4", ".mp4")
    {:ok, meta} = Media.prepare(path, name, "keep.mp4")

    :ok = Application.stop(:bj_files)
    {:ok, _} = Application.ensure_all_started(:bj_files)

    assert Media.load(name) == {:ok, meta}
    assert Media.status(name) == {:ok, meta}
    assert {:ok, _} = Media.asset(name, :preview)
  end

  test "stale or incomplete metadata is not ready and backfill repairs it" do
    {name, path} = store("compat.mp4", ".mp4")
    {:ok, _} = Media.prepare(path, name, "x.mp4")
    meta_path = Path.join([Media.previews_dir(), name, "meta.json"])

    File.write!(meta_path, File.read!(meta_path) |> Jason.decode!() |> Map.put("version", 0) |> Jason.encode!())
    assert Media.load(name) == :error

    assert %{ready: 1} = Media.backfill()
    assert {:ok, _} = Media.load(name)

    File.rm!(Path.join([Media.previews_dir(), name, "poster.jpg"]))
    assert Media.load(name) == :error
    assert Media.asset(name, :preview) == :error
    assert %{ready: 1} = Media.backfill()
    assert {:ok, _} = Media.asset(name, :poster)
  end

  test "backfill is idempotent and never deletes legacy originals" do
    {good, good_path} = store("compat.mp4", ".mp4")
    {bad, bad_path} = store("text.mp4", ".mp4")
    bad_sha = sha(bad_path)

    assert %{ready: 1, skipped: 0, failed: [{^bad, :invalid_media}]} = Media.backfill()
    assert {:ok, %{"title" => title}} = Media.load(good)
    assert title == Path.rootname(good)
    assert sha(bad_path) == bad_sha
    assert File.regular?(good_path)

    assert %{ready: 0, skipped: 1, failed: [{^bad, :invalid_media}]} = Media.backfill()
  end

  # --- admission, timeouts, cleanup -------------------------------------------------------

  test "a full gate refuses with :busy instead of queueing" do
    {name, path} = store("compat.mp4", ".mp4")
    holder = hold_gate()

    assert Media.prepare(path, name, "x.mp4") == {:error, :busy}
    assert Media.enqueue(path, name, "x.mp4") == {:error, :busy}
    refute File.exists?(Path.join(Media.jobs_dir(), name <> ".pending"))

    send(holder, :release)
    eventually(fn -> Gate.busy() == 0 end)
    assert {:ok, _} = Media.prepare(path, name, "x.mp4")
  end

  test "the wall-clock limit kills ffmpeg and leaves nothing behind" do
    Application.put_env(:bj_files, :media_timeout_ms, 150)
    {name, path} = store("lossless.mp4", ".mp4")

    assert Media.prepare(path, name, "slow.mp4") == {:error, :timeout}
    assert_nothing_published(name)
    assert Gate.busy() == 0
    refute ffmpeg_running?(name)
    assert File.regular?(path)
  end

  test "a preparation whose caller dies releases capacity, kills ffmpeg and removes scratch files" do
    {name, path} = store("lossless.mp4", ".mp4")
    caller = spawn(fn -> Media.prepare(path, name, "x.mp4") end)

    eventually(fn -> ffmpeg_running?(name) end)
    Process.exit(caller, :kill)

    eventually(fn -> Gate.busy() == 0 end)
    eventually(fn -> not ffmpeg_running?(name) end)
    assert_nothing_published(name)
    assert File.regular?(path)
  end

  # --- async jobs -------------------------------------------------------------------------

  test "an enqueued upload is durably pending, then ready" do
    {name, path} = store("lossless.mp4", ".mp4")

    assert Media.enqueue(path, name, "clip.mp4") == :ok
    # The marker exists before enqueue returns; the transcode takes seconds.
    assert File.regular?(Path.join(Media.jobs_dir(), name <> ".pending"))
    assert Media.status(name) == :processing
    assert Media.enqueue(path, name, "clip.mp4") == {:error, :already_pending}

    eventually(fn -> match?({:ok, _}, Media.status(name)) end)
    assert {:ok, %{"title" => "clip"}} = Media.status(name)
    refute File.exists?(Path.join(Media.jobs_dir(), name <> ".pending"))
    assert File.regular?(path)
  end

  test "a failed upload settles with a public reason and removes the original" do
    {name, path} = store("text.mp4", ".mp4")

    assert Media.enqueue(path, name, "evil.mp4") == :ok
    eventually(fn -> Media.status(name) == {:error, :invalid_media} end)
    refute File.exists?(path)
    assert_nothing_published(name)
    assert Gate.busy() == 0
  end

  test "pending uploads are resumed or explicitly failed after a restart" do
    {resumable, path} = store("compat.mp4", ".mp4")
    gone = "missingorig1.mp4"
    File.mkdir_p!(Media.jobs_dir())

    :ok = Application.stop(:bj_files)
    for n <- [resumable, gone], do: File.write!(Path.join(Media.jobs_dir(), n <> ".pending"), ~s({"version":1,"original_filename":"r.mp4"}))
    {:ok, _} = Application.ensure_all_started(:bj_files)

    eventually(fn -> Media.status(gone) == {:error, :processing_failed} end)
    eventually(fn -> match?({:ok, _}, Media.status(resumable)) end)
    assert {:ok, %{"title" => "r"}} = Media.status(resumable)
    assert File.regular?(path)
  end

  # --- command runner -----------------------------------------------------------------------

  test "commands are killed at the deadline" do
    started = System.monotonic_time(:millisecond)
    deadline = started + 200

    assert Command.run(System.find_executable("sleep"), ["30"], deadline: deadline) == {:error, :timeout}
    assert System.monotonic_time(:millisecond) - started < 5_000
  end

  test "continuous subprocess output cannot postpone the wall-clock deadline" do
    started = System.monotonic_time(:millisecond)

    assert Command.run(System.find_executable("yes"), [],
             deadline: started + 200, output: :tail, max_output: 64
           ) == {:error, :timeout}
    assert System.monotonic_time(:millisecond) - started < 5_000
  end

  test "captured output is capped" do
    deadline = System.monotonic_time(:millisecond) + 10_000

    assert Command.run(System.find_executable("yes"), [], deadline: deadline, output: :all, max_output: 4096) ==
             {:error, :output_too_large}

    assert {:ok, out} =
             Command.run(System.find_executable("seq"), ["1", "100000"], deadline: deadline, output: :tail, max_output: 64)

    assert byte_size(out) == 64
    assert String.ends_with?(out, "100000\n")
  end

  # --- helpers ------------------------------------------------------------------------------

  defp fx(file), do: Path.join(@fixtures, file)

  defp ffmpeg!(args) do
    {out, status} = System.cmd("ffmpeg", ["-nostdin", "-v", "error", "-y" | args], stderr_to_stdout: true)
    if status != 0, do: raise("fixture ffmpeg failed: #{out}")
  end

  defp store(fixture, ext) do
    name = "t" <> Base.encode16(:crypto.strong_rand_bytes(6), case: :lower) <> ext
    path = Path.join(Store.dir(), name)
    File.cp!(fx(fixture), path)
    {name, path}
  end

  defp sha(path), do: :crypto.hash(:sha256, File.read!(path))

  defp streams(path, type) do
    {json, 0} = System.cmd("ffprobe", ["-v", "quiet", "-show_streams", "-of", "json", path])
    json |> Jason.decode!() |> Map.fetch!("streams") |> Enum.filter(&(&1["codec_type"] == type))
  end

  defp video_stream(path), do: path |> streams("video") |> hd()

  defp assert_nothing_published(name) do
    assert Media.load(name) == :error
    refute File.exists?(Path.join(Media.previews_dir(), name))
    leftovers =
      case File.ls(Media.previews_dir()) do
        {:ok, entries} -> Enum.filter(entries, &String.starts_with?(&1, ".tmp-"))
        {:error, _} -> []
      end

    assert leftovers == []
  end

  defp ffmpeg_running?(name) do
    {out, _} = System.cmd("pgrep", ["-f", "ffmpeg.*\\.tmp-" <> Regex.escape(name)])
    out != ""
  end

  defp hold_gate do
    test = self()

    pid =
      spawn(fn ->
        :ok = Gate.acquire()
        send(test, :held)

        receive do
          :release -> Gate.release()
        end
      end)

    assert_receive :held
    pid
  end

  defp eventually(fun, tries \\ 600) do
    cond do
      fun.() -> :ok
      tries == 0 -> flunk("condition not reached")
      true -> Process.sleep(100) && eventually(fun, tries - 1)
    end
  end

  # A PNG whose header claims width x height; the pixel data is irrelevant.
  defp png_header(width, height) do
    ihdr = <<width::32, height::32, 8, 2, 0, 0, 0>>
    idat = :zlib.compress(<<0, 0, 0, 0>>)
    <<137, 80, 78, 71, 13, 10, 26, 10>> <> chunk("IHDR", ihdr) <> chunk("IDAT", idat) <> chunk("IEND", "")
  end

  defp chunk(type, data), do: <<byte_size(data)::32>> <> type <> data <> <<:erlang.crc32(type <> data)::32>>
end
