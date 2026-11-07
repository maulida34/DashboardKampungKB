"""
launcher.py - Pintu masuk aplikasi (dijalankan saat .exe diklik).

Cara kerja:
  1. Menjalankan server Streamlit di proses terpisah (hanya bisa dibuka dari komputer ini).
  2. Menampilkan dasbor di jendela aplikasi (pywebview), bukan di browser.
  3. Saat jendela ditutup, server ikut dimatikan.

Cara menjalankan:
  python launcher.py              -> jendela aplikasi (untuk tes sebelum build)
  python launcher.py --server N   -> dipakai internal: hanya server di port N
"""
import atexit
import os
import socket
import subprocess
import sys
import time

JUDUL = "Dasbor Lapor Kampung KB"

# Aplikasi tanpa konsol
ADA_KONSOL = sys.stdout is not None
for _nama in ("stdout", "stderr"):
    if getattr(sys, _nama) is None:
        setattr(sys, _nama, open(os.devnull, "w"))

SUDAH_DIBUNDEL = getattr(sys, "frozen", False)                    # True saat berjalan sebagai .exe
BASE_DIR = sys._MEIPASS if SUDAH_DIBUNDEL else os.path.dirname(os.path.abspath(__file__))

HTML_MEMUAT = """<body style="font-family:Segoe UI,sans-serif;background:#F2F4F1;color:#1B2A33;
display:grid;place-items:center;height:100vh;margin:0"><div style="text-align:center">
<div style="font-size:22px;font-weight:600;color:#0F6E6E">Dasbor Lapor Kampung KB</div>
<div style="margin-top:8px;color:#66757F">Memuat dasbor, mohon tunggu...</div></div></body>"""

HTML_GAGAL = """<body style="font-family:Segoe UI,sans-serif;background:#F2F4F1;color:#1B2A33;padding:40px">
<h2 style="color:#B3382C">Dasbor gagal dimuat</h2><p>Tutup aplikasi lalu buka kembali.</p></body>"""


def _modul_aplikasi():
    """Tidak pernah dipanggil. Hanya agar PyInstaller ikut membundel modul yang diimpor app.py."""
    import analisis, grafik, muat_data, pandas, plotly.graph_objects  # noqa: F401,E401


# server Streamlit
def jalankan_server(port: int):
    """Menjalankan Streamlit (proses ini akan terus hidup sampai dimatikan)."""
    import streamlit.web.cli as stcli

    sys.path.insert(0, BASE_DIR)
    sys.argv = [
        "streamlit", "run", os.path.join(BASE_DIR, "app.py"),
        f"--server.port={port}",
        "--server.address=127.0.0.1",                 # hanya komputer ini
        "--server.headless=true",                     # jangan membuka browser
        "--server.fileWatcherType=none",
        "--browser.gatherUsageStats=false",
        "--global.developmentMode=false",
        # Tema dikirim langsung karena .streamlit/config.toml tidak terbaca di dalam .exe
        "--theme.base=light",
        "--theme.primaryColor=#0F6E6E",
        "--theme.backgroundColor=#F2F4F1",
        "--theme.secondaryBackgroundColor=#FFFFFF",
        "--theme.textColor=#1B2A33",
    ]
    stcli.main()


def port_bebas() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def mulai_server(port: int) -> subprocess.Popen:
    """Jalankan diri sendiri dengan argumen --server (sebagai .exe atau lewat python)."""
    perintah = [sys.executable] + ([] if SUDAH_DIBUNDEL else [os.path.abspath(__file__)]) + ["--server", str(port)]
    keluaran = None if ADA_KONSOL else subprocess.DEVNULL          # tanpa konsol, Windows butuh ini agar Popen tidak error
    return subprocess.Popen(perintah, stdin=subprocess.DEVNULL, stdout=keluaran, stderr=keluaran,
                            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))


def tunggu_server(port: int, proses: subprocess.Popen, batas_detik: int = 90) -> bool:
    """Tunggu sampai server siap menerima koneksi."""
    mulai = time.time()
    while time.time() - mulai < batas_detik and proses.poll() is None:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.5):
                return True
        except OSError:
            time.sleep(0.4)
    return False


# jendela aplikasi
def main():
    port = port_bebas()
    server = mulai_server(port)
    atexit.register(server.terminate)
    alamat = f"http://127.0.0.1:{port}"

    try:
        import webview
    except ImportError:                                
        import webbrowser
        if tunggu_server(port, server):
            webbrowser.open(alamat)
            server.wait()
        return

    try:
        webview.settings["ALLOW_DOWNLOADS"] = True     
    except Exception:
        pass

    jendela = webview.create_window(JUDUL, html=HTML_MEMUAT, width=1366, height=820, min_size=(1000, 640))

    def saat_siap():                                   
        if tunggu_server(port, server):
            jendela.load_url(alamat)
        else:
            jendela.load_html(HTML_GAGAL)

    webview.start(saat_siap)
    server.terminate()                                 


if __name__ == "__main__":
    import multiprocessing
    multiprocessing.freeze_support()
    if len(sys.argv) >= 3 and sys.argv[1] == "--server":
        jalankan_server(int(sys.argv[2]))
    else:
        main()
