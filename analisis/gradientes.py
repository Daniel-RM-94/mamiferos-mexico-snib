"""Gradientes de riqueza y composicion por latitud y altitud.

Uso:
    python -m analisis.gradientes

Salidas en outputs/gradientes/:
    gradiente_latitud.csv / .png   riqueza observada y rarefactada por banda de 1°,
                                   y % de especies de los ordenes principales
    gradiente_altitud.csv / .png   lo mismo por banda de 250 m
    especies_altitud.csv           por especie: percentiles de altitud y de latitud
    altitud_ordenes.png            altitud mediana de las especies de cada orden
    alta_montana.png               rango altitudinal de las especies que viven mas alto

La riqueza observada crece con el esfuerzo; la rarefactada estima las especies
esperadas con el mismo numero de registros en todas las bandas (Hurlbert), asi
que su forma es el gradiente sin el efecto del muestreo desigual. Solo se
rarefactan bandas con al menos MIN_REGISTROS_BANDA registros.

Para altitud se excluyen registros con incertidumbre conocida mayor a
MAX_INCERTIDUMBRE_M (a 10 km de error la altitud puede variar cientos de metros).
"""
import argparse

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.ticker import MultipleLocator

from analisis import estilo
from analisis.comparativo import riqueza_rarefactada
from config import DIR_OUTPUTS, ZONAS_UTM
from pipeline.io import cargar_procesado

SALIDA = DIR_OUTPUTS / "gradientes"
BANDA_LATITUD = 1.0
BANDA_ALTITUD = 250
MIN_REGISTROS_BANDA = 300
MAX_INCERTIDUMBRE_M = 1_000
MIN_REGISTROS_ESPECIE = 20     # para percentiles de altitud por especie
MIN_ESPECIES_ORDEN = 5
ORDENES = ["Rodentia", "Chiroptera", "Carnivora"]   # composicion (slots 1-3, fijos)
COLUMNAS = ["unidad", "especie", "ordenvalido", "latitud", "altitud_m", "incertidumbre_m",
            "endemica_especie", "en_nom059", "iucn_amenazada", "nom059_cod", "iucn_cod",
            "dup_evento", "es_marino", "es_exotica"]


def preparar(unidades) -> pd.DataFrame:
    df = cargar_procesado(unidades, columnas=COLUMNAS)
    df = df[df["especie"].notna() & ~df["dup_evento"] & ~df["es_exotica"] & ~df["es_marino"]]
    return df.assign(en_riesgo=df["en_nom059"] | df["iucn_amenazada"])


def para_altitud(df: pd.DataFrame) -> pd.DataFrame:
    return df[df["altitud_m"].notna() & ~(df["incertidumbre_m"] > MAX_INCERTIDUMBRE_M)]


# ─────────────────────────────────────────
# Riqueza por bandas
# ─────────────────────────────────────────

def gradiente(df: pd.DataFrame, columna: str, ancho: float) -> pd.DataFrame:
    """Por banda: registros, especies observadas, rarefactadas y % por orden."""
    banda = (np.floor(df[columna] / ancho) * ancho).rename("banda")
    g = df.groupby(banda)
    t = pd.DataFrame({"registros": g.size(), "especies": g["especie"].nunique()})
    conteos = {b: s.value_counts().to_numpy() for b, s in g["especie"]}
    validas = t.index[t["registros"] >= MIN_REGISTROS_BANDA]
    n_ref = int(t.loc[validas, "registros"].min())
    t["n_rarefaccion"] = n_ref
    t["especies_rarefactadas"] = [round(riqueza_rarefactada(conteos[b], n_ref), 1)
                                  if b in validas else np.nan for b in t.index]

    especies = df.assign(banda=banda).drop_duplicates(["banda", "especie"])
    pct = pd.crosstab(especies["banda"], especies["ordenvalido"], normalize="index") * 100
    for orden in ORDENES:
        t[f"pct_{orden}"] = pct.get(orden, 0).round(1)
    t.loc[t["registros"] < MIN_REGISTROS_BANDA, [f"pct_{o}" for o in ORDENES]] = np.nan
    t.index = t.index.astype(float)
    return t


