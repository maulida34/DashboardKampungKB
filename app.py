import inspect
from pathlib import Path

import pandas as pd
import streamlit as st

import analisis as A
import grafik as G
import muat_data as M

import textwrap

JUDUL = "Dasboard Kampung KB"
BASE_DIR = Path(__file__).parent
CSV_DEFAULT = Path("data.csv")         

st.set_page_config(page_title=JUDUL, page_icon="", layout="wide", initial_sidebar_state="expanded")

_lama = [(mod.__file__, nama) for nama, mod, ciri in
         (("muat_data.py", M, "url_ekspor_csv"), ("analisis.py", A, "a12_target_tahunan"), ("grafik.py", G, "batang_target"))
         if not hasattr(mod, ciri)]
if _lama:
    st.error("Ada file kode yang masih versi lama, jadi aplikasi berhenti. Timpa dengan versi terbaru:")
    for _lokasi, _nama in _lama:
        st.code(f"{_nama}  <-  terbaca dari: {_lokasi}")
    st.info("Setelah menimpa, hentikan Streamlit (Ctrl+C) lalu jalankan lagi: streamlit run app.py")
    st.stop()

def muat_css(nama="style.css"):
    berkas = BASE_DIR / nama
    if berkas.exists():
        st.markdown(f"<style>{berkas.read_text(encoding='utf-8')}</style>", unsafe_allow_html=True)


def lebar_penuh(fungsi) -> dict:
    """Streamlit baru memakai width='stretch'; versi lama use_container_width=True."""
    return {"width": "stretch"} if "width" in inspect.signature(fungsi).parameters else {"use_container_width": True}

CONFIG_GRAFIK = {"displaylogo": False,
                 "modeBarButtonsToRemove": ["zoom2d", "pan2d", "select2d", "lasso2d", "zoomIn2d",
                                            "zoomOut2d", "autoScale2d", "resetScale2d"],
                 "toImageButtonOptions": {"format": "png", "scale": 2}}

def kartu(tempat, fig):
    """Taruh satu grafik di dalam kartu putih."""
    with tempat:
        with st.container(border=True):
            st.plotly_chart(fig, config=CONFIG_GRAFIK, **lebar_penuh(st.plotly_chart))

@st.dialog("Data lengkap", width="large")

def tampil_lengkap(data, judul, lebar_label=34):
    lebar = 50
    baris = max(len(textwrap.wrap(str(t), lebar)) or 1 for t in data["label"])
    tinggi = 110 + len(data) * max(30, baris * 17 + 12)
    st.markdown(f"**{judul}** · {len(data)} data")
    st.plotly_chart(G.batang_mendatar(data, "", tinggi, lebar_label=lebar),
                    config=CONFIG_GRAFIK, **lebar_penuh(st.plotly_chart))


def kartu_top(tempat, data, judul, kunci, n=3, tinggi=200):
    """n teratas di halaman. Tombol 'Lihat semua' membuka data lengkap di jendela besar."""
    with tempat:
        with st.container(border=True):
            st.plotly_chart(G.batang_mendatar(data.head(n), f"{judul} ({n} teratas)", tinggi),
                            config=CONFIG_GRAFIK, **lebar_penuh(st.plotly_chart))
            if len(data) > n and st.button(f"Lihat semua ({len(data)})", key=kunci):
                tampil_lengkap(data, judul)

def angka(n) -> str:
    """1101 -> '1.101'"""
    return f"{int(n):,}".replace(",", ".")


muat_css()

# data
st.sidebar.title("Laporan Kampung KB")
sumber = st.sidebar.radio("Sumber data", ["Link Google Sheets", "Unggah CSV"], key="f_sumber")


def perbarui_sheet():
    st.session_state["_versi_sheet"] = st.session_state.get("_versi_sheet", 0) + 1


@st.cache_data(ttl=600, show_spinner="Mengambil data dari Google Sheets...")
def ambil_sheet(url: str, versi: int) -> bytes:
    """Unduh isi spreadsheet. Disimpan 10 menit; tombol 'Perbarui data' memaksa ambil ulang (versi naik)."""
    return M.unduh_csv(url)


@st.cache_data(show_spinner="Memuat data...")
def muat(isi: bytes, versi_peta: float):
    """versi_peta = waktu ubah kecamatan.csv, supaya data dihitung ulang bila file itu diedit."""
    return M.rapikan(M.baca_csv(isi))


if sumber == "Link Google Sheets":
    tautan = st.sidebar.text_input("Tautan spreadsheet", value=M.tautan_bawaan(), key="f_tautan",
                                   placeholder="https://docs.google.com/spreadsheets/d/...")
    st.sidebar.button("Perbarui data", on_click=perbarui_sheet)
    if not tautan.strip():
        st.title(JUDUL)
        st.info("Tempel tautan Google Sheets (hasil jawaban Google Form) di sidebar, atau pilih 'Unggah CSV'.")
        st.stop()
    try:
        isi = ambil_sheet(M.url_ekspor_csv(tautan), st.session_state.get("_versi_sheet", 0))
    except ValueError as galat:
        st.title(JUDUL)
        st.error(str(galat))
        st.stop()
    nama_file = "Google Sheets"
else:
    unggah = st.sidebar.file_uploader("Unggah CSV Google Form", type="csv", key="unggah_sidebar")
    if unggah is None and not CSV_DEFAULT.exists():             # belum ada data: tombol unggah juga ditaruh di sini
        st.title(JUDUL)
        st.info("Mulai dengan mengunggah file CSV hasil ekspor Google Form.")
        unggah = st.file_uploader("Unggah CSV Google Form", type="csv", key="unggah_utama")
        if unggah is None:
            st.stop()
    if unggah is not None:
        isi, nama_file = unggah.getvalue(), unggah.name
    else:
        isi, nama_file = CSV_DEFAULT.read_bytes(), CSV_DEFAULT.name

