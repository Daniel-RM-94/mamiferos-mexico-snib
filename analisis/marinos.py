"""Mamiferos marinos: diversidad por cuenca, calendario de ballenas y especies en riesgo.

Uso:
    python -m analisis.marinos
    python -m analisis.marinos --ballenas "Megaptera novaeangliae" "Orcinus orca"

Registros de Mexico de cetaceos, sirenios, pinnipedos y nutria marina
(es_marino), a nivel especie y sin duplicados de evento.

Salidas en outputs/marinos/:
    cuencas.csv / .png             M1: registros, riqueza rarefactada y Chao1 por cuenca
    beta_cuencas.csv               M1: Jaccard, recambio y anidamiento entre cuencas
    exclusivas_cuencas.csv         M1: especies registradas en una sola cuenca
    estacionalidad_ballenas.csv / .png
                                   M2: indice mensual corregido por esfuerzo, por cuenca
    fenologia_ballenas.csv / .png  M2: fecha central de la temporada por decada (IC 95 %)
    riesgo_marinos.csv             M3: especies en NOM-059 o amenazadas en la IUCN
    vaquita.csv / .png             M3: registros, EOO y ANP de Phocoena sinus por decada

Cuencas (M1). En el mar las zonas UTM no son una unidad natural, asi que cada
registro se asigna a una cuenca con reglas geograficas aproximadas:
    - Golfo de Mexico y Caribe: al este de 98° O y al norte de 17.3° N (el istmo
      de Tehuantepec separa las dos costas); Caribe al este de 88.5° O y al sur
      de 21.35° N (Quintana Roo, al sur de Cabo Catoche).
    - Golfo de California: al este del eje de la peninsula de Baja California y
      al norte de la linea Cabo San Lucas - Punta Piaxtla (limite sur de la OHI).
    - Pacifico: el resto.
La regla coincide con el estado de todos los registros de Sonora, Oaxaca,
Guerrero, Jalisco, Colima, Veracruz, Tamaulipas, Campeche, Yucatan y Quintana Roo.

Estacionalidad (M2): el mismo indice que temporal.py, con todos los cetaceos
de la cuenca como medida del esfuerzo de cada mes. La fecha central es la media
circular de los meses ponderada por la tasa de deteccion (registros de la
especie / registros de cetaceos en el mes), con IC 95 % por bootstrap.

EOO (M3): poligono convexo minimo en la proyeccion de eoo_aoo.py. En especies
marinas el poligono incluye tierra firme; se usa solo para comparar periodos
de una misma especie.
"""
import argparse

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from pyproj import Transformer
from scipy.spatial import ConvexHull

from analisis import estilo
from analisis.comparativo import (
    beta_pares,
    chao1,
    cobertura,
    curvas_rarefaccion,
    riqueza_rarefactada,
)
from analisis.eoo_aoo import PROYECCION, eoo_km2
from analisis.temporal import MESES, suma_movil_circular
from config import ANIO_RECIENTE, DIR_OUTPUTS
from pipeline.io import cargar_procesado
from pipeline.limpieza import CATEGORIAS_IUCN, CATEGORIAS_NOM, valor_nivel_especie

SALIDA = DIR_OUTPUTS / "marinos"
CUENCAS = ["Pacífico", "Golfo de California", "Golfo de México", "Caribe"]
COLORES_CUENCA = dict(zip(CUENCAS, [estilo.CATEGORICA[0], estilo.CATEGORICA[1],
                                    estilo.CATEGORICA[2], estilo.CATEGORICA[6]]))
# Eje de la peninsula de Baja California (lat, lon), de norte a sur
EJE_BAJA = [(32.7, -116.2), (31.0, -115.4), (30.0, -115.0), (29.0, -114.1), (28.0, -113.5),
            (27.0, -112.8), (26.0, -112.0), (25.0, -111.5), (24.0, -110.8), (23.0, -109.8),
            (22.8, -109.9)]
CABO_SAN_LUCAS = (22.88, -109.91)
PUNTA_PIAXTLA = (23.65, -106.83)

BALLENAS = ["Megaptera novaeangliae", "Eschrichtius robustus",
            "Balaenoptera musculus", "Balaenoptera physalus"]
