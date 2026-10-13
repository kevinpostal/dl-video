defmodule BjFiles.Ranged do
  @moduledoc """
  Sends a file honouring a single `Range: bytes=` request. AVPlayer and Safari
  refuse to play video from servers that ignore Range.
  """
  import Plug.Conn

  def send(conn, path) do
    size = File.stat!(path).size

    conn =
      conn
      |> put_resp_content_type(MIME.from_path(path), nil)
      |> put_resp_header("accept-ranges", "bytes")
      |> put_resp_header("cache-control", "public, max-age=31536000, immutable")
      # Defence in depth should a renderable file ever land in the store.
      # No `sandbox`: Safari/WebKit refuse to play a top-level video under it.
      |> put_resp_header("x-content-type-options", "nosniff")
      |> put_resp_header(
        "content-security-policy",
        "default-src 'none'; media-src 'self'; img-src 'self'; form-action 'none'; base-uri 'none'"
      )
      |> put_resp_header("referrer-policy", "no-referrer")

    case parse(get_req_header(conn, "range"), size) do
      :full ->
        send_body(conn, 200, path, 0, size)

      {:ok, first, last} ->
        conn
        |> put_resp_header("content-range", "bytes #{first}-#{last}/#{size}")
        |> send_body(206, path, first, last - first + 1)

      :unsatisfiable ->
        conn
        |> put_resp_header("content-range", "bytes */#{size}")
        |> send_resp(416, "")
    end
  end

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

  defp open_range({first, ""}, size) when first < size, do: {:ok, first, size - 1}
  defp open_range({_, ""}, _size), do: :unsatisfiable
  defp open_range(_, _size), do: :full

  defp closed_range({first, ""}, {last, ""}, size) when first <= last and first < size,
    do: {:ok, first, min(last, size - 1)}

  defp closed_range({_, ""}, {_, ""}, _size), do: :unsatisfiable
  defp closed_range(_, _, _size), do: :full
end
