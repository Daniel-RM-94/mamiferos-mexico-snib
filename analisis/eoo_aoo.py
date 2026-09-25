"""Extension de presencia (EOO) y area de ocupacion (AOO) por especie, y
comparacion con los umbrales del criterio B de la IUCN (evaluacion nacional).

Uso:
    python -m analisis.eoo_aoo
    python -m analisis.eoo_aoo --mapa "Romerolagus diazi" "Lepus flavigularis"

Salidas en outputs/eoo_aoo/:
    eoo_aoo.csv            por especie: EOO y AOO (todos los anos y desde
                           ANIO_RECIENTE), umbrales B1 y B2 que alcanza, categorias actuales
    candidatas.csv         alcanzan umbral de amenaza por B1 (EOO) pero no estan
                           amenazadas en IUCN ni listadas en NOM-059
    eoo_vs_aoo.png         todas las especies contra los umbrales B1/B2
    contraccion.png        especies en riesgo o endemicas que se siguen registrando
                           pero cuya EOO reciente es mucho menor que la historica
                           (las que ya no se registran estan en conservacion.py, D2)
    eoo_<especie>.html     mapa: puntos, poligonos EOO y celdas AOO

Metodo (IUCN Standards and Petitions Committee, 2024):
  * EOO: area del poligono convexo minimo de los puntos. Si EOO < AOO, EOO = AOO.
  * AOO: celdas de 2 x 2 km ocupadas x 4 km2.
  * Areas en Albers equivalente centrada en Mexico (en grados no se miden areas).
  * Umbrales B1 (EOO): CR < 100, EN < 5,000, VU < 20,000 km2.
    Umbrales B2 (AOO): CR < 10, EN < 500, VU < 2,000 km2.

Alcanzar un umbral NO es una categoria: el criterio B exige ademas al menos
dos condiciones (fragmentacion o pocas localidades, declive continuo,
fluctuaciones extremas). La AOO de registros es un minimo: el muestreo
incompleto la subestima. La EOO es sensible a puntos mal georreferenciados.
"""
import argparse
import html
import re

import folium
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from branca.element import Element
from pyproj import Transformer
from scipy.spatial import ConvexHull, QhullError

from analisis import estilo
from analisis.mapas import CSS, agregar_mapa_base, agregar_zonas
from config import ANIO_RECIENTE, DIR_OUTPUTS, ZONAS_UTM
from pipeline.io import cargar_procesado
from pipeline.limpieza import CATEGORIAS_IUCN, CATEGORIAS_NOM, valor_nivel_especie

SALIDA = DIR_OUTPUTS / "eoo_aoo"
PROYECCION = ("+proj=aea +lat_1=14.5 +lat_2=32.5 +lat_0=24 +lon_0=-102 "
              "+datum=WGS84 +units=m +no_defs")
CELDA_AOO_M = 2_000
MAX_INCERTIDUMBRE_EOO_M = 10_000   # para AOO se usa el tamano de celda (2 km)
UMBRALES_EOO = [("CR", 100), ("EN", 5_000), ("VU", 20_000)]
UMBRALES_AOO = [("CR", 10), ("EN", 500), ("VU", 2_000)]
CATEGORIAS_UMBRAL = ["CR", "EN", "VU", "No alcanza", "Pocos registros"]
MIN_LOCALIDADES = 10              # menos localidades: no se evalua (errores, vagabundos)
MIN_PUNTOS_CONTRACCION = 20
MAPAS_EJEMPLO = ["Romerolagus diazi", "Lepus flavigularis"]
COLUMNAS = ["especie", "subespecie", "ordenvalido", "nombrecomun", "longitud", "latitud",
            "anio", "incertidumbre_m", "endemica", "endemica_especie", "nom059_cod",
            "iucn_cod", "dup_evento", "es_marino", "es_exotica", "paismapa"]

_A_METROS = Transformer.from_crs("EPSG:4326", PROYECCION, always_xy=True)
_A_GRADOS = Transformer.from_crs(PROYECCION, "EPSG:4326", always_xy=True)


def preparar(unidades) -> pd.DataFrame:
    df = cargar_procesado(unidades, columnas=COLUMNAS)
    df = df[df["especie"].notna() & ~df["dup_evento"] & ~df["es_exotica"] & ~df["es_marino"]]
    df = df[~(df["incertidumbre_m"] > MAX_INCERTIDUMBRE_EOO_M)].copy()
    df["x"], df["y"] = _A_METROS.transform(df["longitud"].to_numpy(), df["latitud"].to_numpy())
    return df


