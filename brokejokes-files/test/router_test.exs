defmodule BjFiles.RouterTest do
  use ExUnit.Case, async: false
  import Plug.Test
  import Plug.Conn

  @opts BjFiles.Router.init([])
  @auth "Bearer test-token"
  @base "https://files.example.com"

  # A real, tiny H264/AAC MP4 made by ffmpeg so preparation exercises the
  # actual media pipeline instead of trusting an extension.
  setup_all do
    dir = Path.join(System.tmp_dir!(), "bj_router_fixtures_#{System.unique_integer([:positive])}")
    File.mkdir_p!(dir)
    video = Path.join(dir, "clip.mp4")

    args =
      ~w(-nostdin -v error -y -f lavfi -i testsrc=size=320x240:rate=15 -f lavfi -i sine=frequency=440:sample_rate=44100
         -t 1 -c:v libx264 -pix_fmt yuv420p -c:a aac -movflags +faststart -shortest) ++ [video]

    {out, status} = System.cmd("ffmpeg", args, stderr_to_stdout: true)
    assert status == 0, "ffmpeg fixture generation failed: #{out}"

    on_exit(fn -> File.rm_rf!(dir) end)
    %{video: File.read!(video)}
  end

  setup do
    File.rm_rf!(BjFiles.Store.dir())
    File.mkdir_p!(BjFiles.Store.dir())

    previous = Application.fetch_env!(:bj_files, :max_upload_bytes)
    Application.put_env(:bj_files, :max_upload_bytes, 20 * 1024 * 1024)
    on_exit(fn -> Application.put_env(:bj_files, :max_upload_bytes, previous) end)
    :ok
  end

  defp call(conn), do: BjFiles.Router.call(conn, @opts)

  defp upload(body, filename, auth \\ @auth, field \\ "file") do
    boundary = "bjboundary"

    payload =
      "--#{boundary}\r\n" <>
        ~s(Content-Disposition: form-data; name="#{field}"; filename="#{filename}"\r\n) <>
        "Content-Type: application/octet-stream\r\n\r\n" <> body <> "\r\n--#{boundary}--\r\n"

    conn(:post, "/upload", payload)
    |> put_req_header("content-type", "multipart/form-data; boundary=#{boundary}")
    |> put_req_header("authorization", auth)
    |> call()
  end

  defp request(method, url, headers \\ []) do
    path = URI.parse(url).path

    Enum.reduce(headers, conn(method, path), fn
      {"host", host}, c -> %{c | host: host}
      {k, v}, c -> put_req_header(c, k, v)
    end)
    |> call()
  end

  defp get(url, headers \\ []), do: request(:get, url, headers)

  defp status(status_url, auth \\ @auth), do: get(status_url, [{"authorization", auth}])

  # Polls the authenticated status URL the way the uploader does.
  defp await_final(status_url, attempts \\ 600) do
    conn = status(status_url)

    cond do
      conn.status == 202 and attempts > 0 ->
        Process.sleep(100)
        await_final(status_url, attempts - 1)

      true ->
        conn
    end
  end

  # Uploads and waits for the final outcome, whether admission answered 201
  # directly or 202 with a status URL.
  defp upload_final(body, filename) do
    conn = upload(body, filename)

    case conn.status do
      202 ->
        %{"status_url" => status_url, "name" => name} = Jason.decode!(conn.resp_body)
        assert status_url == "#{@base}/status/#{name}"
        {await_final(status_url), name}

      _ ->
        {conn, conn.resp_body |> Jason.decode!() |> Map.get("name")}
    end
  end

  defp ready!(video, filename \\ "My Clip.MP4") do
    {conn, name} = upload_final(video, filename)
    assert conn.status in [200, 201], "expected ready payload, got #{conn.status}: #{conn.resp_body}"
    payload = Jason.decode!(conn.resp_body)
    assert payload["name"] == name
    payload
  end

  defp stored_originals do
    BjFiles.Store.dir()
    |> File.ls!()
    |> Enum.filter(&File.regular?(Path.join(BjFiles.Store.dir(), &1)))
  end

  defp header(conn, key), do: conn |> get_resp_header(key) |> List.first()

  defp meta_content(html, attr, key) do
    pattern = ~r/<meta #{attr}="#{Regex.escape(key)}" content="([^"]*)">/

    case Regex.run(pattern, html) do
      [_, value] -> value
      nil -> nil
    end
  end

  describe "upload API" do
    test "requires the bearer token" do
      conn = upload("x", "a.mp4", "Bearer nope")
      assert conn.status == 401
      assert stored_originals() == []
    end

    test "non-media uploads are refused and never stored" do
      for name <- ["evil.html", "evil.svg", "noext"] do
        assert upload("<script>alert(1)</script>", name).status == 415
      end

      assert stored_originals() == []
    end

    test "oversized uploads are rejected" do
      Application.put_env(:bj_files, :max_upload_bytes, 1024)
      assert upload(String.duplicate("x", 2048), "big.mp4").status == 413
      assert stored_originals() == []
    end

    test "missing file field is a 400" do
      assert upload("x", "a.mp4", @auth, "other").status == 400
    end

    test "corrupt media fails without advertising URLs or leaving the original" do
      {conn, _name} = upload_final("definitely not a video stream", "broken.mp4")

      assert conn.status in [415, 422]
      body = Jason.decode!(conn.resp_body)
      assert is_binary(body["error"])
      refute Map.has_key?(body, "url")
      refute conn.resp_body =~ "ffmpeg"
      assert stored_originals() == []
    end

    test "status requires auth and rejects unknown or malformed names" do
      assert status("#{@base}/status/abcdefghijk.mp4", "Bearer nope").status == 401
      assert status("#{@base}/status/abcdefghijk.mp4").status == 404
      assert status("#{@base}/status/..%2F..%2Fetc%2Fpasswd").status == 404
    end
  end

  describe "ready video" do
    test "status returns share, original and preview URLs only once assets are served", %{video: video} do
      %{"url" => url, "download_url" => download_url, "preview_url" => preview_url, "name" => name} = ready!(video)

      assert url == "#{@base}/s/#{name}"
      assert download_url == "#{@base}/f/#{name}"
      assert preview_url == "#{@base}/v/#{name}.mp4"
      assert name =~ ~r/\A[A-Za-z0-9_-]+\.mp4\z/

      original = get(download_url)
      assert original.status == 200
      assert original.resp_body == video
      assert header(original, "content-type") == "video/mp4"
      assert header(original, "access-control-allow-origin") == "*"

      preview = get(preview_url)
      assert preview.status == 200
      assert header(preview, "content-type") == "video/mp4"
      assert header(preview, "cache-control") =~ "immutable"
      assert header(preview, "x-content-type-options") == "nosniff"
      assert header(preview, "accept-ranges") == "bytes"
      assert byte_size(preview.resp_body) <= 19 * 1024 * 1024
      assert binary_part(preview.resp_body, 4, 4) == "ftyp"

      poster = get("#{@base}/p/#{name}.jpg")
      assert poster.status == 200
      assert header(poster, "content-type") == "image/jpeg"
      assert <<0xFF, 0xD8, _::binary>> = poster.resp_body
    end

    test "preview supports HEAD, ranges and revalidation", %{video: video} do
      %{"preview_url" => preview_url} = ready!(video)
      full = get(preview_url)
      size = byte_size(full.resp_body)

      head = request(:head, preview_url)
      assert head.status == 200
      assert head.resp_body == ""
      assert header(head, "content-length") == Integer.to_string(size)

      part = get(preview_url, [{"range", "bytes=0-99"}])
      assert part.status == 206
      assert part.resp_body == binary_part(full.resp_body, 0, 100)
      assert header(part, "content-range") == "bytes 0-99/#{size}"

      etag = header(full, "etag")
      assert get(preview_url, [{"if-none-match", etag}]).status == 304
      assert get(preview_url, [{"range", "bytes=0-9"}, {"if-range", ~s("stale")}]).status == 200
    end

    test "share page carries escaped absolute metadata with actual preview dimensions", %{video: video} do
      %{"url" => url, "preview_url" => preview_url, "name" => name} =
        ready!(video, "<img src=x onerror=alert(1)> & 'quoted'.mp4")

      {:ok, meta} = BjFiles.Media.load(name)

      page = get(url, [{"host", "evil.example"}])
      html = page.resp_body
      assert page.status == 200
      assert header(page, "content-type") == "text/html; charset=utf-8"
      assert header(page, "cache-control") == "public, max-age=300"
      assert header(page, "x-frame-options") == "DENY"
      csp = header(page, "content-security-policy")
      assert csp =~ "default-src 'none'"
      assert csp =~ "media-src 'self'"
      refute csp =~ "script-src"
      refute csp =~ "unsafe-inline"

      assert meta_content(html, "property", "og:type") == "video.other"
      assert meta_content(html, "property", "og:url") == url
      assert meta_content(html, "property", "og:video") == preview_url
      assert meta_content(html, "property", "og:video:secure_url") == preview_url
      assert meta_content(html, "property", "og:video:type") == "video/mp4"
      assert meta_content(html, "property", "og:video:width") == Integer.to_string(meta["width"])
      assert meta_content(html, "property", "og:video:height") == Integer.to_string(meta["height"])
      assert {meta["width"], meta["height"]} == {320, 240}
      assert meta_content(html, "property", "og:image") == "#{@base}/p/#{name}.jpg"
      assert meta_content(html, "name", "twitter:card") == "player"
      assert meta_content(html, "name", "twitter:player") == "#{@base}/embed/#{name}"
      assert meta_content(html, "name", "twitter:player:width") == "320"
      assert meta_content(html, "name", "twitter:player:stream") == preview_url

      refute html =~ "evil.example"
      refute html =~ "<img src=x"
      refute html =~ "<script"
      assert html =~ ~s(href="/d/#{name}" download)
      assert html =~ ~s(<source src="/v/#{name}.mp4" type="video/mp4">)

      head = request(:head, url)
      assert head.status == 200
      assert head.resp_body == ""

      assert get(url, [{"if-none-match", header(page, "etag")}]).status == 304
    end

    test "embed player can be framed and plays the preview", %{video: video} do
      %{"name" => name} = ready!(video)

      embed = get("#{@base}/embed/#{name}")
      assert embed.status == 200
      assert get_resp_header(embed, "x-frame-options") == []
      csp = header(embed, "content-security-policy")
      assert csp =~ "frame-ancestors https:"
      refute csp =~ "frame-ancestors 'self'"
      refute csp =~ "frame-ancestors 'none'"
      assert embed.resp_body =~ ~s(<source src="/v/#{name}.mp4" type="video/mp4">)
      assert embed.resp_body =~ "playsinline"
    end

    test "download route offers the original as a sanitised attachment", %{video: video} do
      %{"name" => name} = ready!(video, "Café; clip (1).mp4")

      download = get("#{@base}/d/#{name}")
      assert download.status == 200
      assert download.resp_body == video
      disposition = header(download, "content-disposition")
      assert disposition =~ ~r/\Aattachment; filename="[\w .()\-]+\.mp4"; filename\*=UTF-8''[\w.~%\-]+\z/
    end
  end

  describe "legacy originals without metadata" do
    setup do
      name = "legacyClip01.mp4"
      File.write!(Path.join(BjFiles.Store.dir(), name), "raw legacy bytes")
      %{name: name}
    end

    test "share page links the original but advertises no derivatives", %{name: name} do
      page = get("#{@base}/s/#{name}")
      html = page.resp_body

      assert page.status == 200
      assert header(page, "cache-control") == "private, no-cache"
      assert meta_content(html, "property", "og:url") == "#{@base}/s/#{name}"
      assert meta_content(html, "property", "og:type") == "website"
      assert meta_content(html, "name", "twitter:card") == "summary"
      refute html =~ "og:video"
      refute html =~ "og:image"
      refute html =~ "twitter:player"
      refute html =~ "/v/"
      refute html =~ "/p/"
      assert html =~ ~s(href="/d/#{name}" download)
      assert html =~ ~s(href="/f/#{name}")
    end

    test "public GETs never create derivatives", %{name: name} do
      assert get("#{@base}/s/#{name}").status == 200
      assert get("#{@base}/v/#{name}.mp4").status == 404
      assert get("#{@base}/p/#{name}.jpg").status == 404
      assert get("#{@base}/embed/#{name}").status == 404
      assert get("#{@base}/f/#{name}").resp_body == "raw legacy bytes"

      refute File.exists?(Path.join([BjFiles.Store.dir(), ".previews", name]))
    end
  end

  describe "raw original byte ranges" do
    # Plain bytes, not a media file: this only exercises /f range handling.
    setup do
      name = "rangeFixture01.bin"
      File.write!(Path.join(BjFiles.Store.dir(), name), "0123456789")
      %{url: "#{@base}/f/#{name}"}
    end

    test "range requests return partial content", %{url: url} do
      mid = get(url, [{"range", "bytes=2-5"}])
      assert mid.status == 206
      assert mid.resp_body == "2345"
      assert header(mid, "content-range") == "bytes 2-5/10"

      assert get(url, [{"range", "bytes=-3"}]).resp_body == "789"
      assert get(url, [{"range", "bytes=7-"}]).resp_body == "789"
      assert get(url, [{"range", "bytes=8-100"}]).resp_body == "89"
      assert get(url, [{"range", "bytes=10-"}]).status == 416
      assert get(url, [{"range", "bytes=5-2"}]).status == 200
      assert get(url, [{"range", "bytes=0-1,4-5"}]).resp_body == "0123456789"
    end

    test "HEAD reports the length without a body", %{url: url} do
      head = request(:head, url)
      assert head.status == 200
      assert head.resp_body == ""
      assert header(head, "content-length") == "10"

      ranged = request(:head, url, [{"range", "bytes=0-3"}])
      assert ranged.status == 206
      assert header(ranged, "content-length") == "4"
    end

    test "validators allow revalidation and safe resumption", %{url: url} do
      full = get(url)
      etag = header(full, "etag")
      assert header(full, "last-modified") =~ " GMT"

      assert get(url, [{"if-none-match", etag}]).status == 304
      assert get(url, [{"if-none-match", "W/" <> etag}]).status == 304
      assert get(url, [{"range", "bytes=0-1"}, {"if-range", etag}]).status == 206
      assert get(url, [{"range", "bytes=0-1"}, {"if-range", ~s("other")}]).resp_body == "0123456789"
    end

    test "original keeps restrictive headers and allows anonymous cross-origin reads", %{url: url} do
      got = get(url)
      assert header(got, "x-content-type-options") == "nosniff"
      assert header(got, "access-control-allow-origin") == "*"
      assert get_resp_header(got, "access-control-allow-credentials") == []
      csp = header(got, "content-security-policy")
      assert csp =~ "default-src 'none'"
      refute csp =~ "sandbox"
    end
  end

  test "names outside the store are not served on any public route" do
    for path <- [
          "/f/..%2Fetc%2Fpasswd",
          "/f/short.mp4",
          "/f/abcdefghij.mp4",
          "/d/..%2Fetc%2Fpasswd",
          "/s/..%2Fetc%2Fpasswd",
          "/s/abcdefghij.mp4",
          "/embed/..%2Fetc%2Fpasswd",
          "/v/..%2F..%2Fetc%2Fpasswd.mp4",
          "/v/abcdefghij.mp4",
          "/p/..%2F.previews%2Fx.jpg",
          "/p/abcdefghij.mp4.png"
        ] do
      assert call(conn(:get, path)).status == 404, path
    end
  end
end
