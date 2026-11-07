defmodule BjFiles.Router do
  @moduledoc """
  Authenticated API (Bearer token):
    POST /upload          multipart field `file`; stores the original and admits
                          preparation. 202 `{status_url, name}`, or 201 with the
                          ready payload if preparation already finished.
    GET  /status/:name    202 while preparing; 200 `{url, download_url,
                          preview_url, name}` once ready; 422/504 on failure.

  Public (GET/HEAD, never triggers encoding):
    /s/:name              share page with OpenGraph/Twitter metadata
    /embed/:name          minimal player for `twitter:player`
    /f/:name              original bytes, ranges (existing links)
    /d/:name              original as an attachment download
    /v/:name.mp4          bounded MP4 preview
    /p/:name.jpg          JPEG poster
    /health
  """
  use Plug.Router
  require Logger

  alias BjFiles.{Media, Page, Ranged, Share, Store}

  @ready_page_cache "public, max-age=300"
  @revalidate_cache "private, no-cache"

  plug Plug.Logger
  plug :security_headers
  plug :match
  plug :dispatch

  get "/health" do
    send_resp(conn, 200, "ok")
  end

  post "/upload" do
    with :ok <- authorize(conn),
         {:ok, conn} <- parse_multipart(conn),
         {:ok, %Plug.Upload{path: tmp, filename: filename}} <- upload_field(conn),
         {:ok, name} <- Store.put(tmp, filename),
         :ok <- admit(name, filename) do
      Logger.info("stored #{name} from #{inspect(filename)}; preparing")

      case Media.status(name) do
        {:ok, meta} -> json(conn, 201, Share.ready_payload(name, meta))
        _ -> json(conn, 202, %{status_url: Share.status_url(name), name: name})
      end
    else
      :unauthorized -> json(conn, 401, %{error: "unauthorized"})
      :too_large -> json(conn, 413, %{error: "file too large"})
      :bad_request -> json(conn, 400, %{error: "malformed multipart body"})
      :missing -> json(conn, 400, %{error: "missing multipart field \"file\""})
      {:error, :unsupported_type} -> json(conn, 415, %{error: "only video, audio or image files"})
      {:admission, reason} -> admission_error(conn, reason)
      {:error, reason} -> store_error(conn, reason)
    end
  end

  get "/status/:name" do
    case authorize(conn) do
      :ok -> upload_status(conn, name)
      :unauthorized -> json(conn, 401, %{error: "unauthorized"})
    end
  end

  match "/s/:name", via: [:get, :head] do
    with {:ok, original} <- Store.path(name) do
      case Media.status(name) do
        {:ok, meta} ->
          send_html(conn, 200, Page.share(Share.ready_view(name, original, meta)), @ready_page_cache, Page.page_csp())

        :processing ->
          send_html(conn, 202, Page.preparing(name), "no-store", Page.page_csp())

        # No metadata yet (pre-dates previews) or a failed backfill: the original
        # is still offered, nothing derived is advertised, and the page is
        # revalidated so a later backfill shows up.
        _ ->
          send_html(conn, 200, Page.share(Share.legacy_view(name, original)), @revalidate_cache, Page.page_csp())
      end
    else
      _ -> not_found(conn)
    end
  end

  match "/embed/:name", via: [:get, :head] do
    with {:ok, original} <- Store.path(name),
         {:ok, meta} <- Media.status(name),
         %{kind: "video", preview?: true} = view <- Share.ready_view(name, original, meta) do
      send_html(conn, 200, Page.embed(view), @ready_page_cache, Page.embed_csp())
    else
      _ -> not_found(conn)
    end
  end

  match "/f/:name", via: [:get, :head] do
    case Store.path(name) do
      {:ok, path} -> Ranged.send(conn, path)
      :error -> not_found(conn)
    end
  end

  match "/d/:name", via: [:get, :head] do
    case Store.path(name) do
      {:ok, path} ->
        title =
          case Media.load(name) do
            {:ok, %{"title" => title}} -> title
            _ -> nil
          end

        Ranged.send(conn, path, disposition: Share.attachment_disposition(name, title))

      :error ->
        not_found(conn)
    end
  end

  match "/v/:file", via: [:get, :head] do
    serve_asset(conn, file, ".mp4", :preview, "video/mp4")
  end

  match "/p/:file", via: [:get, :head] do
    serve_asset(conn, file, ".jpg", :poster, "image/jpeg")
  end

  match _ do
    not_found(conn)
  end

  defp security_headers(conn, _opts), do: put_resp_header(conn, "x-content-type-options", "nosniff")

  defp upload_status(conn, name) do
    result = if Share.valid_name?(name), do: Media.status(name), else: :error

    case result do
      {:ok, meta} ->
        case Store.path(name) do
          {:ok, _} -> json(conn, 200, Share.ready_payload(name, meta))
          :error -> json(conn, 404, %{error: "not found"})
        end

      :processing ->
        conn
        |> put_resp_header("retry-after", "2")
        |> json(202, %{status: "processing", status_url: Share.status_url(name), name: name})

      {:error, :timeout} ->
        json(conn, 504, %{error: "media processing timed out"})

      {:error, reason} when reason in [:invalid_media, :unsupported_media] ->
        json(conn, 422, %{error: "invalid or unsupported media"})

      {:error, reason} ->
        Logger.warning("preparation of #{name} failed: #{inspect(reason)}")
        json(conn, 422, %{error: "media processing failed"})

      :error ->
        json(conn, 404, %{error: "not found"})
    end
  end

  # Hands the stored original to the bounded preparation queue. If it is not
  # admitted the original is removed so no URL for it can ever be returned.
  defp admit(name, filename) do
    result =
      try do
        with {:ok, path} <- Store.path(name), do: Media.enqueue(path, name, filename)
      rescue
        e -> {:error, {:exception, Exception.message(e)}}
      catch
        :exit, reason -> {:error, {:exit, reason}}
      end

    case result do
      :ok ->
        :ok

      {:error, reason} ->
        discard(name)
        {:admission, reason}

      :error ->
        {:admission, :missing_original}
    end
  end

  defp discard(name) do
    case Store.path(name) do
      {:ok, path} -> File.rm(path)
      :error -> :ok
    end
  end

  defp admission_error(conn, :busy) do
    conn |> put_resp_header("retry-after", "10") |> json(503, %{error: "server busy, retry later"})
  end

  defp admission_error(conn, :timeout), do: json(conn, 504, %{error: "media processing timed out"})
  defp admission_error(conn, :invalid_media), do: json(conn, 422, %{error: "invalid or corrupt media"})
  defp admission_error(conn, :unsupported_media), do: json(conn, 415, %{error: "unsupported media"})

  defp admission_error(conn, reason) do
    Logger.error("could not admit upload for preparation: #{inspect(reason)}")
    json(conn, 500, %{error: "could not start media processing"})
  end

  defp store_error(conn, reason) do
    Logger.error("store failed: #{inspect(reason)}")
    json(conn, 500, %{error: "store failed"})
  end

  defp serve_asset(conn, file, suffix, kind, content_type) do
    with true <- String.ends_with?(file, suffix),
         name = String.replace_suffix(file, suffix, ""),
         {:ok, path} <- Share.asset(name, kind) do
      Ranged.send(conn, path, content_type: content_type)
    else
      _ -> not_found(conn)
    end
  end

  defp send_html(conn, status, html, cache_control, csp) do
    etag = ~s(W/") <> Base.url_encode64(:crypto.hash(:sha256, html), padding: false) <> ~s(")

    conn =
      conn
      |> put_resp_content_type("text/html", "utf-8")
      |> put_resp_header("cache-control", cache_control)
      |> put_resp_header("content-security-policy", csp)
      |> put_resp_header("referrer-policy", "strict-origin-when-cross-origin")
      |> frame_options(csp)

    if status == 200 and etag in if_none_match(conn) do
      conn |> put_resp_header("etag", etag) |> send_resp(304, "")
    else
      conn = if status == 200, do: put_resp_header(conn, "etag", etag), else: conn
      send_resp(conn, status, html)
    end
  end

  # Legacy browsers ignore `frame-ancestors`; only the share page refuses framing.
  defp frame_options(conn, csp) do
    if String.contains?(csp, "frame-ancestors 'none'"),
      do: put_resp_header(conn, "x-frame-options", "DENY"),
      else: conn
  end

  defp if_none_match(conn) do
    conn
    |> get_req_header("if-none-match")
    |> Enum.flat_map(&String.split(&1, ","))
    |> Enum.map(&String.trim/1)
  end

  defp not_found(conn) do
    conn
    |> put_resp_header("cache-control", "no-cache")
    |> send_resp(404, "not found")
  end

  defp authorize(conn) do
    expected = "Bearer " <> Application.fetch_env!(:bj_files, :upload_token)

    case get_req_header(conn, "authorization") do
      [given] -> if Plug.Crypto.secure_compare(given, expected), do: :ok, else: :unauthorized
      _ -> :unauthorized
    end
  end

  # Parsed only after auth so anonymous clients can't make us spool large bodies.
  defp parse_multipart(conn) do
    opts =
      Plug.Parsers.init(
        parsers: [:multipart],
        pass: ["*/*"],
        length: Application.fetch_env!(:bj_files, :max_upload_bytes)
      )

    {:ok, Plug.Parsers.call(conn, opts)}
  rescue
    Plug.Parsers.RequestTooLargeError -> :too_large
    Plug.Parsers.ParseError -> :bad_request
    Plug.Parsers.BadEncodingError -> :bad_request
  end

  defp upload_field(conn) do
    case conn.body_params do
      %{"file" => %Plug.Upload{} = upload} -> {:ok, upload}
      _ -> :missing
    end
  end

  defp json(conn, status, body) do
    conn
    |> put_resp_content_type("application/json")
    |> put_resp_header("cache-control", "no-store")
    |> send_resp(status, Jason.encode!(body))
  end
end
