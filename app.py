import inspect
from pathlib import Path

import pandas as pd
import streamlit as st

import analisis as A
import grafik as G
import muat_data as M

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


CONFIG_GRAFIK = {"displaylogo": False, "toImageButtonOptions": {"format": "png", "scale": 2}}   # ikon kamera = unduh PNG


def kartu(tempat, fig):
    """Taruh satu grafik di dalam kartu putih."""
    with tempat:
        with st.container(border=True):
            st.plotly_chart(fig, config=CONFIG_GRAFIK, **lebar_penuh(st.plotly_chart))


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

ring = A.ringkasan(df)
jumlah_kampung = len(M.daftar_kelurahan_resmi())          
with st.container(border=True):
    st.markdown('<div class="kpi-strip-marker"></div>', unsafe_allow_html=True)
    k = st.columns(4)
    k[0].metric("Total laporan", angka(ring["total"]))
    k[1].metric("Jumlah Kampung KB", jumlah_kampung)
    k[2].metric("Kelurahan yang melapor", ring["kelurahan"])
    k[3].metric("Separuh laporan masuk dalam", "–" if pd.isna(ring["median_jeda"]) else f"{ring['median_jeda']:.0f} hari")
if len(df) != len(semua):
    st.caption(f"Filter aktif: menampilkan {angka(len(df))} dari {angka(len(semua))} laporan.")

belum = A.kelurahan_belum_terpetakan(semua)
if belum:
    st.warning(f"{len(belum)} kelurahan belum ada di kecamatan.csv: {', '.join(belum)}. "
               "Tambahkan ke kecamatan.csv (kolom: kelurahan, kecamatan), lalu muat ulang.")

if df.empty:
    st.warning("Tidak ada laporan yang cocok dengan filter.")
    st.stop()

# sebelas analisis 
st.subheader("Visualisasi")

st.markdown("##### Gambaran umum")
kartu(st.container(), G.garis_area(A.a01_per_bulan(df), "Jumlah laporan kegiatan per bulan"))
st.caption("Bulan terakhir bisa tampak rendah karena laporan sering terlambat masuk.")

kolom = st.columns(2)
kartu(kolom[0], G.batang_mendatar(A.a05_kecamatan(df), "Laporan menurut kecamatan", 420))
kartu(kolom[1], G.donat(A.a02_seksi(df), "Laporan menurut seksi", 420))

st.markdown("##### Wilayah dan kegiatan")
kiri, kanan = st.columns(2)
data_kel = A.a07_kelurahan(df)
tinggi_kiri = max(940, 26 * len(data_kel) + 80)          # makin banyak kelurahan, makin tinggi
kartu(kiri, G.batang_mendatar(data_kel, "Laporan per kelurahan", tinggi_kiri))
kartu(kanan, G.batang_mendatar(A.a08_jenis_kegiatan(df), "Jenis kegiatan terbanyak (10 teratas)", 500))
kartu(kanan, G.batang_mendatar(A.a09_sasaran_peserta(df), "Sasaran peserta kegiatan (10 teratas)", tinggi_kiri - 40 - 500))

st.markdown("##### Siapa dan program")
kolom = st.columns(2)
kartu(kolom[0], G.batang_mendatar(A.a04_pengirim(df), "Pengirim laporan terbanyak (10 teratas)", 440))
kartu(kolom[1], G.batang_mendatar(A.a06_program(df), "Laporan menurut program", 440))

st.markdown("##### Kualitas pelaporan")
kartu(st.container(), G.batang(A.a03_jeda_lapor(df), "Jeda antara kegiatan dan laporan", 380))
cek = A.baris_perlu_dicek(df)
with st.container(border=True):
    st.markdown("**Laporan yang perlu dicek**")
    st.caption(f"{angka(len(cek))} laporan. Penandaan ini otomatis dan perlu diperiksa manual.")
    st.dataframe(cek, hide_index=True, **lebar_penuh(st.dataframe))

with st.expander("Tabel data"):

    tabel = df.drop(columns=["Pengirim", "Tanggal Tertulis (perlu dicek)"]).copy()
    for nama in ("Peserta", "Mitra Kerja", "Catatan Data"):         # daftar -> teks agar bisa ditampilkan
        tabel[nama] = tabel[nama].map(lambda isi_sel: "; ".join(isi_sel))
    cari = st.text_input("Cari di semua kolom", key="f_cari", placeholder="Ketik kata kunci")
    if cari:
        cocok = tabel.astype(str).apply(lambda kol: kol.str.contains(cari, case=False, regex=False)).any(axis=1)
        tabel = tabel[cocok]
    st.caption(f"{angka(len(tabel))} baris")
    st.dataframe(tabel, hide_index=True, **lebar_penuh(st.dataframe))
    st.download_button("Unduh tabel (CSV)", tabel.to_csv(index=False).encode("utf-8-sig"),
                       file_name="data_kampung_kb.csv", mime="text/csv")