FENOLOGIA = ["Megaptera novaeangliae", "Eschrichtius robustus"]
DECADAS_FENOLOGIA = [1990, 2000, 2010, 2020]
MIN_REGISTROS_CUENCA = 50       # para graficar la estacionalidad de una especie en una cuenca
MIN_REGISTROS_DECADA = 80       # para estimar la fecha central de una decada
N_BOOTSTRAP = 2000
VAQUITA = "Phocoena sinus"
IUCN_AMENAZADA = ["VU", "EN", "CR", "EW", "EX"]
COLUMNAS = ["paismapa", "especie", "subespecie", "ordenvalido", "familiavalida", "nombrecomun",
            "es_marino", "dup_evento", "anio", "mes", "latitud", "longitud", "tipo_registro",
            "dentro_anp", "anp_nombre", "nom059_cod", "iucn_cod", "endemica_especie"]

_A_METROS = Transformer.from_crs("EPSG:4326", PROYECCION, always_xy=True)


# ─────────────────────────────────────────
# Datos
# ─────────────────────────────────────────

def asignar_cuenca(lon, lat) -> np.ndarray:
    """Cuenca oceanica de cada punto (ver docstring del modulo)."""
    lon, lat = np.asarray(lon, dtype=float), np.asarray(lat, dtype=float)
    lats, lons = zip(*EJE_BAJA[::-1])
    lon_eje = np.interp(lat, lats, lons)
    t = np.clip((lon - CABO_SAN_LUCAS[1]) / (PUNTA_PIAXTLA[1] - CABO_SAN_LUCAS[1]), 0, 1)
    lat_boca = CABO_SAN_LUCAS[0] + t * (PUNTA_PIAXTLA[0] - CABO_SAN_LUCAS[0])
    atlantico = (lon > -98.0) & (lat > 17.3)
    caribe = atlantico & (lon > -88.5) & (lat < 21.35)
    golfo_california = ~atlantico & (lon > lon_eje) & (lat > lat_boca)
    return np.select([caribe, atlantico, golfo_california],
                     ["Caribe", "Golfo de México", "Golfo de California"], "Pacífico")


def preparar() -> pd.DataFrame:
    df = cargar_procesado(columnas=COLUMNAS)
    df = df[(df["paismapa"] == "MEXICO") & df["es_marino"] & df["especie"].notna()
            & ~df["dup_evento"]].copy()
    df["especie"] = df["especie"].astype(str)
    df["cuenca"] = pd.Categorical(asignar_cuenca(df["longitud"], df["latitud"]),
                                  categories=CUENCAS)
    return df


# ─────────────────────────────────────────
# M1. Diversidad por cuenca
# ─────────────────────────────────────────

def tabla_cuencas(df: pd.DataFrame) -> pd.DataFrame:
    conteos = {c: g["especie"].value_counts().to_numpy()
               for c, g in df.groupby("cuenca", observed=True)}
    n_ref = int(min(c.sum() for c in conteos.values()))
    en_riesgo = set(riesgo_especies(df).index)
    filas = {}
    for c, n in conteos.items():
        sub = df[df["cuenca"] == c]
        filas[c] = {
            "registros": int(n.sum()),
            "especies": int((n > 0).sum()),
            "n_rarefaccion": n_ref,
            "especies_rarefactadas": round(riqueza_rarefactada(n, n_ref), 1),
            "chao1": round(chao1(n), 1),
            "completitud_pct": round((n > 0).sum() / chao1(n) * 100, 1),
            "cobertura_pct": round(cobertura(n) * 100, 2),
            "especies_en_riesgo": sub.loc[sub["especie"].isin(en_riesgo), "especie"].nunique(),
            "pct_dentro_anp": round(sub["dentro_anp"].mean() * 100, 1),
        }
    return pd.DataFrame.from_dict(filas, orient="index").reindex(
        [c for c in CUENCAS if c in conteos])


def presencia_cuencas(df: pd.DataFrame) -> pd.DataFrame:
    return (pd.crosstab(df["cuenca"], df["especie"]) > 0).reindex(
        [c for c in CUENCAS if c in set(df["cuenca"])])