# ─────────────────────────────────────────
# Calculo
# ─────────────────────────────────────────

def celdas_aoo(x, y) -> set:
    return set(zip(np.floor(x / CELDA_AOO_M).astype(int), np.floor(y / CELDA_AOO_M).astype(int)))


def eoo_km2(x, y) -> float:
    puntos = np.unique(np.column_stack([x, y]).round(0), axis=0)
    if len(puntos) < 3:
        return 0.0
    try:
        return ConvexHull(puntos).volume / 1e6      # en 2D, volume = area
    except QhullError:                             # puntos colineales
        return 0.0


def umbral(valor, umbrales, localidades) -> str:
    """Categoria mas severa cuyo umbral se alcanza."""
    if localidades < MIN_LOCALIDADES:
        return "Pocos registros"
    for categoria, limite in umbrales:
        if valor < limite:
            return categoria
    return "No alcanza"


def metricas(sub: pd.DataFrame) -> dict:
    localidades = len(sub[["x", "y"]].round(-2).drop_duplicates())   # puntos a > 100 m
    precisos = sub[~(sub["incertidumbre_m"] > CELDA_AOO_M)]
    aoo = len(celdas_aoo(precisos["x"].to_numpy(), precisos["y"].to_numpy())) * 4
    eoo = max(eoo_km2(sub["x"].to_numpy(), sub["y"].to_numpy()), aoo)
    b1 = umbral(eoo, UMBRALES_EOO, localidades)
    b2 = umbral(aoo, UMBRALES_AOO, localidades)
    return {"registros": len(sub), "localidades": localidades, "celdas_aoo": aoo // 4,
            "eoo_km2": round(eoo, 1), "aoo_km2": aoo, "umbral_b1": b1, "umbral_b2": b2}


def tabla_eoo_aoo(df: pd.DataFrame) -> pd.DataFrame:
    filas = {}
    for especie, sub in df.groupby("especie"):
        todos = metricas(sub)
        recientes = sub[sub["anio"] >= ANIO_RECIENTE]
        rec = metricas(recientes) if len(recientes) else {
            "registros": 0, "localidades": 0, "celdas_aoo": 0, "eoo_km2": 0.0,
            "aoo_km2": 0, "umbral_b1": "Pocos registros", "umbral_b2": "Pocos registros"}
        filas[especie] = {**todos, **{f"{k}_desde_{ANIO_RECIENTE}": v for k, v in rec.items()}}
    t = pd.DataFrame.from_dict(filas, orient="index")
    rec = f"_desde_{ANIO_RECIENTE}"
    t[f"pct_eoo{rec}"] = (t[f"eoo_km2{rec}"] / t["eoo_km2"] * 100).round(1)
    t[f"pct_aoo{rec}"] = (t[f"aoo_km2{rec}"] / t["aoo_km2"] * 100).round(1)
    for col in ["umbral_b1", "umbral_b2", f"umbral_b1{rec}", f"umbral_b2{rec}"]:
        t[col] = pd.Categorical(t[col], categories=CATEGORIAS_UMBRAL, ordered=True)

    g = df.groupby("especie")
    t["orden"] = g["ordenvalido"].first()
    t["nombre_comun"] = g["nombrecomun"].agg(
        lambda s: s.dropna().iat[0].split(",")[0].strip() if s.notna().any() else "")
    t["endemica"] = g["endemica_especie"].first()
    t["iucn_especie"] = pd.Categorical(valor_nivel_especie(df, "iucn_cod").reindex(t.index),
                                       categories=CATEGORIAS_IUCN, ordered=True)
    t["nom059_especie"] = pd.Categorical(valor_nivel_especie(df, "nom059_cod").reindex(t.index),
                                         categories=CATEGORIAS_NOM, ordered=True)
    return t.sort_values("eoo_km2")


def candidatas(t: pd.DataFrame) -> pd.DataFrame:
    """Alcanzan umbral de amenaza por B1 (EOO) con todos los registros y con los
    recientes, sin estar amenazadas en IUCN ni listadas en NOM-059. Se usa B1
    porque la AOO de registros puntuales queda bajo el umbral VU casi siempre."""
    rec = f"umbral_b1_desde_{ANIO_RECIENTE}"
    amenaza = t["umbral_b1"].isin(["CR", "EN", "VU"]) & t[rec].isin(["CR", "EN", "VU"])
    sin_categoria = ~t["iucn_especie"].isin(["VU", "EN", "CR", "EW", "EX"]) & \
        t["nom059_especie"].isna()
    cols = ["nombre_comun", "orden", "endemica", "iucn_especie", "registros", "localidades",
            "eoo_km2", "aoo_km2", "umbral_b1", f"eoo_km2_desde_{ANIO_RECIENTE}", rec]
    return t.loc[amenaza & sin_categoria, cols].sort_values("eoo_km2")