berkas_kec = M.berkas_kecamatan()
try:
    semua = muat(isi, berkas_kec.stat().st_mtime if berkas_kec else 0.0)
except ValueError as galat:
    st.error(f"Data tidak dapat dimuat. {galat}")
    st.stop()

# filter (sidebar)
opsi_seksi = sorted(semua["Seksi"].dropna().unique())
opsi_kel = sorted(semua["Kelurahan"].dropna().unique())
opsi_tahun = ["Semua"] + A.tahun_tersedia(semua) 


def atur_ulang_filter():
    st.session_state["f_seksi"] = opsi_seksi
    st.session_state["f_kel"] = []
    st.session_state["f_periode"] = st.session_state["f_tahun"] = opsi_tahun[1] if len(opsi_tahun) > 1 else "Semua"
    st.session_state["f_cari"] = ""


tanda_berkas = (nama_file, len(isi))                    
if st.session_state.get("_tanda_berkas") != tanda_berkas:
    st.session_state["_tanda_berkas"] = tanda_berkas
    atur_ulang_filter()

st.sidebar.subheader("Filter")
st.sidebar.multiselect("Seksi", opsi_seksi, key="f_seksi")
st.sidebar.multiselect("Kelurahan", opsi_kel, key="f_kel", placeholder="Semua kelurahan")
st.sidebar.selectbox("Tahun kegiatan", opsi_tahun, key="f_tahun")
st.sidebar.button("Atur ulang filter", on_click=atur_ulang_filter)

# --- Unduh data (di sidebar)
st.sidebar.subheader("Unduh data")
bersih = semua.drop(columns=["Pengirim", "Tanggal Tertulis (perlu dicek)"]).copy()
for nama in ("Peserta", "Mitra Kerja", "Catatan Data"):          # daftar -> teks
    bersih[nama] = bersih[nama].map(lambda isi_sel: "; ".join(isi_sel))
st.sidebar.download_button("Data bersih (CSV, bisa dibuka di Excel)",
                           bersih.to_csv(index=False).encode("utf-8-sig"),
                           file_name="data_kampung_kb_bersih.csv", mime="text/csv")
st.sidebar.download_button("Data mentah (CSV)", isi,
                           file_name="data_kampung_kb_mentah.csv", mime="text/csv")

df = semua
if set(st.session_state["f_seksi"]) != set(opsi_seksi):       
    df = df[df["Seksi"].isin(st.session_state["f_seksi"])]
if st.session_state["f_kel"]:
    df = df[df["Kelurahan"].isin(st.session_state["f_kel"])]
if st.session_state["f_tahun"] != "Semua":
    df = df[df["Tanggal Kegiatan"].dt.year == st.session_state["f_tahun"]]


st.sidebar.caption("Data diproses di komputer ini dan tidak dikirim ke mana pun.")
#st.sidebar.caption("Data diproses di komputer ini dan tidak dikirim ke mana pun. Nama pengirim hanya tampil di grafik pengirim (bisa disamarkan di atas).")


# judul dan kartu angka
st.title(JUDUL)
st.caption(f"{nama_file} · {angka(len(semua))} laporan")

jumlah_kampung = len(M.daftar_kelurahan_resmi())          
if len(df) != len(semua):
    st.caption(f"Filter aktif: menampilkan {angka(len(df))} dari {angka(len(semua))} laporan.")

belum = A.kelurahan_belum_terpetakan(semua)
if belum:
    st.warning(f"{len(belum)} kelurahan belum ada di kecamatan.csv: {', '.join(belum)}. "
               "Tambahkan ke kecamatan.csv (kolom: kelurahan, kecamatan), lalu muat ulang.")

if df.empty:
    st.warning("Tidak ada laporan yang cocok dengan filter.")
    st.stop()


# --- Baris 1: kapan dan di mana
kiri, kanan = st.columns([2, 1])

kartu(
    kiri,
    G.garis_area(
        A.a01_per_bulan(df),
        "Jumlah laporan kegiatan per bulan",
        380
    )
)

kartu_top(
    kanan,
    A.a07_kelurahan(df),
    "Laporan per kelurahan",
    "lengkap_kel",
    tinggi=325
)

# --- Baris 2
k1, k2, k3 = st.columns(3)
kartu(k1, G.donat(A.a02_seksi(df), "Laporan menurut seksi", 380))
kartu(k2, G.donat(A.a05_kecamatan(df), "Laporan menurut kecamatan", 380))
kartu_top(k3, A.a08_jenis_kegiatan(df), "Jenis kegiatan terbanyak", "lengkap_jenis", tinggi=325)

# --- Baris 3
k1, k2, k3 = st.columns(3)
kartu_top(k1, A.a06_program(df), "Laporan menurut program", "lengkap_program", tinggi=300)
kartu_top(k2, A.a09_sasaran_peserta(df), "Sasaran peserta kegiatan", "lengkap_sasaran", tinggi=300)
kartu_top(k3, A.a04_pengirim(df), "Pengirim laporan terbanyak", "lengkap_pengirim", tinggi=300)
#st.download_button("Unduh tabel (CSV)", tabel.to_csv(index=False).encode("utf-8-sig"),
#                       file_name="data_kampung_kb.csv", mime="text/csv")