def exclusivas(df: pd.DataFrame, pa: pd.DataFrame) -> pd.DataFrame:
    solo_una = pa.columns[pa.sum() == 1]
    sub = df[df["especie"].isin(solo_una)]
    return (sub.groupby(["cuenca", "especie"], observed=True)
            .agg(orden=("ordenvalido", "first"), familia=("familiavalida", "first"),
                 registros=("especie", "size"))
            .reset_index().sort_values(["cuenca", "registros"], ascending=[True, False]))


def fig_cuencas(df, curvas, tabla, destino):
    fig, (ax_mapa, ax_rar) = plt.subplots(1, 2, figsize=(13, 5.8),
                                          gridspec_kw={"width_ratios": [1.25, 1]})
    for c in CUENCAS:
        sub = df[df["cuenca"] == c]
        ax_mapa.scatter(sub["longitud"], sub["latitud"], s=3, alpha=0.5, linewidths=0,
                        color=COLORES_CUENCA[c], label=f"{c} ({len(sub):,})", rasterized=True)
    lat_eje, lon_eje = zip(*EJE_BAJA)
    ax_mapa.plot(lon_eje, lat_eje, color=estilo.TINTA_TENUE, linewidth=1, linestyle="--")
    ax_mapa.plot([CABO_SAN_LUCAS[1], PUNTA_PIAXTLA[1]], [CABO_SAN_LUCAS[0], PUNTA_PIAXTLA[0]],
                 color=estilo.TINTA_TENUE, linewidth=1, linestyle="--")
    ax_mapa.set_aspect("equal")
    ax_mapa.set_xlabel("Longitud")
    ax_mapa.set_ylabel("Latitud")
    ax_mapa.legend(loc="lower left", markerscale=4, fontsize=8.5)
    ax_mapa.set_title("Registros por cuenca (líneas: eje de Baja California y boca del Golfo)",
                      fontsize=10.5)

    for c in tabla.index:
        cu = curvas[curvas["unidad"] == c]
        ax_rar.plot(cu["registros"], cu["especies_esperadas"], color=COLORES_CUENCA[c], label=c)
        ax_rar.plot(cu["registros"].iloc[-1], cu["especies_esperadas"].iloc[-1], "o",
                    color=COLORES_CUENCA[c], markersize=7, markeredgecolor=estilo.SUPERFICIE,
                    markeredgewidth=2, zorder=3)
    n_ref = int(tabla["n_rarefaccion"].iloc[0])
    ax_rar.axvline(n_ref, color=estilo.TINTA_TENUE, linewidth=1)
    ax_rar.annotate(f"n = {n_ref:,}", xy=(n_ref, 0.02), xycoords=("data", "axes fraction"),
                    xytext=(5, 0), textcoords="offset points", color=estilo.TINTA_2, fontsize=9)
    ax_rar.set_xscale("log")
    ax_rar.xaxis.set_major_formatter(lambda x, _: f"{x:,.0f}")
    ax_rar.set_xlabel("Registros (escala logarítmica)")
    ax_rar.set_ylabel("Especies esperadas")
    ax_rar.set_ylim(0)
    ax_rar.legend(loc="upper left", fontsize=8.5)
    ax_rar.set_title("Curvas de rarefacción por cuenca", fontsize=10.5)
    fig.suptitle("Mamíferos marinos de México por cuenca oceánica", x=0.01, ha="left",
                 fontsize=12, fontweight="semibold")
    fig.tight_layout()
    fig.savefig(destino)
    plt.close(fig)


# ─────────────────────────────────────────
# M2. Calendario de las ballenas
# ─────────────────────────────────────────

def _por_mes(meses: pd.Series) -> pd.Series:
    return meses.astype(int).value_counts().reindex(range(1, 13), fill_value=0)