# ─────────────────────────────────────────
# Figuras
# ─────────────────────────────────────────

GRUPOS_IUCN = [("Amenazada (VU/EN/CR)", ["VU", "EN", "CR"]),
               ("LC o NT", ["LC", "NT"]),
               ("DD o no evaluada", ["DD", None])]


def fig_eoo_aoo(t, destino):
    fig, ax = plt.subplots(figsize=(9.5, 7))
    for (etiqueta, codigos), color in zip(GRUPOS_IUCN[::-1], estilo.CATEGORICA[:3][::-1]):
        iucn = t["iucn_especie"].astype(object)
        mascara = iucn.isin([c for c in codigos if c]) | (iucn.isna() if None in codigos else False)
        sub = t[mascara & (t["localidades"] >= MIN_LOCALIDADES)]
        ax.scatter(sub["aoo_km2"], sub["eoo_km2"], s=26, color=color, alpha=0.8,
                   edgecolors=estilo.SUPERFICIE, linewidths=0.8, label=f"{etiqueta} ({len(sub)})")
    ax.set_xscale("log")
    ax.set_yscale("log")
    for cat, valor in UMBRALES_AOO:
        ax.axvline(valor, color=estilo.TINTA_TENUE, linewidth=1)
        ax.annotate(f"{cat}", (valor, 1), xycoords=("data", "axes fraction"), xytext=(-4, -4),
                    textcoords="offset points", ha="right", va="top", fontsize=8.5,
                    color=estilo.TINTA_2)
    for cat, valor in UMBRALES_EOO:
        ax.axhline(valor, color=estilo.TINTA_TENUE, linewidth=1)
        ax.annotate(f"{cat}", (1, valor), xycoords=("axes fraction", "data"), xytext=(-4, 3),
                    textcoords="offset points", ha="right", fontsize=8.5, color=estilo.TINTA_2)
    ax.xaxis.set_major_formatter(lambda v, _: f"{v:,.0f}")
    ax.yaxis.set_major_formatter(lambda v, _: f"{v:,.0f}")
    ax.set_xlabel("AOO (km², celdas de 2 × 2 km)")
    ax.set_ylabel("EOO (km², polígono convexo mínimo)")
    ax.set_title("Extensión de presencia vs. área de ocupación en México\n"
                 f"(≥ {MIN_LOCALIDADES} localidades; líneas: umbrales B1 y B2 de la IUCN; "
                 "color: categoría IUCN actual)", pad=12)
    ax.legend(loc="lower right", title="IUCN", title_fontsize=9)
    fig.savefig(destino)
    plt.close(fig)


def fig_contraccion(t, destino, top=25):
    rec = f"_desde_{ANIO_RECIENTE}"
    prioritarias = t[(t["endemica"] | t["iucn_especie"].isin(["VU", "EN", "CR"])
                      | t["nom059_especie"].notna())
                     & (t["localidades"] >= MIN_PUNTOS_CONTRACCION)
                     & (t[f"localidades{rec}"] >= MIN_LOCALIDADES)]
    datos = prioritarias.nsmallest(top, f"pct_eoo{rec}").iloc[::-1]
    y = np.arange(len(datos))
    fig, ax = plt.subplots(figsize=(9.5, 0.32 * len(datos) + 2))
    reciente = datos[f"eoo_km2{rec}"]
    ax.hlines(y, reciente, datos["eoo_km2"], color=estilo.REJILLA, linewidth=3)
    ax.scatter(datos["eoo_km2"], y, s=46, color=estilo.OTROS, zorder=3,
               edgecolors=estilo.SUPERFICIE, linewidths=1.5, label="Todos los años")
    ax.scatter(reciente, y, s=46, color=estilo.AZUL, zorder=3,
               edgecolors=estilo.SUPERFICIE, linewidths=1.5, label=f"Desde {ANIO_RECIENTE}")
    etiquetas = []
    for e, fila in datos.iterrows():
        codigos = "/".join(str(v) for v in (fila["nom059_especie"], fila["iucn_especie"])
                           if pd.notna(v))
        etiquetas.append(f"{estilo.cursiva(e)}{' *' if fila['endemica'] else ''}"
                         + (f"  ({codigos})" if codigos else "")
                         + f"  {fila[f'pct_eoo{rec}']:.0f} %")
    ax.set_yticks(y, etiquetas, fontsize=8.5)
    ax.set_xscale("log")
    ax.xaxis.set_major_formatter(lambda v, _: f"{v:,.0f}")
    ax.set_xlabel("EOO (km², escala logarítmica)")
    ax.grid(axis="y", visible=False)
    ax.set_title("Especies en riesgo o endémicas con mayor reducción de EOO reciente\n"
                 f"(≥ {MIN_PUNTOS_CONTRACCION} localidades en total y ≥ {MIN_LOCALIDADES} "
                 f"desde {ANIO_RECIENTE}; * endémica; NOM-059/IUCN; % = EOO reciente / total)",
                 pad=30, fontsize=11)
    ax.legend(loc="lower left", bbox_to_anchor=(0, 1.0), ncols=2, borderaxespad=0.3)
    fig.savefig(destino)
    plt.close(fig)


