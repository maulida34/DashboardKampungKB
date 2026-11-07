import io
import itertools
import re
import sys
import urllib.error
import urllib.request
from collections import Counter, defaultdict
from pathlib import Path

import pandas as pd

K_TIMESTAMP = "Timestamp"
K_PENGIRIM = "Nama Lengkap Pengirim"
K_JABATAN = "Jabatan Pengirim"
K_PENYULUH = "Nama Penyuluh KB Pembina Kampung KB"
K_KELURAHAN = "Nama Kelurahan Kampung Keluarga Berkualitas"
K_JUDUL = "Judul Kegiatan Intervensi"
K_TGL_KEGIATAN = "Tanggal Kegiatan Intervensi"
K_LOKASI = "Tempat / Lokasi Kegiatan Intervensi dilaksanakan"
K_DESKRIPSI = "Deskripsi Singkat Kegiatan Intervensi"
K_SEKSI = "Seksi Kegiatan"
K_PESERTA = "Peserta Kegiatan"
K_MITRA = "OPD Lintas Sektoral / Mitra Kerja"
K_DOKUMENTASI = "Upload Dokumentasi Kegiatan"
WAJIB = [K_TIMESTAMP, K_KELURAHAN, K_TGL_KEGIATAN, K_SEKSI]   

BUCKET = ["0–3 hari", "4–7 hari", "8–14 hari", "15–30 hari", "> 30 hari"]
CATATAN_AMAN = "Tidak ada catatan"
CATATAN_MELEWATI = "Tanggal kegiatan melewati tanggal lapor"
CATATAN_LAMA = "Kegiatan sebelum periode laporan"
CATATAN_DUPLIKAT = "Kemungkinan duplikat"

# CSV Google Form tidak punya kolom kecamatan, jadi dicocokkan dari tabel tetap kecamatan.csv.
BERKAS_KECAMATAN = "kecamatan.csv"
TAK_TERPETAKAN = "Belum terpetakan"


def _norm(s) -> str:
    """Huruf kecil + spasi rapi, dipakai untuk mencocokkan nama kolom."""
    return re.sub(r"\s+", " ", str(s).strip().lower())


def _bersih(s) -> str:
    """Rapikan spasi berlebih / baris baru dalam teks."""
    return re.sub(r"\s+", " ", "" if s is None else str(s)).strip()


def _kunci(s: str) -> str:
    """Kunci pembanding: huruf kecil tanpa spasi/tanda baca ('Dinas Kesehatan.' == 'dinas kesehatan')."""
    return re.sub(r"[\W_]+", "", s.lower())


def _pecah(s) -> list:
    return [t for t in (_bersih(x) for x in re.split(r"[,;\n]+", "" if s is None else str(s))) if t]


def ke_tanggal(nilai):
    s = _bersih(nilai)
    if not s:
        return pd.NaT
    m = re.match(r"^(\d{1,2})/(\d{1,2})/(\d{4})(?:\s+(\d{1,2}):(\d{2})(?::(\d{2}))?)?$", s)
    if m:
        h, mi, d, mo, y, det = int(m[4] or 0), int(m[5] or 0), int(m[1]), int(m[2]), int(m[3]), int(m[6] or 0)
        try:
            return pd.Timestamp(year=y, month=mo, day=d, hour=h, minute=mi, second=det)
        except ValueError:                      # mis. 31/02/2026
            return pd.NaT
    if re.match(r"^\d{4}-\d{2}-\d{2}", s):
        return pd.to_datetime(s, errors="coerce")
    return pd.NaT


def buat_penyatu(nilai):
    per_kunci = defaultdict(Counter)
    for v in nilai:
        d = _bersih(v)
        if d:
            per_kunci[_kunci(d)][d] += 1
    terbaik = {k: c.most_common(1)[0][0] for k, c in per_kunci.items()}

    def ubah(v):
        d = _bersih(v)
        return terbaik.get(_kunci(d), d) if d else None

    return ubah


