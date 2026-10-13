defmodule BjFiles.RouterTest do
  use ExUnit.Case, async: false
  import Plug.Test
  import Plug.Conn

  @opts BjFiles.Router.init([])
  @auth "Bearer test-token"

  setup do
    File.rm_rf!(BjFiles.Store.dir())
    File.mkdir_p!(BjFiles.Store.dir())
    :ok
  end

  defp upload(body, filename, auth \\ @auth, field \\ "file") do
    boundary = "bjboundary"

    payload =
      "--#{boundary}\r\n" <>
        ~s(Content-Disposition: form-data; name="#{field}"; filename="#{filename}"\r\n) <>
        "Content-Type: video/mp4\r\n\r\n" <> body <> "\r\n--#{boundary}--\r\n"

    conn(:post, "/upload", payload)
    |> put_req_header("content-type", "multipart/form-data; boundary=#{boundary}")
    |> put_req_header("authorization", auth)
    |> BjFiles.Router.call(@opts)
  end

  defp get_file(url, headers \\ []) do
    path = URI.parse(url).path

    Enum.reduce(headers, conn(:get, path), fn {k, v}, c -> put_req_header(c, k, v) end)
    |> BjFiles.Router.call(@opts)
  end

  test "upload requires the bearer token" do
    conn = upload("x", "a.mp4", "Bearer nope")
    assert conn.status == 401
    assert File.ls!(BjFiles.Store.dir()) == []
  end

  test "uploaded file is served back with its content type" do
    conn = upload("hello video", "My Clip.MP4")
    assert conn.status == 201
    %{"url" => url} = Jason.decode!(conn.resp_body)
    assert url =~ ~r{\Ahttps://files\.example\.com/f/[A-Za-z0-9_-]+\.mp4\z}

    got = get_file(url)
    assert got.status == 200
    assert got.resp_body == "hello video"
    assert get_resp_header(got, "content-type") == ["video/mp4"]
    assert get_resp_header(got, "accept-ranges") == ["bytes"]
    assert get_resp_header(got, "x-content-type-options") == ["nosniff"]
    assert [csp] = get_resp_header(got, "content-security-policy")
    assert csp =~ "default-src 'none'"
    refute csp =~ "sandbox"
  end

  test "non-media uploads are refused and never stored" do
    for name <- ["evil.html", "evil.svg", "noext"] do
      assert upload("<script>alert(1)</script>", name).status == 415
    end

    assert File.ls!(BjFiles.Store.dir()) == []
  end

  test "range requests return partial content" do
    %{"url" => url} = upload("0123456789", "v.mp4").resp_body |> Jason.decode!()

    mid = get_file(url, [{"range", "bytes=2-5"}])
    assert mid.status == 206
    assert mid.resp_body == "2345"
    assert get_resp_header(mid, "content-range") == ["bytes 2-5/10"]

    assert get_file(url, [{"range", "bytes=-3"}]).resp_body == "789"
    assert get_file(url, [{"range", "bytes=7-"}]).resp_body == "789"
    assert get_file(url, [{"range", "bytes=8-100"}]).resp_body == "89"
    assert get_file(url, [{"range", "bytes=10-"}]).status == 416
  end

  test "names outside the store are not served" do
    for path <- ["/f/..%2Fetc%2Fpasswd", "/f/short.mp4", "/f/abcdefghij.mp4"] do
      assert (conn(:get, path) |> BjFiles.Router.call(@opts)).status == 404
    end
  end

  test "oversized uploads are rejected" do
    assert upload(String.duplicate("x", 2048), "big.mp4").status == 413
  end

  test "missing file field is a 400" do
    assert upload("x", "a.mp4", @auth, "other").status == 400
  end
end
