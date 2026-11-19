import textwrap

import plotly.graph_objects as go

TEAL = "#0F6E6E"
PALET = ["#0F6E6E", "#D9822B", "#3F8FB5", "#B3382C", "#7A6BB0", "#5BA58C", "#C2679B", "#66757F"]
INK, MUTED, GARIS = "#1B2A33", "#66757F", "#E5E9EB"
FONT = "Segoe UI, system-ui, sans-serif"


def _tata(fig, judul, tinggi, legenda=False):
    """Gaya bersama semua grafik: latar putih, judul di kiri atas."""
    fig.update_layout(
        template="simple_white", height=tinggi, showlegend=legenda,
        title=dict(text=judul, x=0, xanchor="left", font=dict(size=15)),
        margin=dict(l=10, r=20, t=50, b=10),
        font=dict(family=FONT, color=INK, size=12),
    )
    return fig


def _kosong(judul, tinggi):
    fig = go.Figure()
    fig.add_annotation(text="Tidak ada data", showarrow=False, font=dict(color=MUTED, size=14))
    fig.update_xaxes(visible=False)
    fig.update_yaxes(visible=False)
    return _tata(fig, judul, tinggi)


def garis_area(data, judul, tinggi=320):
    """Untuk deret waktu (analisis 1)."""
    if data.empty:
        return _kosong(judul, tinggi)
    fig = go.Figure(go.Scatter(
        x=data["label"], y=data["jumlah"], mode="lines+markers",
        line=dict(color=TEAL, width=3), marker=dict(size=7),
        fill="tozeroy", fillcolor="rgba(15,110,110,0.12)",
        hovertemplate="%{x}: %{y} laporan<extra></extra>"))
    fig.update_xaxes(type="category")
    fig.update_yaxes(rangemode="tozero", gridcolor=GARIS)
    return _tata(fig, judul, tinggi)


def batang(data, judul, tinggi=320):
    """Batang tegak (analisis 3, 8, 11)."""
    if data.empty:
        return _kosong(judul, tinggi)
    fig = go.Figure(go.Bar(
        x=data["label"], y=data["jumlah"], marker_color=TEAL,
        text=data["jumlah"], textposition="outside", cliponaxis=False,
        hovertemplate="%{x}: %{y} laporan<extra></extra>"))
    fig.update_xaxes(type="category")
    fig.update_yaxes(range=[0, max(data["jumlah"].max(), 1) * 1.15], gridcolor=GARIS)
    return _tata(fig, judul, tinggi)



def batang_mendatar(data, judul, tinggi=420, lebar_label=34):
    """Batang mendatar untuk nama panjang. Tinggi otomatis mengikuti jumlah kategori."""
    if data.empty:
        return _kosong(judul, tinggi)

    # Membungkus nama kategori yang panjang
    etiket = ["<br>".join(textwrap.wrap(str(t), lebar_label)) or str(t) for t in data["label"]]

    # Menghitung jumlah baris label agar tidak bertumpuk
    total_baris = sum(
        max(1, label.count("<br>") + 1)
        for label in etiket
    )

    # Tinggi grafik otomatis berdasarkan jumlah dan panjang label
    tinggi_otomatis = max(
        tinggi,
        28 * len(data) + 14 * (total_baris - len(data)) + 110
    )

    fig = go.Figure(go.Bar(
        x=data["jumlah"],
        y=etiket,
        orientation="h",
        marker_color=TEAL,
        customdata=data["label"],
        text=data["jumlah"],
        textposition="outside",
        cliponaxis=False,
        hovertemplate="%{customdata}: %{x} laporan<extra></extra>"
    ))

    fig.update_yaxes(
        autorange="reversed",
        automargin=True,
        tickfont=dict(size=11)
    )

    fig.update_xaxes(
        range=[0, max(data["jumlah"].max(), 1) * 1.15],
        gridcolor=GARIS
    )

    return _tata(fig, judul, tinggi_otomatis)



def donat(data, judul, tinggi=380):
    """Komposisi (kecamatan dan seksi). Lingkaran kecil di atas, legenda di bawahnya."""
    if data.empty:
        return _kosong(judul, tinggi)
    fig = go.Figure(go.Pie(
        labels=data["label"], values=data["jumlah"], hole=0.55, sort=False,
        domain=dict(x=[0.2, 0.8], y=[0.42, 0.92]),            # kotak lingkaran: kecil, di bagian atas
        marker=dict(colors=PALET, line=dict(color="white", width=2)),
        textinfo="percent", insidetextorientation="horizontal",
        hovertemplate="%{label}: %{value} laporan (%{percent})<extra></extra>"))
    fig = _tata(fig, judul, tinggi, legenda=True)
    fig.update_layout(legend=dict(orientation="v", x=0.5, xanchor="center", y=0.0, yanchor="bottom",
                                  bgcolor="rgba(0,0,0,0)", borderwidth=0))   # legenda transparan, tanpa bingkai
    return fig

def batang_target(tabel, target, judul):
    if tabel.empty:
        return _kosong(judul, 300)
    etiket = [f"{k} ({c.replace('Banjarmasin ', '')})" for c, k in zip(tabel["Kecamatan"], tabel["Kelurahan"])]
    fig = go.Figure()
    for status, warna in (("Terpenuhi", TEAL), ("Belum terpenuhi", PALET[1])):
        ada = (tabel["Status"] == status).to_numpy()
        fig.add_trace(go.Bar(
            x=tabel.loc[ada, "Kegiatan"], y=[e for e, b in zip(etiket, ada) if b], orientation="h", name=status,
            marker_color=warna, text=tabel.loc[ada, "Kegiatan"], textposition="outside", cliponaxis=False,
            hovertemplate="%{y}: %{x} kegiatan<extra></extra>"))
    fig.add_vline(x=target, line_dash="dash", line_color=INK, annotation_text=f"Target {target}", annotation_position="top")
    fig.update_yaxes(categoryorder="array", categoryarray=etiket, autorange="reversed", automargin=True, tickfont=dict(size=11))
    fig.update_xaxes(range=[0, max(tabel["Kegiatan"].max(), target) * 1.15], gridcolor=GARIS)
    fig = _tata(fig, judul, 26 * len(etiket) + 110, legenda=True)
    fig.update_layout(barmode="overlay", legend=dict(orientation="h", x=1, xanchor="right", y=1.02, yanchor="bottom"))
    return fig

