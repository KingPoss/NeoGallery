import socket
import threading
import time

import webview

from app import paths
from app.web import create_app


def _free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def _run_server(app, port: int) -> None:
    # flask dev server is fine here, we only ever serve 127.0.0.1
    app.run(host="127.0.0.1", port=port, debug=False, use_reloader=False, threaded=True)


def main() -> None:
    paths.ensure_dirs()
    app = create_app()
    port = _free_port()
    t = threading.Thread(target=_run_server, args=(app, port), daemon=True)
    t.start()

    # tiny wait so the server is listening before pywebview hits it
    for _ in range(50):
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.2):
                break
        except OSError:
            time.sleep(0.05)

    webview.create_window("NeoGallery", f"http://127.0.0.1:{port}", width=1280, height=860, min_size=(900, 600))
    webview.start()


if __name__ == "__main__":
    main()