def seksi_pendek(raw):
    s = _bersih(raw)
    if re.match(r"^seksi\s*1", s, re.I): return "Seksi 1: Data Keluarga"
    if re.match(r"^seksi\s*2", s, re.I): return "Seksi 2: Perubahan Perilaku"
    if re.match(r"^seksi\s*3", s, re.I): return "Seksi 3: Layanan & Rujukan"
    if re.match(r"^seksi\s*4", s, re.I): return "Seksi 4: Lingkungan"
    if re.search(r"sekretariat|kesekretarian", s, re.I): return "Sekretariat Pokja"
    return s or None


def program_dari(kategori):
    if not kategori:
        return None
    m = re.match(r"^program\s*(\d+)", kategori, re.I)
    if m:
        return f"Program {m[1]}"
    return "Sekretariat" if re.match(r"^sekretariat", kategori, re.I) else "Lainnya"


def kegiatan_dari(kategori):
    if not kategori:
        return None
    return _bersih(re.sub(r"^(program\s*\d+|sekretariat)\s*[-–:]\s*", "", kategori, flags=re.I))


ATURAN_PERAN = [
    (r"penyuluh|pentuluh|plkb|\bpkb\b", "Penyuluh KB"),
    (r"sekret|sekertaris", "Sekretaris"),
    (r"ketua", "Ketua"),
    (r"bendahara", "Bendahara"),
    (r"kader|\bimp\b|\btpk\b", "Kader"),
    (r"ppkbd", "Sub PPKBD"),
    (r"pengurus|pegurus|pengurangan", "Pengurus"),
    (r"anggota", "Anggota"),
    (r"bkb|bkl|bkr|poktan|\bpik\b", "Kelompok BKB/BKL/BKR"),
]


def peran_dari(jabatan):
    s = _norm(jabatan)
    if not s:
        return "Tidak diisi"
    for pola, label in ATURAN_PERAN:
        if re.search(pola, s):
            return label
    return "Lainnya"


# kecamatan
def _cari_berkas(nama):
    kandidat = []
    if getattr(sys, "frozen", False):
        kandidat.append(Path(sys.executable).parent / nama)
    kandidat += [Path.cwd() / nama, Path(getattr(sys, "_MEIPASS", Path(__file__).parent)) / nama]
    return next((p for p in kandidat if p.exists()), None)


def berkas_kecamatan():
    return _cari_berkas(BERKAS_KECAMATAN)


def muat_peta_kecamatan() -> dict:
    """Baca kecamatan.csv"""
    berkas = berkas_kecamatan()
    if berkas is None:
        return {}
    for enc in ("utf-8-sig", "cp1252"):
        try:
            tabel = pd.read_csv(berkas, dtype=str, keep_default_na=False, encoding=enc)
            break
        except UnicodeDecodeError:
            continue
    else:
        return {}
    kolom = {_norm(c): c for c in tabel.columns}
    if "kelurahan" not in kolom or "kecamatan" not in kolom:
        raise ValueError("kecamatan.csv harus punya kolom 'kelurahan' dan 'kecamatan'.")
    return {_kunci(_bersih(k)): (_bersih(k), _bersih(c))
            for k, c in zip(tabel[kolom["kelurahan"]], tabel[kolom["kecamatan"]]) if _bersih(k) and _bersih(c)}


def petakan_kecamatan(kelurahan: pd.Series) -> pd.Series:
    peta = muat_peta_kecamatan()

    def cari(nama):
        if not isinstance(nama, str) or not nama:
            return None
        return peta[_kunci(nama)][1] if _kunci(nama) in peta else TAK_TERPETAKAN

    return kelurahan.map(cari)


def samakan_nama_kelurahan(kelurahan: pd.Series) -> pd.Series:
    peta = muat_peta_kecamatan()
    return kelurahan.map(lambda n: peta[_kunci(n)][0] if isinstance(n, str) and _kunci(n) in peta else n)


def daftar_kelurahan_resmi() -> list:
    return sorted(muat_peta_kecamatan().values(), key=lambda x: (x[1], x[0]))