def estacionalidad_ballenas(df: pd.DataFrame, especies) -> pd.DataFrame:
    cetaceos = df[(df["ordenvalido"] == "Cetacea") & df["mes"].notna()]
    filas = []
    for cuenca, sub in cetaceos.groupby("cuenca", observed=True):
        esfuerzo = _por_mes(sub["mes"])
        for esp in especies:
            n_mes = _por_mes(sub.loc[sub["especie"] == esp, "mes"])
            n = int(n_mes.sum())
            if n == 0:
                continue
            indice = (suma_movil_circular(n_mes) / suma_movil_circular(esfuerzo)
                      / (n / esfuerzo.sum()))
            for m in range(1, 13):
                filas.append({"especie": esp, "cuenca": cuenca, "mes": m,
                              "registros": int(n_mes[m]), "registros_cuenca": n,
                              "indice": round(float(indice[m]), 3)})
    return pd.DataFrame(filas)


def fecha_central(n_especie, n_esfuerzo) -> float:
    """Media circular de los meses ponderada por la tasa de deteccion.
    Devuelve el mes en escala continua: 1.0 = 1 de enero, 12.99 = fin de diciembre."""
    n_especie, n_esfuerzo = np.asarray(n_especie, float), np.asarray(n_esfuerzo, float)
    tasa = np.divide(n_especie, n_esfuerzo, out=np.zeros(12), where=n_esfuerzo > 0)
    angulo = 2 * np.pi * (np.arange(12) + 0.5) / 12          # centro de cada mes
    media = np.arctan2((tasa * np.sin(angulo)).sum(), (tasa * np.cos(angulo)).sum())
    return float((media % (2 * np.pi)) / (2 * np.pi) * 12 + 1)