def fig_gradiente(t, ancho, xlabel, titulo, destino, unidad_banda, paso_marcas):
    x = t.index + ancho / 2                       # centro de la banda
    validas = t["especies_rarefactadas"].notna()
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(10, 7.5), sharex=True,
                                   gridspec_kw={"height_ratios": [1.4, 1], "hspace": 0.12})

    ax1.plot(x, t["especies"], color=estilo.OTROS, label="Observadas (dependen del esfuerzo)")
    ax1.plot(x[validas], t.loc[validas, "especies_rarefactadas"], color=estilo.TINTA,
             marker="o", markersize=5, markeredgecolor=estilo.SUPERFICIE, markeredgewidth=1.5,
             label=f"Rarefactadas a {int(t['n_rarefaccion'].iat[0]):,} registros")
    ax1.set_ylabel("Especies")
    ax1.set_ylim(0)
    ax1.set_title(titulo, pad=30)
    ax1.legend(loc="lower left", bbox_to_anchor=(0, 1.0), ncols=2, borderaxespad=0.3)

    for orden, color in zip(ORDENES, estilo.CATEGORICA):
        ax2.plot(x, t[f"pct_{orden}"], color=color, label=orden)
        ultimo = t[f"pct_{orden}"].last_valid_index()
        ax2.annotate(orden, (ultimo + ancho / 2, t.at[ultimo, f"pct_{orden}"]),
                     xytext=(6, 0), textcoords="offset points", va="center",
                     fontsize=9, color=estilo.TINTA_2)
    ax2.set_ylabel("% de las especies de la banda")
    ax2.set_ylim(0)
    ax2.set_xlabel(xlabel)
    ax2.legend(loc="upper left", ncols=3, fontsize=8.5)
    ax2.set_xlim(t.index.min(), t.index.max() + ancho * 1.9)
    ax2.xaxis.set_major_locator(MultipleLocator(paso_marcas))
    ax2.xaxis.set_major_formatter(lambda v, _: f"{v:,.0f}{unidad_banda}")
    fig.savefig(destino)
    plt.close(fig)


# ─────────────────────────────────────────
# Altitud por especie
# ─────────────────────────────────────────

def especies_altitud(df_alt: pd.DataFrame, df: pd.DataFrame) -> pd.DataFrame:
    g = df_alt.groupby("especie")["altitud_m"]
    t = pd.DataFrame({
        "registros_con_altitud": g.size(),
        "altitud_p05": g.quantile(0.05).round(0),
        "altitud_mediana": g.median().round(0),
        "altitud_p95": g.quantile(0.95).round(0),
    })
    t["rango_altitudinal"] = t["altitud_p95"] - t["altitud_p05"]
    gl = df.groupby("especie")
    t = t.join(pd.DataFrame({
        "orden": gl["ordenvalido"].first(),
        "latitud_p05": gl["latitud"].quantile(0.05).round(2),
        "latitud_mediana": gl["latitud"].median().round(2),
        "latitud_p95": gl["latitud"].quantile(0.95).round(2),
        "endemica": gl["endemica_especie"].first(),
        "en_riesgo": gl["en_riesgo"].any(),
        "nom059_max": gl["nom059_cod"].max(),
        "iucn_max": gl["iucn_cod"].max(),
    }))
    return (t[t["registros_con_altitud"] >= MIN_REGISTROS_ESPECIE]
            .sort_values("altitud_mediana", ascending=False))


def fig_ordenes(esp, destino):
    conteo = esp["orden"].value_counts()
    ordenes = conteo[conteo >= MIN_ESPECIES_ORDEN].index
    ordenes = esp[esp["orden"].isin(ordenes)].groupby("orden")["altitud_mediana"] \
        .median().sort_values().index
    rng = np.random.default_rng(0)
    fig, ax = plt.subplots(figsize=(9, 0.55 * len(ordenes) + 1.8))
    for i, orden in enumerate(ordenes):
        valores = esp.loc[esp["orden"] == orden, "altitud_mediana"]
        ax.boxplot(valores, positions=[i], vert=False, widths=0.55, showfliers=False,
                   medianprops={"color": estilo.TINTA, "linewidth": 2},
                   boxprops={"color": estilo.TINTA_2}, whiskerprops={"color": estilo.TINTA_2},
                   capprops={"color": estilo.TINTA_2})
        ax.scatter(valores, i + rng.uniform(-0.18, 0.18, len(valores)), s=14,
                   color=estilo.AZUL, alpha=0.55, linewidths=0, zorder=3)
    ax.set_yticks(range(len(ordenes)),
                  [f"{o} ({conteo[o]})" for o in ordenes])
    ax.xaxis.set_major_formatter(lambda v, _: f"{v:,.0f} m")
    ax.set_xlabel("Altitud mediana de la especie")
    ax.grid(axis="y", visible=False)
    ax.set_title(f"Altitud mediana de las especies por orden (entre paréntesis, especies con "
                 f"≥ {MIN_REGISTROS_ESPECIE} registros)", fontsize=11)
    fig.savefig(destino)
    plt.close(fig)


