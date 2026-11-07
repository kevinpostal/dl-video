defmodule BjFiles.PageTest do
  use ExUnit.Case, async: false

  alias BjFiles.{Page, Share}

  @base "https://files.example.com"
  @hostile ~s|</title><script>alert("x")</script>&<img src=x onerror=alert(1)>'|

  defp view(overrides) do
    Map.merge(
      %{
        state: :ready,
        name: "abcdef123456.mov",
        title: "Clip",
        kind: "video",
        width: 1280,
        height: 720,
        duration: 62.4,
        preview?: true,
        poster?: true,
        original_inline?: false,
        original_bytes: 23_875_000
      },
      Map.new(overrides)
    )
  end

  defp meta_content(html, attr, key) do
    case Regex.run(~r/<meta #{attr}="#{Regex.escape(key)}" content="([^"]*)">/, html) do
      [_, value] -> value
      nil -> nil
    end
  end

  defp style_hash(html) do
    [_, css] = Regex.run(~r{<style>(.*)</style>}s, html)
    "'sha256-" <> Base.encode64(:crypto.hash(:sha256, css)) <> "'"
  end

  test "ready video page advertises the preview with its own dimensions and original suffix kept" do
    html = Page.share(view([]))

    assert meta_content(html, "property", "og:type") == "video.other"
    assert meta_content(html, "property", "og:url") == "#{@base}/s/abcdef123456.mov"
    assert meta_content(html, "property", "og:video") == "#{@base}/v/abcdef123456.mov.mp4"
    assert meta_content(html, "property", "og:video:width") == "1280"
    assert meta_content(html, "property", "og:video:height") == "720"
    assert meta_content(html, "property", "og:image") == "#{@base}/p/abcdef123456.mov.jpg"
    assert meta_content(html, "property", "og:image:type") == "image/jpeg"
    assert meta_content(html, "name", "twitter:card") == "player"
    assert meta_content(html, "name", "twitter:player") == "#{@base}/embed/abcdef123456.mov"
    assert meta_content(html, "name", "twitter:player:height") == "720"
    assert meta_content(html, "property", "og:description") == "Video · 1:02 · 1280×720"
    assert html =~ ~s(<video controls playsinline preload="metadata" width="1280" height="720" poster="/p/abcdef123456.mov.jpg")
    assert html =~ "Download original (22.8 MB)"
    assert html =~ ~s(<meta name="viewport")
    assert html =~ ~s(<html lang="en">)
  end

  test "hostile titles are escaped everywhere" do
    for html <- [Page.share(view(title: @hostile)), Page.embed(view(title: @hostile))] do
      refute html =~ "<script"
      refute html =~ "<img src=x"
      refute html =~ ~s|alert("x")|
      assert html =~ "&lt;/title&gt;&lt;script&gt;"
    end
  end

  test "inline stylesheet is the only style the CSP allows, and no script is allowed" do
    assert Page.page_csp() =~ "style-src " <> style_hash(Page.share(view([])))
    assert Page.embed_csp() =~ "style-src " <> style_hash(Page.embed(view([])))
    assert Page.page_csp() =~ "style-src " <> style_hash(Page.preparing("abcdef123456.mov"))

    for csp <- [Page.page_csp(), Page.embed_csp()] do
      assert csp =~ "default-src 'none'"
      assert csp =~ "media-src 'self'"
      refute csp =~ "script-src"
      refute csp =~ "unsafe"
    end

    assert Page.page_csp() =~ "frame-ancestors 'none'"
    assert Page.embed_csp() =~ "frame-ancestors https:"
  end

  test "video without a preview falls back to its poster thumbnail" do
    html = Page.share(view(preview?: false))

    assert meta_content(html, "property", "og:type") == "website"
    assert meta_content(html, "property", "og:image") == "#{@base}/p/abcdef123456.mov.jpg"
    assert meta_content(html, "name", "twitter:card") == "summary_large_image"
    refute html =~ "og:video"
    refute html =~ "twitter:player"
    refute html =~ "/v/"
    assert html =~ ~s(<img src="/p/abcdef123456.mov.jpg")
  end

  test "legacy page offers only the original" do
    html =
      Page.share(
        view(state: :legacy, title: "Shared video", width: nil, height: nil, duration: nil, preview?: false, poster?: false)
      )

    assert meta_content(html, "name", "twitter:card") == "summary"
    refute html =~ "og:image"
    refute html =~ "og:video"
    refute html =~ "/p/"
    assert html =~ ~s(href="/d/abcdef123456.mov" download)
    assert html =~ ~s(href="/f/abcdef123456.mov")
  end

  test "legacy image uses the original itself as the thumbnail" do
    html =
      Page.share(
        view(
          state: :legacy,
          name: "abcdef123456.png",
          kind: "image",
          width: nil,
          height: nil,
          duration: nil,
          preview?: false,
          poster?: false,
          original_inline?: true
        )
      )

    assert meta_content(html, "property", "og:image") == "#{@base}/f/abcdef123456.png"
    assert html =~ ~s(<img src="/f/abcdef123456.png")
  end

  test "preparing page advertises no media and is not a share card" do
    html = Page.preparing("abcdef123456.mov")
    refute html =~ "og:"
    refute html =~ "twitter:"
    refute html =~ "<video"
    assert html =~ ~s(role="status")
  end

  test "player card needs an https public URL" do
    previous = Application.fetch_env!(:bj_files, :public_url)
    Application.put_env(:bj_files, :public_url, "http://localhost:4000/")
    on_exit(fn -> Application.put_env(:bj_files, :public_url, previous) end)

    html = Page.share(view([]))
    assert meta_content(html, "name", "twitter:card") == "summary_large_image"
    assert meta_content(html, "property", "og:video") == "http://localhost:4000/v/abcdef123456.mov.mp4"
    refute html =~ "og:video:secure_url"
    refute html =~ "twitter:player"
  end

  describe "attachment_disposition/2" do
    test "header-unsafe characters never reach the header" do
      value = Share.attachment_disposition("abcdef123456.mov", "a\"b\r\nX-Evil: 1;\\/c é")

      refute value =~ ~r/[\r\n]/
      assert value =~ ~r/\Aattachment; filename="[\w .()\-]+\.mov"; filename\*=UTF-8''[\w.~%\-]+\z/
      assert value =~ "filename*=UTF-8''"
      assert value =~ "%C3%A9.mov"
    end

    test "falls back to the stored name without a usable title" do
      assert Share.attachment_disposition("abcdef123456.mov", nil) ==
               ~s(attachment; filename="abcdef123456.mov"; filename*=UTF-8''abcdef123456.mov)

      assert Share.attachment_disposition("abcdef123456.mov", " ../ ") ==
               ~s(attachment; filename="abcdef123456.mov"; filename*=UTF-8''abcdef123456.mov)
    end
  end
end