BERKAS_SUMBER = "sumber_data.txt"


def tautan_bawaan() -> str:
    berkas = _cari_berkas(BERKAS_SUMBER)
    if berkas is None:
        return ""
    for baris in berkas.read_text(encoding="utf-8-sig").splitlines():
        baris = baris.strip()
        if baris and not baris.startswith("#"):
            return baris
    return ""


def url_ekspor_csv(tautan: str) -> str:
    """Tautan Google Sheets"""
    t = tautan.strip()
    if not t:
        raise ValueError("Tautan spreadsheet masih kosong.")
    if "docs.google.com/spreadsheets" not in t:
        raise ValueError("Tautan harus berupa link Google Sheets (https://docs.google.com/spreadsheets/d/...).")
    if "output=csv" in t or "format=csv" in t:
        return t                                                   # sudah berupa tautan CSV
    gid = re.search(r"[#&?]gid=(\d+)", t)
    sufiks = f"&gid={gid.group(1)}" if gid else ""
    if "/d/e/" in t:                                               # tautan "Publikasikan ke web"
        dasar = re.sub(r"/(pubhtml|pub)\b.*$", "", t.split("?")[0])
        return f"{dasar}/pub?output=csv{sufiks}"
    m = re.search(r"/spreadsheets/d/([A-Za-z0-9_-]+)", t)
    if not m:
        raise ValueError("ID spreadsheet tidak ditemukan di tautan. Salin tautan langsung dari bilah alamat browser.")
    return f"https://docs.google.com/spreadsheets/d/{m.group(1)}/export?format=csv{sufiks}"


def unduh_csv(url: str, batas_detik: int = 30) -> bytes:
    permintaan = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    try:
        with urllib.request.urlopen(permintaan, timeout=batas_detik) as jawaban:
            isi = jawaban.read()
    except urllib.error.HTTPError as galat:
        raise ValueError(f"Spreadsheet tidak bisa dibuka (kode {galat.code}). Pastikan dibagikan sebagai "
                         "'Siapa saja yang memiliki link' dengan akses Pelihat.") from None
    except (urllib.error.URLError, TimeoutError, OSError):
        raise ValueError("Tidak bisa terhubung ke Google. Periksa koneksi internet, atau pilih 'Unggah CSV'.") from None
    if isi.lstrip()[:15].lower().startswith((b"<!doctype html", b"<html")):
        raise ValueError("Google meminta login, artinya spreadsheet belum dibagikan. Atur akses menjadi "
                         "'Siapa saja yang memiliki link' (Pelihat), atau pilih 'Unggah CSV'.")
    return isi


# fungsi utama
def baca_csv(isi: bytes) -> pd.DataFrame:
    for enc in ("utf-8-sig", "cp1252"):
        try:
            return pd.read_csv(io.BytesIO(isi), dtype=str, keep_default_na=False, encoding=enc)
        except UnicodeDecodeError:
            continue
    raise ValueError("File tidak bisa dibaca. Pastikan formatnya CSV hasil ekspor Google Form.")