def fenologia(df: pd.DataFrame, especies, semilla=0) -> pd.DataFrame:
    """Fecha central de la temporada por cuenca y decada, con IC 95 % por bootstrap.
    El esfuerzo de cada mes son los cetaceos registrados en la misma cuenca y decada."""
    rng = np.random.default_rng(semilla)
    cetaceos = df[(df["ordenvalido"] == "Cetacea") & df["mes"].notna()]
    decada = (cetaceos["anio"] // 10 * 10).astype("Int64")
    filas = []
    for esp in especies:
        for cuenca in ["Pacífico", "Golfo de California"]:
            for d in DECADAS_FENOLOGIA:
                sub = cetaceos[(decada == d) & (cetaceos["cuenca"] == cuenca)]
                n_esf = _por_mes(sub["mes"]).to_numpy()
                n_esp = _por_mes(sub.loc[sub["especie"] == esp, "mes"]).to_numpy()
                if n_esp.sum() < MIN_REGISTROS_DECADA:
                    continue
                boot = [fecha_central(rng.multinomial(n_esp.sum(), n_esp / n_esp.sum()),
                                      rng.multinomial(n_esf.sum(), n_esf / n_esf.sum()))
                        for _ in range(N_BOOTSTRAP)]
                centro = fecha_central(n_esp, n_esf)
                # desenrollar alrededor del centro para el intervalo circular
                boot = centro + (np.asarray(boot) - centro + 6) % 12 - 6
                filas.append({"especie": esp, "cuenca": cuenca, "decada": f"{d}s",
                              "registros": int(n_esp.sum()),
                              "registros_cetaceos": int(n_esf.sum()),
                              "fecha_central": round(centro, 2),
                              "ic95_inf": round(float(np.percentile(boot, 2.5)), 2),
                              "ic95_sup": round(float(np.percentile(boot, 97.5)), 2),
                              "fecha": _como_fecha(centro)})
    return pd.DataFrame(filas)


def _como_fecha(mes_continuo: float) -> str:
    mes = int(mes_continuo)
    dia = int(round((mes_continuo - mes) * 30)) + 1
    return f"{min(dia, 30)} {MESES[(mes - 1) % 12].lower()}"


def fig_estacionalidad(est, especies, destino):
    fig, ejes = plt.subplots(1, len(especies), figsize=(4.1 * len(especies), 3.6),
                             sharey=True, squeeze=False)
    validos = est[est["registros_cuenca"] >= MIN_REGISTROS_CUENCA]
    tope = validos["indice"].max()
    for ax, esp in zip(ejes.flat, especies):
        ax.axhline(1, color=estilo.TINTA_TENUE, linewidth=1)
        for cuenca in CUENCAS:
            d = validos[(validos["especie"] == esp) & (validos["cuenca"] == cuenca)]
            if d.empty:
                continue
            ax.plot(d["mes"], d["indice"], color=COLORES_CUENCA[cuenca],
                    label=f"{cuenca}: {d['registros_cuenca'].iat[0]:,} reg.")
        ax.set_title(estilo.cursiva(esp), fontsize=10.5)
        ax.set_xticks(range(1, 13), [m[0] for m in MESES])
        ax.set_ylim(0, tope * 1.2)
        ax.legend(loc="upper right", fontsize=7.5, handlelength=1.2)
    ejes.flat[0].set_ylabel("Índice (1 = lo esperado por el esfuerzo)")
    fig.suptitle("Estacionalidad de las ballenas, corregida por el esfuerzo de observación de "
                 "cetáceos", x=0.01, ha="left", fontsize=12, fontweight="semibold")
    fig.tight_layout()
    fig.savefig(destino)
    plt.close(fig)


def fig_fenologia(fen, destino):
    especies = list(dict.fromkeys(fen["especie"]))
    fig, ejes = plt.subplots(1, len(especies), figsize=(5.2 * len(especies), 3.9),
                             sharey=True, squeeze=False)

    def eje_temporada(m):              # dic -> 12, ene -> 13, ... para no cortar el invierno
        return np.where(np.asarray(m) < 7, np.asarray(m) + 12, m)

    decadas = [f"{d}s" for d in DECADAS_FENOLOGIA]
    for ax, esp in zip(ejes.flat, especies):
        for k, cuenca in enumerate(["Pacífico", "Golfo de California"]):
            d = fen[(fen["especie"] == esp) & (fen["cuenca"] == cuenca)]
            if d.empty:
                continue
            x = np.array([decadas.index(v) for v in d["decada"]]) + (k - 0.5) * 0.22
            centro = eje_temporada(d["fecha_central"])
            inf, sup = eje_temporada(d["ic95_inf"]), eje_temporada(d["ic95_sup"])
            color = COLORES_CUENCA[cuenca]
            ax.errorbar(x, centro, yerr=[centro - inf, sup - centro], fmt="o", color=color,
                        ecolor=color, elinewidth=2, capsize=0, markersize=7, alpha=0.9,
                        markeredgecolor=estilo.SUPERFICIE, markeredgewidth=1.5, label=cuenca)
            for xi, ci, n in zip(x, centro, d["registros"]):
                ax.annotate(f"{n:,}", (xi, ci), xytext=(7, 0), textcoords="offset points",
                            va="center", fontsize=7.5, color=estilo.TINTA_2)
        ax.set_xticks(range(len(decadas)), decadas)
        ax.set_xlim(-0.6, len(decadas) - 0.2)
        ax.set_title(estilo.cursiva(esp), fontsize=10.5)
        ax.grid(axis="x", visible=False)
        ax.legend(loc="upper left", fontsize=8)
    etiquetas = ["1 dic", "1 ene", "1 feb", "1 mar", "1 abr", "1 may"]
    ejes.flat[0].set_yticks(range(12, 18), etiquetas)
    ejes.flat[0].set_ylabel("Fecha central de la temporada")
    fig.suptitle("Fecha central de la temporada por década (IC 95 %; número = registros)",
                 x=0.01, ha="left", fontsize=12, fontweight="semibold")
    fig.tight_layout()
    fig.savefig(destino)
    plt.close(fig)


# ─────────────────────────────────────────
# M3. Especies en riesgo y vaquita
# ─────────────────────────────────────────

def riesgo_especies(df: pd.DataFrame) -> pd.DataFrame:
    especies = sorted(df["especie"].unique())
    nom = pd.Categorical(valor_nivel_especie(df, "nom059_cod").reindex(especies),
                         categories=CATEGORIAS_NOM, ordered=True)
    iucn = pd.Categorical(valor_nivel_especie(df, "iucn_cod").reindex(especies),
                          categories=CATEGORIAS_IUCN, ordered=True)
    t = pd.DataFrame({"nom059": nom, "iucn": iucn}, index=especies)
    return t[t["nom059"].isin(["A", "P", "E"]) | t["iucn"].isin(IUCN_AMENAZADA)]


def tabla_riesgo(df: pd.DataFrame) -> pd.DataFrame:
    riesgo = riesgo_especies(df)
    sub = df[df["especie"].isin(riesgo.index)]
    g = sub.groupby("especie")
    t = pd.DataFrame({
        "nombre_comun": g["nombrecomun"].agg(
            lambda s: s.dropna().iat[0].split(",")[0].strip() if s.notna().any() else ""),
        "orden": g["ordenvalido"].first(),
        "registros": g.size(),
        "cuencas": g["cuenca"].agg(lambda s: ", ".join(c for c in CUENCAS if c in set(s))),
        "pct_dentro_anp": (g["dentro_anp"].mean() * 100).round(1),
        "anp_principal": g["anp_nombre"].agg(
            lambda s: s.dropna().mode().iat[0] if s.notna().any() else ""),
        "primer_anio": g["anio"].min(),
        "ultimo_anio": g["anio"].max(),
        f"registros_desde_{ANIO_RECIENTE}": g["anio"].agg(
            lambda a: int((a >= ANIO_RECIENTE).sum())),
    }).join(riesgo)
    return t.sort_values(["iucn", "nom059"], ascending=False)


def _eoo_km2(sub) -> float:
    x, y = _A_METROS.transform(sub["longitud"].to_numpy(), sub["latitud"].to_numpy())
    return eoo_km2(np.asarray(x), np.asarray(y))


def vaquita(df: pd.DataFrame) -> pd.DataFrame:
    v = df[(df["especie"] == VAQUITA) & df["anio"].notna()].copy()
    v["decada"] = (v["anio"] // 10 * 10).astype(int)
    g = v.groupby("decada")
    return pd.DataFrame({
        "registros": g.size(),
        "colecciones": g["tipo_registro"].agg(lambda s: int((s == "Coleccion").sum())),
        "eoo_km2": g.apply(_eoo_km2, include_groups=False).round(0),
        "pct_dentro_anp": (g["dentro_anp"].mean() * 100).round(1),
        "ultimo_anio": g["anio"].max(),
    })


def fig_vaquita(df, tabla, destino):
    v = df[(df["especie"] == VAQUITA) & df["anio"].notna()].copy()
    v["decada"] = (v["anio"] // 10 * 10).astype(int)
    fig, (ax_mapa, ax_bar) = plt.subplots(1, 2, figsize=(12, 5),
                                          gridspec_kw={"width_ratios": [1.1, 1]})
    decadas = sorted(v["decada"].unique())
    pasos = np.linspace(1, len(estilo.PASOS_SECUENCIAL) - 1, len(decadas)).round().astype(int)
    colores = {d: estilo.PASOS_SECUENCIAL[i] for d, i in zip(decadas, pasos)}
    for d in decadas:
        sub = v[v["decada"] == d]
        ax_mapa.scatter(sub["longitud"], sub["latitud"], s=18, color=colores[d],
                        edgecolors=estilo.SUPERFICIE, linewidths=0.5, label=f"{d}s ({len(sub)})")
        puntos = sub[["longitud", "latitud"]].drop_duplicates().to_numpy()
        if len(puntos) >= 3:
            casco = ConvexHull(puntos)
            vert = np.append(casco.vertices, casco.vertices[0])
            ax_mapa.plot(puntos[vert, 0], puntos[vert, 1], color=colores[d], linewidth=1)
    ax_mapa.set_aspect("equal")
    ax_mapa.set_xlabel("Longitud")
    ax_mapa.set_ylabel("Latitud")
    ax_mapa.legend(title="Década (registros)", fontsize=8.5, title_fontsize=9)
    ax_mapa.set_title("Registros y polígono convexo por década", fontsize=10.5)

    x = np.arange(len(tabla))
    ax_bar.bar(x, tabla["registros"], color=[colores[d] for d in tabla.index], width=0.6)
    for xi, (n, eoo, anp) in enumerate(zip(tabla["registros"], tabla["eoo_km2"],
                                           tabla["pct_dentro_anp"])):
        ax_bar.annotate(f"{n} reg.\nEOO {eoo:,.0f} km²\n{anp:.0f} % en ANP", (xi, n),
                        xytext=(0, 4), textcoords="offset points", ha="center", va="bottom",
                        fontsize=8, color=estilo.TINTA_2)
    ax_bar.set_xticks(x, [f"{d}s" for d in tabla.index])
    ax_bar.set_ylim(0, tabla["registros"].max() * 1.45)
    ax_bar.set_ylabel("Registros")
    ax_bar.grid(axis="x", visible=False)
    ax_bar.set_title(f"Último registro en el SNIB: {int(tabla['ultimo_anio'].max())}",
                     fontsize=10.5)
    fig.suptitle(f"Vaquita marina ({estilo.cursiva(VAQUITA)}) en los registros del SNIB",
                 x=0.01, ha="left", fontsize=12, fontweight="semibold")
    fig.tight_layout()
    fig.savefig(destino)
    plt.close(fig)


# ─────────────────────────────────────────
# Ejecucion
# ─────────────────────────────────────────

def main(ballenas):
    SALIDA.mkdir(parents=True, exist_ok=True)
    estilo.aplicar()
    csv = {"encoding": "utf-8-sig"}
    df = preparar()
    print(f"{len(df):,} registros de {df['especie'].nunique()} especies marinas en Mexico")

    # M1
    tabla = tabla_cuencas(df)
    tabla.to_csv(SALIDA / "cuencas.csv", index_label="cuenca", **csv)
    conteos = {c: g["especie"].value_counts().to_numpy()
               for c, g in df.groupby("cuenca", observed=True)}
    curvas = curvas_rarefaccion(conteos)
    fig_cuencas(df, curvas, tabla, SALIDA / "cuencas.png")
    pa = presencia_cuencas(df)
    beta = beta_pares(pa)
    beta.to_csv(SALIDA / "beta_cuencas.csv", index=False, **csv)
    exc = exclusivas(df, pa)
    exc.to_csv(SALIDA / "exclusivas_cuencas.csv", index=False, **csv)
    print("\n[M1] Diversidad por cuenca:")
    print(tabla.to_string())
    print(beta[["unidad_1", "unidad_2", "compartidas", "jaccard_similitud", "beta_recambio",
                "beta_anidamiento"]].to_string(index=False))
    print("exclusivas:", exc.groupby("cuenca", observed=True).size().to_dict())

    # M2
    est = estacionalidad_ballenas(df, ballenas)
    est.to_csv(SALIDA / "estacionalidad_ballenas.csv", index=False, **csv)
    fig_estacionalidad(est, ballenas, SALIDA / "estacionalidad_ballenas.png")
    pico = est[est["registros_cuenca"] >= MIN_REGISTROS_CUENCA].loc[
        lambda d: d.groupby(["especie", "cuenca"], observed=True)["indice"].idxmax()]
    print("\n[M2] Mes de maximo indice por especie y cuenca:")
    print(pico.assign(mes=pico["mes"].map(lambda m: MESES[m - 1]))[
        ["especie", "cuenca", "mes", "indice", "registros_cuenca"]].to_string(index=False))
    fen = fenologia(df, [e for e in FENOLOGIA if e in ballenas])
    fen.to_csv(SALIDA / "fenologia_ballenas.csv", index=False, **csv)
    if not fen.empty:
        fig_fenologia(fen, SALIDA / "fenologia_ballenas.png")
    print("\n[M2] Fecha central de la temporada por decada:")
    print(fen.to_string(index=False))

    # M3
    riesgo = tabla_riesgo(df)
    riesgo.to_csv(SALIDA / "riesgo_marinos.csv", index_label="especie", **csv)
    print(f"\n[M3] {len(riesgo)} especies marinas en riesgo (NOM-059 A/P/E o IUCN VU-EX):")
    print(riesgo[["nom059", "iucn", "registros", "cuencas", "pct_dentro_anp", "ultimo_anio",
                  f"registros_desde_{ANIO_RECIENTE}"]].to_string())
    vq = vaquita(df)
    vq.to_csv(SALIDA / "vaquita.csv", index_label="decada", **csv)
    fig_vaquita(df, vq, SALIDA / "vaquita.png")
    print("\n[M3] Vaquita por decada:")
    print(vq.to_string())
    print(f"\nSalidas en {SALIDA}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--ballenas", nargs="+", default=BALLENAS,
                        help="especies para la estacionalidad (binomio)")
    main(parser.parse_args().ballenas)