def fig_alta_montana(esp, destino, top=30):
    datos = esp.head(top).iloc[::-1]
    y = np.arange(len(datos))
    fig, ax = plt.subplots(figsize=(9.5, 0.3 * len(datos) + 1.9))
    ax.hlines(y, datos["altitud_p05"], datos["altitud_p95"], color=estilo.OTROS, linewidth=4)
    ax.scatter(datos["altitud_mediana"], y, s=50, color=estilo.AZUL,
               edgecolors=estilo.SUPERFICIE, linewidths=2, zorder=3)
    etiquetas = []
    for e, fila in datos.iterrows():
        codigos = "/".join(str(v) for v in (fila["nom059_max"], fila["iucn_max"]) if pd.notna(v))
        etiquetas.append(f"{estilo.cursiva(e)}{' *' if fila['endemica'] else ''}"
                         + (f"  ({codigos})" if codigos else ""))
    ax.set_yticks(y, etiquetas, fontsize=8.5)
    ax.xaxis.set_major_formatter(lambda v, _: f"{v:,.0f} m")
    ax.set_xlabel("Altitud (barra: percentiles 5–95; punto: mediana)")
    ax.grid(axis="y", visible=False)
    ax.set_title(f"Las {top} especies con mayor altitud mediana\n"
                 "(* endémica; NOM-059/IUCN)")
    fig.savefig(destino)
    plt.close(fig)


# ─────────────────────────────────────────
# Ejecucion
# ─────────────────────────────────────────

def main(unidades):
    SALIDA.mkdir(parents=True, exist_ok=True)
    estilo.aplicar()
    csv = {"encoding": "utf-8-sig"}
    df = preparar(unidades)
    df_alt = para_altitud(df)
    print(f"{len(df):,} registros | {len(df_alt):,} con altitud confiable")

    lat = gradiente(df, "latitud", BANDA_LATITUD)
    lat.to_csv(SALIDA / "gradiente_latitud.csv", index_label="banda_latitud", **csv)
    fig_gradiente(lat, BANDA_LATITUD, "Latitud (punto: centro de la banda de 1°)",
                  "Riqueza de especies por latitud", SALIDA / "gradiente_latitud.png", "°", 2)

    alt = gradiente(df_alt, "altitud_m", BANDA_ALTITUD)
    alt = alt[alt.index >= 0]
    alt.to_csv(SALIDA / "gradiente_altitud.csv", index_label="banda_altitud_m", **csv)
    fig_gradiente(alt, BANDA_ALTITUD, f"Altitud (punto: centro de la banda de {BANDA_ALTITUD} m)",
                  "Riqueza de especies por altitud", SALIDA / "gradiente_altitud.png", " m", 500)

    esp = especies_altitud(df_alt, df)
    esp.to_csv(SALIDA / "especies_altitud.csv", **csv)
    fig_ordenes(esp, SALIDA / "altitud_ordenes.png")
    fig_alta_montana(esp, SALIDA / "alta_montana.png")

    cols = ["registros", "especies", "especies_rarefactadas"] + [f"pct_{o}" for o in ORDENES]
    print(f"\nLatitud (rarefaccion a {int(lat['n_rarefaccion'].iat[0]):,} registros):")
    print(lat[cols].to_string())
    print(f"\nAltitud (rarefaccion a {int(alt['n_rarefaccion'].iat[0]):,} registros):")
    print(alt[cols].to_string())
    print("\nEspecies de mayor altitud:")
    print(esp.head(8)[["altitud_p05", "altitud_mediana", "altitud_p95", "endemica",
                       "en_riesgo"]].to_string())
    print(f"\nSalidas en {SALIDA}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--unidades", nargs="+", default=list(ZONAS_UTM))
    main(parser.parse_args().unidades)
