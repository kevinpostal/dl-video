defmodule BjFiles.Router do
  @moduledoc """
  POST /upload   (Bearer token, multipart field `file`) -> 201 {"url": ...}
  GET  /f/:name  public download with single-range support (iOS video playback)
  GET  /health
  """
  use Plug.Router
  require Logger

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
         %Plug.Upload{path: tmp, filename: filename} <- conn.body_params["file"] || :missing,
         {:ok, name} <- BjFiles.Store.put(tmp, filename) do
      url = String.trim_trailing(Application.fetch_env!(:bj_files, :public_url), "/") <> "/f/" <> name
      Logger.info("stored #{name} from #{inspect(filename)}")
      json(conn, 201, %{url: url, name: name})
    else
      :unauthorized -> json(conn, 401, %{error: "unauthorized"})
      :too_large -> json(conn, 413, %{error: "file too large"})
      :missing -> json(conn, 400, %{error: "missing multipart field \"file\""})
      {:error, :unsupported_type} -> json(conn, 415, %{error: "only video, audio or image files"})
      {:error, reason} -> json(conn, 500, %{error: "store failed: #{inspect(reason)}"})
    end
  end

  match "/f/:name", via: [:get, :head] do
    case BjFiles.Store.path(name) do
      {:ok, path} -> BjFiles.Ranged.send(conn, path)
      :error -> send_resp(conn, 404, "not found")
    end
  end

  match _ do
    send_resp(conn, 404, "not found")
  end

  defp security_headers(conn, _opts), do: put_resp_header(conn, "x-content-type-options", "nosniff")

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
  end

  defp json(conn, status, body) do
    conn
    |> put_resp_content_type("application/json")
    |> send_resp(status, Jason.encode!(body))
  end
end