# ─────────────────────────────────────────
# Mapa de una especie
# ─────────────────────────────────────────

def _poligono_convexo(sub):
    puntos = np.unique(np.column_stack([sub["x"], sub["y"]]).round(0), axis=0)
    if len(puntos) < 3:
        return None
    try:
        vertices = puntos[ConvexHull(puntos).vertices]
    except QhullError:
        return None
    lon, lat = _A_GRADOS.transform(vertices[:, 0], vertices[:, 1])
    return list(zip(lat, lon))


def _celdas_en_grados(sub):
    precisos = sub[~(sub["incertidumbre_m"] > CELDA_AOO_M)]
    cuadros = []
    for cx, cy in celdas_aoo(precisos["x"].to_numpy(), precisos["y"].to_numpy()):
        xs = np.array([cx, cx + 1, cx + 1, cx]) * CELDA_AOO_M
        ys = np.array([cy, cy, cy + 1, cy + 1]) * CELDA_AOO_M
        lon, lat = _A_GRADOS.transform(xs, ys)
        cuadros.append(list(zip(lat, lon)))
    return cuadros


def mapa_eoo(nombre: str, df: pd.DataFrame, t: pd.DataFrame):
    sub = df[df["especie"] == nombre]
    if sub.empty:
        raise ValueError(f"No hay registros de '{nombre}' en las zonas analizadas")
    recientes = sub[sub["anio"] >= ANIO_RECIENTE]
    fila = t.loc[nombre]
    rec = f"_desde_{ANIO_RECIENTE}"

    mapa = folium.Map(tiles=None, control_scale=True, prefer_canvas=True)
    agregar_mapa_base(mapa)
    capas = [("EOO, todos los años", sub, estilo.OTROS),
             (f"EOO desde {ANIO_RECIENTE}", recientes, estilo.AZUL)]
    for etiqueta, datos, color in capas:
        poligono = _poligono_convexo(datos) if len(datos) else None
        if poligono:
            grupo = folium.FeatureGroup(name=etiqueta)
            folium.Polygon(poligono, color=color, weight=2, fill=True, fill_color=color,
                           fill_opacity=0.10).add_to(grupo)
            grupo.add_to(mapa)
    grupo = folium.FeatureGroup(name=f"Celdas AOO ({fila['celdas_aoo']:,} de 2 × 2 km)")
    for cuadro in _celdas_en_grados(sub):
        folium.Polygon(cuadro, color=estilo.CATEGORICA[1], weight=1, fill=True,
                       fill_color=estilo.CATEGORICA[1], fill_opacity=0.6).add_to(grupo)
    grupo.add_to(mapa)
    grupo = folium.FeatureGroup(name="Registros")
    puntos = sub.drop_duplicates(["longitud", "latitud"])
    for p in puntos.itertuples():
        reciente = pd.notna(p.anio) and p.anio >= ANIO_RECIENTE
        folium.CircleMarker(
            (p.latitud, p.longitud), radius=3.5, weight=1, color=estilo.SUPERFICIE, fill=True,
            fill_color=estilo.AZUL if reciente else estilo.TINTA_2, fill_opacity=0.9,
            tooltip="sin fecha" if pd.isna(p.anio) else str(int(p.anio)),
        ).add_to(grupo)
    grupo.add_to(mapa)
    agregar_zonas(mapa)
    folium.LayerControl(collapsed=False).add_to(mapa)
    mapa.fit_bounds([[sub["latitud"].min(), sub["longitud"].min()],
                     [sub["latitud"].max(), sub["longitud"].max()]], padding=(30, 30))

    codigos = " · ".join(f"{k}: {v}" for k, v in
                         [("NOM-059", fila["nom059_especie"]), ("IUCN", fila["iucn_especie"])]
                         if pd.notna(v))
    filas_tabla = "".join(
        f"<tr><td>{html.escape(e)}</td><td style='text-align:right'>{a:,.0f}</td>"
        f"<td style='text-align:right'>{b:,.0f}</td></tr>"
        for e, a, b in [("EOO (km²)", fila["eoo_km2"], fila[f"eoo_km2{rec}"]),
                        ("AOO (km²)", fila["aoo_km2"], fila[f"aoo_km2{rec}"]),
                        ("Registros", fila["registros"], fila[f"registros{rec}"])])
    caja = (f'<div class="caja-mapa" style="left:12px;bottom:44px">'
            f"<h4><i>{html.escape(nombre)}</i>{' (endémica)' if fila['endemica'] else ''}</h4>"
            f"<p>{html.escape(fila['nombre_comun'])}<br>{html.escape(codigos)}</p>"
            f"<table style='border-collapse:collapse;font-variant-numeric:tabular-nums'>"
            f"<tr style='color:#3d3d3d'><td></td><td style='padding-left:12px'>Todos</td>"
            f"<td style='padding-left:12px'>Desde {ANIO_RECIENTE}</td></tr>{filas_tabla}</table>"
            f"<p style='margin-top:8px'>Umbral B1 (EOO): <b>{fila['umbral_b1']}</b> "
            f"(desde {ANIO_RECIENTE}: <b>{fila[f'umbral_b1{rec}']}</b>)<br>"
            f"Umbral B2 (AOO): <b>{fila['umbral_b2']}</b> "
            f"(desde {ANIO_RECIENTE}: <b>{fila[f'umbral_b2{rec}']}</b>)</p></div>")
    mapa.get_root().header.add_child(Element(CSS))
    mapa.get_root().html.add_child(Element(caja))
    destino = SALIDA / f"eoo_{re.sub(r'[^a-z0-9]+', '_', nombre.lower())}.html"
    mapa.save(destino)
    return destino


