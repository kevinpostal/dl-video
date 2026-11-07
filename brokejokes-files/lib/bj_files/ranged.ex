defmodule BjFiles.Ranged do
  @moduledoc """
  Sends a public media file honouring a single `Range: bytes=` request.
  AVPlayer and Safari refuse to play video from servers that ignore Range.

  Files are immutable once published, so responses carry a strong validator
  (`etag`) for `If-None-Match` revalidation and `If-Range` resumption, and are
  readable cross-origin (no credentials) so embedders and players can use them.

  Options:
    * `:content_type` - overrides the type guessed from the path's extension
    * `:disposition` - a `content-disposition` value built by
      `BjFiles.Share.attachment_disposition/2` (never raw client input)
  """
  import Plug.Conn

  def send(conn, path, opts \\ []) do
    %File.Stat{size: size, mtime: mtime, inode: inode} = File.stat!(path, time: :posix)
    etag = ~s("#{Integer.to_string(inode, 16)}-#{Integer.to_string(size, 16)}-#{Integer.to_string(mtime, 16)}")

    conn =
      conn
      |> put_resp_content_type(Keyword.get_lazy(opts, :content_type, fn -> MIME.from_path(path) end), nil)
      |> put_resp_header("accept-ranges", "bytes")
      |> put_resp_header("etag", etag)
      |> put_resp_header("last-modified", http_date(mtime))
      |> put_resp_header("cache-control", "public, max-age=31536000, immutable")
      # Defence in depth should a renderable file ever land in the store.
      # No `sandbox`: Safari/WebKit refuse to play a top-level video under it.
      |> put_resp_header("x-content-type-options", "nosniff")
      |> put_resp_header(
        "content-security-policy",
        "default-src 'none'; media-src 'self'; img-src 'self'; form-action 'none'; base-uri 'none'"
      )
      |> put_resp_header("referrer-policy", "no-referrer")
      |> put_resp_header("access-control-allow-origin", "*")
      |> put_resp_header("access-control-expose-headers", "accept-ranges, content-length, content-range, etag")
      |> put_resp_header("cross-origin-resource-policy", "cross-origin")
      |> put_disposition(opts[:disposition])

    if not_modified?(conn, etag) do
      send_resp(conn, 304, "")
    else
      range = if if_range_matches?(conn, etag), do: get_req_header(conn, "range"), else: []
      send_range(conn, path, parse(range, size), size)
    end
  end

  defp send_range(conn, path, :full, size), do: send_body(conn, 200, path, 0, size)

  defp send_range(conn, path, {:ok, first, last}, size) do
    conn
    |> put_resp_header("content-range", "bytes #{first}-#{last}/#{size}")
    |> send_body(206, path, first, last - first + 1)
  end

  defp send_range(conn, _path, :unsatisfiable, size) do
    conn
    |> put_resp_header("content-range", "bytes */#{size}")
    |> send_resp(416, "")
  end

  defp put_disposition(conn, nil), do: conn
  defp put_disposition(conn, disposition), do: put_resp_header(conn, "content-disposition", disposition)

  # `If-None-Match` uses weak comparison (RFC 9110 §13.1.2).
  defp not_modified?(conn, etag) do
    case get_req_header(conn, "if-none-match") do
      [] ->
        false

      values ->
        values
        |> Enum.flat_map(&String.split(&1, ","))
        |> Enum.map(&(&1 |> String.trim() |> String.replace_prefix("W/", "")))
        |> Enum.any?(&(&1 == "*" or &1 == etag))
    end
  end

  # `If-Range` needs a strong match; a date or stale tag means "send it all".
  defp if_range_matches?(conn, etag) do
    case get_req_header(conn, "if-range") do
      [] -> true
      [value] -> String.trim(value) == etag
      _ -> false
    end
  end

  defp http_date(posix), do: posix |> DateTime.from_unix!() |> Calendar.strftime("%a, %d %b %Y %H:%M:%S GMT")

  defp send_body(%{method: "HEAD"} = conn, status, _path, _offset, length) do
    conn |> put_resp_header("content-length", Integer.to_string(length)) |> send_resp(status, "")
  end

  defp send_body(conn, status, path, offset, length) do
    send_file(conn, status, path, offset, length)
  end

  @doc false
  # Multi-range requests are answered with the whole file, which RFC 9110 allows.
  def parse(["bytes=" <> spec], size) do
    case String.split(spec, "-", parts: 2) do
      ["", suffix] -> suffix_range(Integer.parse(suffix), size)
      [first, ""] -> open_range(Integer.parse(first), size)
      [first, last] -> closed_range(Integer.parse(first), Integer.parse(last), size)
      _ -> :full
    end
  end

  def parse(_, _size), do: :full

  defp suffix_range({n, ""}, size) when n > 0 and size > 0, do: {:ok, max(size - n, 0), size - 1}
  defp suffix_range({_, ""}, _size), do: :unsatisfiable
  defp suffix_range(_, _size), do: :full

  defp open_range({first, ""}, size) when first >= 0 and first < size, do: {:ok, first, size - 1}
  defp open_range({first, ""}, _size) when first >= 0, do: :unsatisfiable
  defp open_range(_, _size), do: :full

  defp closed_range({first, ""}, {last, ""}, size) when first >= 0 and first <= last and first < size,
    do: {:ok, first, min(last, size - 1)}

  defp closed_range({first, ""}, {last, ""}, _size) when first >= 0 and first <= last, do: :unsatisfiable
  defp closed_range(_, _, _size), do: :full
end
