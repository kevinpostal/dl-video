defmodule BjFiles.Page do
  @moduledoc """
  Static HTML for public share pages. No script: native `<video>`/`<audio>`
  controls play the media, so the CSP can forbid scripts outright and only
  allow the exact inline stylesheet by hash.

  Metadata URLs are absolute (from `BjFiles.Share.base_url/0`); in-page media
  and links are same-origin paths so the page also works when reached through
  another hostname. Every interpolated value is HTML-escaped.
  """

  alias BjFiles.Share

  @page_css """
  :root{color-scheme:dark}
  *{box-sizing:border-box}
  body{margin:0;min-height:100vh;display:flex;align-items:center;justify-content:center;background:#111;color:#f2f2f2;font:16px/1.5 system-ui,-apple-system,"Segoe UI",Roboto,sans-serif}
  main{width:100%;max-width:960px;padding:16px}
  h1{margin:0 0 12px;font-size:1.25rem;overflow-wrap:anywhere}
  video,img{display:block;width:100%;height:auto;max-height:80vh;object-fit:contain;background:#000;border-radius:8px}
  audio{display:block;width:100%}
  .meta{margin:8px 0 16px;color:#c8c8c8}
  .actions{display:flex;flex-wrap:wrap;gap:12px;margin:0}
  .button{display:inline-block;min-height:44px;padding:11px 20px;border-radius:8px;background:#2f6fed;color:#fff;font-weight:600;text-decoration:none}
  .button.secondary{background:#3a3a3a}
  a:focus-visible{outline:3px solid #ffbf47;outline-offset:2px}
  """

  @embed_css """
  html,body{margin:0;height:100%;background:#000}
  video{display:block;width:100%;height:100%;object-fit:contain}
  """

  @page_hash "'sha256-" <> Base.encode64(:crypto.hash(:sha256, @page_css)) <> "'"
  @embed_hash "'sha256-" <> Base.encode64(:crypto.hash(:sha256, @embed_css)) <> "'"

  @doc "CSP for the share page: own media and the hashed stylesheet only; never framed."
  def page_csp do
    "default-src 'none'; style-src #{@page_hash}; img-src 'self'; media-src 'self'; " <>
      "frame-ancestors 'none'; base-uri 'none'; form-action 'none'"
  end

  @doc "CSP for the player card iframe: may be framed by any https site (Twitter/X player cards)."
  def embed_csp do
    "default-src 'none'; style-src #{@embed_hash}; img-src 'self'; media-src 'self'; " <>
      "frame-ancestors https:; base-uri 'none'; form-action 'none'"
  end

  @doc "Share page for a ready or legacy view from `BjFiles.Share`."
  def share(view) do
    name = view.name
    share_url = Share.url(Share.share_path(name))
    description = description(view)

    [
      head_open(view.title),
      meta_name("description", description),
      ~s(<link rel="canonical" href="#{e(share_url)}">\n),
      meta_prop("og:site_name", site_name()),
      meta_prop("og:type", og_type(view)),
      meta_prop("og:url", share_url),
      meta_prop("og:title", view.title),
      meta_prop("og:description", description),
      image_meta(view),
      video_meta(view),
      twitter_meta(view, description),
      style(@page_css),
      "</head>\n<body>\n<main>\n",
      "<h1>", e(view.title), "</h1>\n",
      media_body(view),
      ~s(<p class="meta">), e(description), "</p>\n",
      actions(view),
      "</main>\n</body>\n</html>\n"
    ]
    |> IO.iodata_to_binary()
  end

  @doc "Shown while a new upload is still being prepared; advertises no media."
  def preparing(name) do
    [
      head_open("Preparing upload"),
      ~s(<meta name="robots" content="noindex">\n),
      ~s(<meta http-equiv="refresh" content="5">\n),
      style(@page_css),
      "</head>\n<body>\n<main>\n<h1>Preparing upload</h1>\n",
      ~s(<p class="meta" role="status">This upload is still being prepared. ),
      ~s(The page refreshes automatically; you can also <a href="#{e(Share.share_path(name))}">reload it</a>.</p>\n),
      "</main>\n</body>\n</html>\n"
    ]
    |> IO.iodata_to_binary()
  end

  @doc "Minimal same-origin player for `twitter:player`. Only for ready previews."
  def embed(%{preview?: true} = view) do
    name = view.name

    [
      head_open(view.title),
      ~s(<meta name="robots" content="noindex">\n),
      style(@embed_css),
      "</head>\n<body>\n",
      ~s(<video controls playsinline preload="metadata"),
      dims_attrs(view),
      poster_attr(view),
      ~s( aria-label="#{e(view.title)}">),
      ~s(<source src="#{e(Share.preview_path(name))}" type="video/mp4">),
      ~s(<a href="#{e(Share.share_path(name))}" target="_blank" rel="noopener">Open video</a>),
      "</video>\n</body>\n</html>\n"
    ]
    |> IO.iodata_to_binary()
  end

  defp head_open(title) do
    [
      "<!doctype html>\n<html lang=\"en\">\n<head>\n",
      ~s(<meta charset="utf-8">\n),
      ~s(<meta name="viewport" content="width=device-width, initial-scale=1">\n),
      "<title>", e(title), "</title>\n"
    ]
  end

  defp style(css), do: ["<style>", css, "</style>\n"]

  defp og_type(%{kind: "video", preview?: true}), do: "video.other"
  defp og_type(_), do: "website"

  # Thumbnail fallback: a poster when one was generated, otherwise an image
  # original (legacy or ready) since that file is itself the picture.
  defp image_meta(view) do
    case og_image(view) do
      nil ->
        []

      {url, type} ->
        [
          meta_prop("og:image", url),
          if(https?(url), do: meta_prop("og:image:secure_url", url), else: []),
          if(type, do: meta_prop("og:image:type", type), else: []),
          if(view.poster? and view.width,
            do: [meta_prop("og:image:width", view.width), meta_prop("og:image:height", view.height)],
            else: []
          ),
          meta_prop("og:image:alt", view.title)
        ]
    end
  end

  defp og_image(%{poster?: true, name: name}), do: {Share.url(Share.poster_path(name)), "image/jpeg"}
  defp og_image(%{kind: "image", name: name}), do: {Share.url(Share.original_path(name)), nil}
  defp og_image(_), do: nil

  defp video_meta(%{kind: "video", preview?: true} = view) do
    url = Share.url(Share.preview_path(view.name))

    [
      meta_prop("og:video", url),
      if(https?(url), do: meta_prop("og:video:secure_url", url), else: []),
      meta_prop("og:video:type", "video/mp4"),
      if(view.width,
        do: [meta_prop("og:video:width", view.width), meta_prop("og:video:height", view.height)],
        else: []
      )
    ]
  end

  defp video_meta(_), do: []

  defp twitter_meta(view, description) do
    image = og_image(view)

    [
      meta_name("twitter:card", twitter_card(view, image)),
      meta_name("twitter:title", view.title),
      meta_name("twitter:description", description),
      case image do
        {url, _} -> [meta_name("twitter:image", url), meta_name("twitter:image:alt", view.title)]
        nil -> []
      end,
      if(twitter_player?(view, image), do: twitter_player(view), else: [])
    ]
  end

  defp twitter_card(view, image) do
    cond do
      twitter_player?(view, image) -> "player"
      image -> "summary_large_image"
      true -> "summary"
    end
  end

  # X requires an https player, explicit dimensions and a fallback image.
  defp twitter_player?(view, image) do
    view.kind == "video" and view.preview? and view.width != nil and image != nil and
      https?(Share.base_url())
  end

  defp twitter_player(view) do
    [
      meta_name("twitter:player", Share.url(Share.embed_path(view.name))),
      meta_name("twitter:player:width", view.width),
      meta_name("twitter:player:height", view.height),
      meta_name("twitter:player:stream", Share.url(Share.preview_path(view.name))),
      meta_name("twitter:player:stream:content_type", "video/mp4")
    ]
  end

  defp media_body(%{kind: "video", preview?: true} = view) do
    [
      ~s(<video controls playsinline preload="metadata"),
      dims_attrs(view),
      poster_attr(view),
      ~s( aria-label="#{e(view.title)}">),
      ~s(<source src="#{e(Share.preview_path(view.name))}" type="video/mp4">),
      unplayable(view),
      "</video>\n"
    ]
  end

  defp media_body(%{kind: "video", original_inline?: true} = view) do
    [
      ~s(<video controls playsinline preload="metadata"),
      poster_attr(view),
      ~s( aria-label="#{e(view.title)}" src="#{e(Share.original_path(view.name))}">),
      unplayable(view),
      "</video>\n"
    ]
  end

  defp media_body(%{kind: "image", original_inline?: true} = view) do
    [~s(<img src="#{e(Share.original_path(view.name))}" alt="#{e(view.title)}"), dims_attrs(view), ">\n"]
  end

  defp media_body(%{kind: "audio"} = view) do
    {src, type} =
      if view.preview?,
        do: {Share.preview_path(view.name), ~s( type="audio/mp4")},
        else: {Share.original_path(view.name), ""}

    [
      if(view.poster?, do: ~s(<img src="#{e(Share.poster_path(view.name))}" alt=""#{dims_attrs(view)}>\n), else: []),
      ~s(<audio controls preload="metadata" aria-label="#{e(view.title)}">),
      ~s(<source src="#{e(src)}"#{type}>),
      unplayable(view),
      "</audio>\n"
    ]
  end

  defp media_body(%{poster?: true} = view) do
    [~s(<img src="#{e(Share.poster_path(view.name))}" alt="#{e(view.title)}"), dims_attrs(view), ">\n"]
  end

  defp media_body(_view), do: []

  defp unplayable(view) do
    ~s(<p>This browser cannot play it here. <a href="#{e(Share.download_path(view.name))}" download>Download the original</a>.</p>)
  end

  defp actions(view) do
    size = if view.original_bytes, do: " (" <> human_bytes(view.original_bytes) <> ")", else: ""

    [
      ~s(<p class="actions">),
      ~s(<a class="button" href="#{e(Share.download_path(view.name))}" download>Download original#{e(size)}</a>),
      ~s(<a class="button secondary" href="#{e(Share.original_path(view.name))}">Open original</a>),
      "</p>\n"
    ]
  end

  defp dims_attrs(%{width: w, height: h}) when is_integer(w) and is_integer(h),
    do: ~s( width="#{w}" height="#{h}")

  defp dims_attrs(_), do: ""

  defp poster_attr(%{poster?: true, name: name}), do: ~s( poster="#{e(Share.poster_path(name))}")
  defp poster_attr(_), do: ""

  defp description(view) do
    parts =
      [
        kind_label(view.kind),
        view.duration && format_duration(view.duration),
        view.width && "#{view.width}×#{view.height}",
        view.state == :legacy && "original file"
      ]
      |> Enum.filter(& &1)

    Enum.join(parts, " · ")
  end

  defp kind_label("video"), do: "Video"
  defp kind_label("image"), do: "Image"
  defp kind_label("audio"), do: "Audio"
  defp kind_label(_), do: "File"

  defp format_duration(seconds) do
    total = round(seconds)
    {h, m, s} = {div(total, 3600), div(rem(total, 3600), 60), rem(total, 60)}
    pad = &String.pad_leading(Integer.to_string(&1), 2, "0")
    if h > 0, do: "#{h}:#{pad.(m)}:#{pad.(s)}", else: "#{m}:#{pad.(s)}"
  end

  defp human_bytes(bytes) when bytes >= 1024 * 1024 * 1024,
    do: :erlang.float_to_binary(bytes / (1024 * 1024 * 1024), decimals: 1) <> " GB"

  defp human_bytes(bytes) when bytes >= 1024 * 1024,
    do: :erlang.float_to_binary(bytes / (1024 * 1024), decimals: 1) <> " MB"

  defp human_bytes(bytes) when bytes >= 1024, do: "#{div(bytes, 1024)} KB"
  defp human_bytes(bytes), do: "#{bytes} B"

  defp site_name, do: URI.parse(Share.base_url()).host || ""

  defp https?(url), do: String.starts_with?(url, "https://")

  defp meta_prop(property, content), do: ~s(<meta property="#{property}" content="#{e(content)}">\n)
  defp meta_name(name, content), do: ~s(<meta name="#{name}" content="#{e(content)}">\n)

  defp e(value) when is_binary(value), do: Plug.HTML.html_escape(value)
  defp e(value) when is_integer(value), do: Integer.to_string(value)
end