# ─────────────────────────────────────────
# Ejecucion
# ─────────────────────────────────────────

def main(unidades, especies_mapa):
    SALIDA.mkdir(parents=True, exist_ok=True)
    estilo.aplicar()
    csv = {"encoding": "utf-8-sig"}
    df = preparar(unidades)
    t = tabla_eoo_aoo(df)
    t.to_csv(SALIDA / "eoo_aoo.csv", **csv)
    cand = candidatas(t)
    cand.to_csv(SALIDA / "candidatas.csv", **csv)
    fig_eoo_aoo(t, SALIDA / "eoo_vs_aoo.png")
    fig_contraccion(t, SALIDA / "contraccion.png")

    iucn = t["iucn_especie"].astype(object).fillna("NE")
    print(f"{len(t)} especies nativas terrestres | {len(df):,} registros")
    for col, nombre in [("umbral_b1", "B1 (EOO)"), ("umbral_b2", "B2 (AOO)")]:
        print(f"\nUmbral {nombre}, todos los registros, vs IUCN actual:")
        print(pd.crosstab(t[col], iucn, margins=True, margins_name="Total").to_string())
    print(f"\nCandidatas a revision (B1 de amenaza con todos los registros y desde "
          f"{ANIO_RECIENTE}; sin amenaza en IUCN ni NOM-059): {len(cand)}")
    print(cand.head(15)[["nombre_comun", "endemica", "iucn_especie", "localidades",
                         "eoo_km2", "umbral_b1"]].to_string())

    for especie in especies_mapa:
        print(f"Mapa: {mapa_eoo(especie, df, t)}")
    print(f"\nSalidas en {SALIDA}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--unidades", nargs="+", default=list(ZONAS_UTM))
    parser.add_argument("--mapa", nargs="+", default=MAPAS_EJEMPLO,
                        help="especies para el mapa de EOO/AOO (binomio)")
    args = parser.parse_args()
    main(args.unidades, args.mapa)
