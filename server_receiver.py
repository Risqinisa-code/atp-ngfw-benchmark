#!/usr/bin/env python3
"""
server_receiver.py  -- jalankan di Host B (10.0.10.105), Python 3.9+

Web server kecil yang menerima upload file via HTTP POST (multipart) ke
/upload, membaca lalu membuang isinya, dan membalas 200 OK. Tidak menyimpan
berkas; tujuannya hanya agar berkas MELEWATI DUT untuk diinspeksi TE/TEX.

Jalankan:
  python server_receiver.py            # default port 8080
  python server_receiver.py --port 80  # jika TE hanya aktif untuk HTTP port 80

Biarkan berjalan selama seluruh eksperimen. Hentikan dengan Ctrl+C.
"""
import argparse
import socketserver
import http.server


class Handler(http.server.BaseHTTPRequestHandler):
    def _drain(self):
        length = int(self.headers.get("Content-Length", 0))
        remaining = length
        chunk = 1024 * 64
        while remaining > 0:
            data = self.rfile.read(min(chunk, remaining))
            if not data:
                break
            remaining -= len(data)

    def do_POST(self):
        try:
            self._drain()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(b'{"status":"ok"}')
        except (ConnectionError, OSError):
            # Client memutus koneksi sebelum selesai (mis. timeout di mode Hold).
            # Wajar dan tidak merusak data; abaikan tanpa mencetak traceback.
            pass

    def do_GET(self):
        try:
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"server up")
        except (ConnectionError, OSError):
            pass

    def handle_one_request(self):
        try:
            super().handle_one_request()
        except (ConnectionError, OSError):
            self.close_connection = True

    def log_message(self, *args):
        pass  # senyap agar konsol tidak banjir


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8080)
    ap.add_argument("--bind", default="0.0.0.0")
    args = ap.parse_args()

    class QuietServer(socketserver.ThreadingTCPServer):
        allow_reuse_address = True
        daemon_threads = True

        def handle_error(self, request, client_address):
            # Jangan cetak traceback untuk koneksi yang diputus client (normal di mode Hold).
            import sys
            exc = sys.exc_info()[1]
            if isinstance(exc, (ConnectionError, OSError)):
                return
            super().handle_error(request, client_address)

    with QuietServer((args.bind, args.port), Handler) as httpd:
        print(f"Server listening on {args.bind}:{args.port} (POST /upload)")
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\nstopped")


if __name__ == "__main__":
    main()