def rapikan(mentah: pd.DataFrame) -> pd.DataFrame:
    peta = {_norm(c): c for c in mentah.columns}
    kurang = [n for n in WAJIB if _norm(n) not in peta]
    if kurang:
        raise ValueError("Kolom tidak ditemukan di file: " + ", ".join(kurang))

    ada_isi = mentah.apply(lambda k: k.str.strip() != "").any(axis=1)      # buang baris kosong
    m = mentah[ada_isi].reset_index(drop=True)

    def ambil(nama):
        c = peta.get(_norm(nama))
        return m[c] if c else pd.Series("", index=m.index)

    # tanggal
    ts = pd.to_datetime(ambil(K_TIMESTAMP).map(ke_tanggal))
    tgl_asli = pd.to_datetime(ambil(K_TGL_KEGIATAN).map(ke_tanggal))
    jeda_mentah = (ts.dt.normalize() - tgl_asli.dt.normalize()).dt.days     
    melewati = jeda_mentah < 0                                             
    tgl = tgl_asli.mask(melewati)
    jeda = jeda_mentah.mask(melewati)
    ketepatan = pd.cut(jeda, bins=[-0.5, 3, 7, 14, 30, float("inf")], labels=BUCKET).astype(object)
    tertulis = tgl_asli.dt.strftime("%d/%m/%Y").where(melewati)

    # kategori kegiatan
    kol_kat = [c for c in m.columns if _norm(c).startswith("kategori kegiatan")]
    if kol_kat:
        kategori = m[kol_kat].apply(lambda r: next((b for b in map(_bersih, r) if b), None), axis=1)
    else:
        kategori = pd.Series([None] * len(m), index=m.index)

    kel_mentah = ambil(K_KELURAHAN).map(_bersih)
    tahun = kel_mentah.str.extract(r"\((\d{4})\)\s*$")[0]
    kel_nama = kel_mentah.str.replace(r"\s*\(\d{4}\)\s*$", "", regex=True)
    kelurahan = samakan_nama_kelurahan(kel_nama.map(buat_penyatu(kel_nama)))
    penyuluh = ambil(K_PENYULUH).map(buat_penyatu(ambil(K_PENYULUH)))
    pengirim = ambil(K_PENGIRIM).map(buat_penyatu(ambil(K_PENGIRIM)))

    def daftar(seri):
        pecahan = seri.map(_pecah)
        ubah = buat_penyatu(itertools.chain.from_iterable(pecahan))
        return pecahan.map(lambda lst: list(dict.fromkeys(ubah(t) for t in lst)))

    peserta, mitra = daftar(ambil(K_PESERTA)), daftar(ambil(K_MITRA))

    judul = ambil(K_JUDUL).map(_bersih)
    deskripsi = ambil(K_DESKRIPSI).map(_bersih)
    dokumentasi = ambil(K_DOKUMENTASI).str.count(r"https?://")

    tahun_awal = ts.dt.year.min()
    lama = (tgl.dt.year < tahun_awal) if pd.notna(tahun_awal) else pd.Series(False, index=m.index)
    catatan, pernah = [], set()
    for i in range(len(m)):
        c = []
        if melewati.iloc[i]:
            c.append(CATATAN_MELEWATI)
        if lama.iloc[i]:
            c.append(CATATAN_LAMA)
        if judul.iloc[i]:                       # duplikat = pengirim + judul + tanggal + deskripsi sama persis
            tg = tgl_asli.iloc[i]
            kunci = (_kunci(pengirim.iloc[i] or ""), _kunci(judul.iloc[i]),
                     tg.date() if pd.notna(tg) else None, _kunci(deskripsi.iloc[i]))
            if kunci in pernah:
                c.append(CATATAN_DUPLIKAT)
            else:
                pernah.add(kunci)
        catatan.append(c or [CATATAN_AMAN])

    return pd.DataFrame({
        "Tanggal Kegiatan": tgl,
        "Tanggal Lapor": ts.dt.normalize(),
        "Kelurahan": kelurahan,
        "Kecamatan": petakan_kecamatan(kelurahan),
        "Tahun Dibentuk": tahun,
        "Penyuluh KB Pembina": penyuluh,
        "Seksi": ambil(K_SEKSI).map(seksi_pendek),
        "Program": kategori.map(program_dari),
        "Kegiatan": kategori.map(kegiatan_dari),
        "Judul Kegiatan": judul.mask(judul == ""),
        "Lokasi": ambil(K_LOKASI).map(_bersih).pipe(lambda x: x.mask(x == "")),
        "Peserta": peserta,
        "Mitra Kerja": mitra,
        "Pengirim": pengirim,
        "Peran Pengirim": ambil(K_JABATAN).map(peran_dari),
        "Jeda Lapor (hari)": jeda,
        "Ketepatan Lapor": ketepatan,
        "Jumlah Dokumentasi": dokumentasi,
        "Catatan Data": catatan,
        "Tanggal Tertulis (perlu dicek)": tertulis,
    })
