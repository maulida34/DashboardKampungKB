import re

import pandas as pd

from muat_data import BUCKET, CATATAN_AMAN, TAK_TERPETAKAN

BULAN = ["Jan", "Feb", "Mar", "Apr", "Mei", "Jun", "Jul", "Agu", "Sep", "Okt", "Nov", "Des"]


def _urut_alami(teks):
    """Kunci urut 'Program 2' < 'Program 10' (angka dibaca sebagai angka)."""
    return [int(t) if i % 2 else t.lower() for i, t in enumerate(re.split(r"(\d+)", str(teks)))]


def _hitung(seri, top=None, urut="jumlah", kecuali=(), susunan=None) -> pd.DataFrame:
    """
    Mesin penghitung yang dipakai hampir semua analisis: hitung berapa kali tiap nilai muncul.
      top     : ambil N teratas (None = semua)
      urut    : 'jumlah' (terbanyak dulu) atau 'label' (A-Z / angka naik)
      kecuali : nilai yang dibuang dari hitungan
      susunan : urutan tetap yang dipaksakan (nilai yang tidak ada dihitung 0)
    """
    s = seri.dropna()
    s = s[~s.isin(kecuali)]
    h = s.value_counts()
    if susunan is not None:
        h = h.reindex(susunan, fill_value=0)
    elif urut == "label":
        h = h.reindex(sorted(h.index, key=_urut_alami))
    if top:
        h = h.head(top)
    return pd.DataFrame({"label": [str(x) for x in h.index], "jumlah": h.values})


def a01_per_bulan(df) -> pd.DataFrame:
    """Jumlah laporan per bulan kegiatan (bulan tanpa laporan tetap ditampilkan sebagai 0)."""
    t = df["Tanggal Kegiatan"].dropna()
    if t.empty:
        return pd.DataFrame({"label": [], "jumlah": []})
    per = t.dt.to_period("M").value_counts().sort_index()
    per = per.reindex(pd.period_range(per.index.min(), per.index.max(), freq="M"), fill_value=0)
    return pd.DataFrame({"label": [f"{BULAN[p.month - 1]} {p.year}" for p in per.index], "jumlah": per.values})


def a02_seksi(df):
    """Laporan menurut seksi."""
    return _hitung(df["Seksi"])


def a03_jeda_lapor(df):
    """Selisih hari antara tanggal kegiatan dan tanggal laporan (Timestamp), dikelompokkan."""
    return _hitung(df["Ketepatan Lapor"], susunan=BUCKET)


def a04_pengirim(df):
    """10 pengirim dengan laporan terbanyak."""
    return _hitung(df["Pengirim"], top=10)


def a05_kecamatan(df):
    """Laporan menurut kecamatan (kecamatan dicocokkan dari kecamatan.csv)."""
    return _hitung(df["Kecamatan"])


def a06_program(df):
    """Laporan menurut program (Program 1, 2, ... Sekretariat)."""
    return _hitung(df["Program"], urut="label")


def a07_kelurahan(df, top=None):
    """Laporan per kelurahan, terbanyak di atas. top = jumlah kelurahan yang ditampilkan (None = semua)."""
    return _hitung(df["Kelurahan"], top=top)


def a08_jenis_kegiatan(df):
    """12 jenis kegiatan terbanyak."""
    return _hitung(df["Kegiatan"], top=10)


def a09_sasaran_peserta(df):
    """10 sasaran peserta terbanyak (satu laporan bisa punya banyak peserta -> dipecah dulu)."""
    return _hitung(df["Peserta"].explode(), top=10)

"""
def a10_tahun_dibentuk(df):
    Laporan menurut tahun Kampung KB dibentuk.
    return _hitung(df["Tahun Dibentuk"], urut="label")
"""

def a11_perlu_dicek(df):
    """Jumlah laporan bermasalah: kegiatan sebelum periode, tanggal melewati tanggal lapor, kemungkinan duplikat."""
    return _hitung(df["Catatan Data"].explode(), kecuali=[CATATAN_AMAN])


def tahun_tersedia(df) -> list:
    """Tahun-tahun yang ada pada tanggal kegiatan, terbaru dulu (untuk pilihan tahun target)."""
    return sorted(df["Tanggal Kegiatan"].dropna().dt.year.unique().tolist(), reverse=True)


def a12_target_tahunan(df, kelurahan_resmi, tahun, target) -> pd.DataFrame:
    """
    Capaian tiap kelurahan terhadap target setahun: jumlah kegiatan (menurut tanggal kegiatan) dalam satu tahun.
      kelurahan_resmi : daftar [(kelurahan, kecamatan)] dari kecamatan.csv, supaya kelurahan yang belum
                        pernah melapor tetap tampil (dengan angka 0).
    Kolom hasil: Kecamatan | Kelurahan | Kegiatan | Capaian (%) | Kurang | Status. Terbanyak di atas.
    """
    kegiatan = df.dropna(subset=["Tanggal Kegiatan", "Kelurahan"])
    jumlah = kegiatan.loc[kegiatan["Tanggal Kegiatan"].dt.year == tahun, "Kelurahan"].value_counts()

    kerangka = {kel: kec for kel, kec in kelurahan_resmi}
    for kel in jumlah.index:                                   # kelurahan di data yang tidak ada di daftar resmi
        kerangka.setdefault(kel, TAK_TERPETAKAN)

    tabel = pd.DataFrame({"Kecamatan": list(kerangka.values()), "Kelurahan": list(kerangka.keys())})
    tabel["Kegiatan"] = tabel["Kelurahan"].map(jumlah).fillna(0).astype(int)
    tabel["Capaian (%)"] = (tabel["Kegiatan"] / target * 100).round().astype(int)
    tabel["Kurang"] = (target - tabel["Kegiatan"]).clip(lower=0)
    tabel["Status"] = ["Terpenuhi" if n >= target else "Belum terpenuhi" for n in tabel["Kegiatan"]]
    return tabel.sort_values(["Kegiatan", "Kelurahan"], ascending=[False, True]).reset_index(drop=True)


def kelurahan_belum_terpetakan(df) -> list:
    """Nama kelurahan yang tidak ditemukan di kecamatan.csv (untuk peringatan)."""
    return sorted(df.loc[df["Kecamatan"] == TAK_TERPETAKAN, "Kelurahan"].dropna().unique())


def baris_perlu_dicek(df) -> pd.DataFrame:
    """Daftar laporan yang ditandai bermasalah (ditampilkan di bawah analisis 11)."""
    ada_masalah = df["Catatan Data"].map(lambda c: c != [CATATAN_AMAN])
    kolom = ["Tanggal Kegiatan", "Tanggal Tertulis (perlu dicek)", "Tanggal Lapor", "Kelurahan",
             "Judul Kegiatan", "Catatan Data"]
    out = df.loc[ada_masalah, kolom].copy()
    out["Catatan Data"] = out["Catatan Data"].map(lambda c: "; ".join(c))
    return out

def ringkasan(df) -> dict:
    return {
        "total": len(df),
        "kelurahan": df["Kelurahan"].nunique(),
        "penyuluh": df["Penyuluh KB Pembina"].nunique(),
        "dokumentasi": int(df["Jumlah Dokumentasi"].sum()),
        "median_jeda": df["Jeda Lapor (hari)"].median(),
    }
