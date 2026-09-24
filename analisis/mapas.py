"""Mapas de distribucion: celdas de riqueza/esfuerzo y registros por especie.

Uso:
    python -m analisis.mapas                      # celdas de Mexico + especie ejemplo
    python -m analisis.mapas --especie "Lynx rufus" "Tapirus bairdii"
    python -m analisis.mapas --unidades 15 16 GUATEMALA BELICE

Salidas en outputs/mapas/:
    celdas.html     mapa interactivo; se elige la capa en el control de capas
                    (arriba a la derecha) y cada celda muestra su ficha al pasar el cursor
    celdas.png      las mismas seis capas como mapas pequenos, para reportes
    celdas.csv      metricas por celda (tabla de respaldo de ambos mapas)
    especie_<nombre>.html   registros de una especie coloreados por periodo

El mapa base (Esri, gris claro) se descarga al abrir el HTML: requiere internet.
"""
import argparse
import html
import re

import folium
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from branca.element import Element, MacroElement, Template
from matplotlib.colors import ListedColormap
from matplotlib.patches import Patch

from analisis import estilo
from config import ANIO_RECIENTE, CELDA_GRADOS, DIR_OUTPUTS, ZONAS_UTM
from pipeline.io import cargar_procesado

SALIDA = DIR_OUTPUTS / "mapas"
ESPECIE_EJEMPLO = "Cynomys mexicanus"
MIN_REGISTROS_RAZON = 5
COLUMNAS = ["unidad", "especie", "zona_utm", "celda_id", "celda_lon", "celda_lat",
            "endemica_especie", "en_nom059", "iucn_amenazada", "es_marino", "es_exotica",
            "dup_evento", "anio"]


# ─────────────────────────────────────────
# Metricas por celda
# ─────────────────────────────────────────

def metricas_celdas(df: pd.DataFrame) -> pd.DataFrame:
    """Una fila por celda con esfuerzo, riqueza, endemicas, riesgo y ultimo registro."""
    g = df.groupby("celda_id")
    celdas = pd.DataFrame({
        "lon": g["celda_lon"].first(),
        "lat": g["celda_lat"].first(),
        "zona": g["unidad"].agg(lambda s: s.mode().iat[0]),
        "registros": g.size(),
        "especies": g["especie"].nunique(),
        "endemicas": df[df["endemica_especie"]].groupby("celda_id")["especie"].nunique(),
        "en_riesgo": df[df["en_nom059"] | df["iucn_amenazada"]]
                     .groupby("celda_id")["especie"].nunique(),
        "pct_recientes": g["anio"].agg(
            lambda a: (a.dropna() >= ANIO_RECIENTE).mean() * 100 if a.notna().any() else np.nan
        ).round(1),
        "especies_top": g["especie"].agg(
            lambda s: ", ".join(s.value_counts().index[:3])),
    })
    celdas[["endemicas", "en_riesgo"]] = celdas[["endemicas", "en_riesgo"]].fillna(0).astype(int)
    celdas["razon_esperada"] = razon_riqueza_esperada(celdas)
    return celdas.reset_index()


def razon_riqueza_esperada(celdas: pd.DataFrame) -> pd.Series:
    """Especies observadas / esperadas segun el esfuerzo de la celda.

    Ajusta log(especies) ~ log(registros) (cuadratico, capta la saturacion)
    sobre celdas con >= MIN_REGISTROS_RAZON. >1: mas especies de las que el
    esfuerzo explica (candidata a hotspot real); <1: menos.
    """
    ok = celdas["registros"] >= MIN_REGISTROS_RAZON
    x = np.log(celdas.loc[ok, "registros"])
    y = np.log(celdas.loc[ok, "especies"])
    esperado = np.exp(np.polyval(np.polyfit(x, y, 2), x))
    return (celdas.loc[ok, "especies"] / esperado).round(2).reindex(celdas.index)


# ─────────────────────────────────────────
# Clasificacion en clases de color
# ─────────────────────────────────────────

def _pasos(n):
    idx = np.linspace(0, len(estilo.PASOS_SECUENCIAL) - 1, n).round().astype(int)
    return [estilo.PASOS_SECUENCIAL[i] for i in idx]


def clases_conteo(valores: pd.Series, n=6):
    """Cuantiles sobre los valores > 0; el cero es su propia clase (gris neutro)."""
    positivos = valores[valores > 0]
    cortes = np.unique(np.round(np.quantile(positivos, np.linspace(0, 1, n + 1))))
    cortes[0] = 0
    etiquetas = [f"{int(a) + 1:,}" if a + 1 == b else f"{int(a) + 1:,}–{int(b):,}"
                 for a, b in zip(cortes[:-1], cortes[1:])]
    clase = pd.cut(valores, bins=cortes, labels=etiquetas)
    clase = clase.cat.add_categories("0").cat.reorder_categories(["0"] + etiquetas)
    clase = clase.fillna("0")
    return clase, [estilo.NEUTRO] + _pasos(len(etiquetas))


def clases_razon(valores: pd.Series):
    cortes = [0, 0.5, 0.7, 0.87, 1.15, 1.4, 2, np.inf]
    etiquetas = ["< 0.5×", "0.5–0.7×", "0.7–0.87×", "≈ esperado",
                 "1.15–1.4×", "1.4–2×", "> 2×"]
    return pd.cut(valores, bins=cortes, labels=etiquetas), estilo.PASOS_DIVERGENTE


def clases_porcentaje(valores: pd.Series):
    cortes = [-0.1, 20, 40, 60, 80, 100]
    etiquetas = ["0–20 %", "20–40 %", "40–60 %", "60–80 %", "80–100 %"]
    clase = pd.cut(valores, bins=cortes, labels=etiquetas)
    clase = clase.cat.add_categories("sin fecha").fillna("sin fecha")
    return clase, _pasos(len(etiquetas)) + [estilo.OTROS]


# nombre de capa, columna, descripcion, funcion de clases
CAPAS = [
    ("Esfuerzo de muestreo", "registros",
     "Registros por celda (sin duplicados de evento)", clases_conteo),
    ("Riqueza observada", "especies",
     "Especies registradas por celda", clases_conteo),
    ("Riqueza vs. esperada", "razon_esperada",
     "Especies observadas ÷ esperadas para el esfuerzo de la celda. "
     f"Azul: más de lo esperado. Sin color: menos de {MIN_REGISTROS_RAZON} registros.",
     clases_razon),
    ("Especies endémicas", "endemicas",
     "Especies endémicas de México registradas por celda", clases_conteo),
    ("Especies en riesgo", "en_riesgo",
     "Especies en NOM-059 o IUCN VU/EN/CR por celda", clases_conteo),
    ("Registros recientes", "pct_recientes",
     f"% de los registros fechados de la celda que son de {ANIO_RECIENTE} en adelante. "
     "Claro: la celda se conoce sobre todo por colectas antiguas.",
     clases_porcentaje),
]


def clasificar(celdas: pd.DataFrame):
    """Devuelve {capa: (serie de clases, lista de colores por clase)}."""
    return {nombre: funcion(celdas[col]) for nombre, col, _, funcion in CAPAS}


# ─────────────────────────────────────────
# Mapa interactivo de celdas (folium)
# ─────────────────────────────────────────

CSS = """
<style>
.caja-mapa { position: fixed; z-index: 1000; background: #fcfcfb; color: #0b0b0b;
  border: 1px solid rgba(11,11,11,.10); border-radius: 8px; padding: 10px 12px;
  font: 12px/1.4 system-ui, -apple-system, "Segoe UI", sans-serif;
  box-shadow: 0 1px 4px rgba(0,0,0,.08); max-width: 270px; }
.caja-mapa[hidden] { display: none; }
.caja-mapa h4 { margin: 0 0 2px; font-size: 13px; font-weight: 600; }
.caja-mapa p { margin: 0 0 8px; color: #52514e; }
.fila-leyenda { display: flex; align-items: center; gap: 8px; margin: 2px 0;
  font-variant-numeric: tabular-nums; }
.muestra { width: 14px; height: 14px; border-radius: 3px; flex: none; }
.punto { width: 10px; height: 10px; border-radius: 50%; flex: none; }
.etiqueta-zona { font: 600 12px system-ui, "Segoe UI", sans-serif; color: #52514e;
  white-space: nowrap; transform: translate(-50%, -50%); }
.leaflet-tooltip { font: 12px/1.45 system-ui, "Segoe UI", sans-serif; }
</style>
"""


class _CambioDeCapa(MacroElement):
    """Pinta el GeoJSON de celdas segun la capa base elegida y cambia la leyenda.
    Un solo GeoJSON (y no uno por capa) mantiene el HTML en ~2 MB."""
    _template = Template("""
{% macro script(this, kwargs) %}
(function () {
  var mapa = {{ this._parent.get_name() }};
  var celdas = {{ this.celdas.get_name() }};
  var campos = {{ this.campos|tojson }};
  var capaActual = {{ this.inicial|tojson }};
  var base = {weight: 0.4, color: '#ffffff'};
  function pintar(nombre) {
    capaActual = nombre;
    var campo = campos[nombre];
    celdas.setStyle(function (f) {
      var c = f.properties[campo];
      return c ? {fillColor: c, fillOpacity: 0.82, opacity: 1,
                  weight: base.weight, color: base.color}
               : {fillOpacity: 0, opacity: 0};
    });
    document.querySelectorAll('.leyenda-capa').forEach(function (d) {
      d.hidden = d.dataset.capa !== nombre;
    });
  }
  mapa.on('baselayerchange', function (e) { pintar(e.name); });
  celdas.on('mouseover', function (e) {
    if (e.layer.feature.properties[campos[capaActual]]) {
      e.layer.setStyle({weight: 2, color: '#0b0b0b'}); e.layer.bringToFront();
    }
  });
  celdas.on('mouseout', function (e) {
    if (e.layer.feature.properties[campos[capaActual]]) e.layer.setStyle(base);
  });
  pintar(capaActual);
})();
{% endmacro %}
""")

    def __init__(self, celdas, campos, inicial):
        super().__init__()
        self.celdas, self.campos, self.inicial = celdas, campos, inicial


def _leyenda_html(nombre, descripcion, colores_por_clase, visible):
    filas = "".join(
        f'<div class="fila-leyenda"><span class="muestra" style="background:{c}"></span>'
        f"{html.escape(str(e))}</div>"
        for e, c in colores_por_clase)
    oculto = "" if visible else " hidden"
    return (f'<div class="caja-mapa leyenda-capa" data-capa="{html.escape(nombre)}" '
            f'style="left:12px;bottom:44px"{oculto}><h4>{html.escape(nombre)}</h4>'
            f"<p>{html.escape(descripcion)}</p>{filas}</div>")


def _json_valor(v):
    if isinstance(v, (float, np.floating)) and np.isnan(v):
        return None
    return v.item() if isinstance(v, np.generic) else v


def agregar_mapa_base(mapa):
    """Gris claro de Esri: no pide API key (CARTO la exige al abrir desde file://)."""
    folium.TileLayer(
        "https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/"
        "World_Light_Gray_Base/MapServer/tile/{z}/{y}/{x}",
        attr="Tiles &copy; Esri &mdash; Esri, DeLorme, NAVTEQ", max_zoom=16,
        name="Mapa base", overlay=True, control=False,
    ).add_to(mapa)


def agregar_zonas(mapa, lat=(14.3, 32.7)):
    """Meridianos que separan las zonas UTM, con su nombre arriba."""
    grupo = folium.FeatureGroup(name="Límites de zonas UTM", overlay=True)
    limites = sorted({lim for z in ZONAS_UTM.values() for lim in z})[1:-1]
    for lon in limites:
        folium.PolyLine([(lat[0], lon), (lat[1], lon)], color=estilo.TINTA_2,
                        weight=1.5, opacity=0.8).add_to(grupo)
    for nombre, (oeste, este) in ZONAS_UTM.items():
        folium.Marker(
            (lat[1] + 0.6, (max(oeste, -118) + este) / 2),
            icon=folium.DivIcon(html=f'<div class="etiqueta-zona">{nombre}</div>',
                                icon_size=(0, 0)),
        ).add_to(grupo)
    grupo.add_to(mapa)


def mapa_celdas(celdas: pd.DataFrame, clases: dict, destino):
    mitad = CELDA_GRADOS / 2
    campos = {}
    propiedades = celdas.copy()
    for i, (nombre, col, _, _) in enumerate(CAPAS):
        clase, colores = clases[nombre]
        color_de = dict(zip(clase.cat.categories, colores))
        campos[nombre] = f"c{i}"
        propiedades[f"c{i}"] = clase.map(color_de).astype(object)
        if col == "razon_esperada":
            propiedades.loc[celdas["razon_esperada"].isna(), f"c{i}"] = None
    propiedades["pct_recientes"] = propiedades["pct_recientes"].map(
        lambda v: "sin fecha" if pd.isna(v) else f"{v:.0f} %")
    propiedades["razon_esperada"] = propiedades["razon_esperada"].map(
        lambda r: f"pocos registros (< {MIN_REGISTROS_RAZON})" if pd.isna(r) else f"{r:.2f}×")

    campos_tooltip = ["celda_id", "zona", "registros", "especies", "razon_esperada",
                      "endemicas", "en_riesgo", "pct_recientes", "especies_top"]
    features = []
    for fila in propiedades.to_dict("records"):
        x, y = fila["lon"], fila["lat"]
        features.append({
            "type": "Feature",
            "geometry": {"type": "Polygon", "coordinates": [[
                [x - mitad, y - mitad], [x + mitad, y - mitad], [x + mitad, y + mitad],
                [x - mitad, y + mitad], [x - mitad, y - mitad]]]},
            "properties": {k: _json_valor(fila[k])
                           for k in campos_tooltip + list(campos.values())},
        })

    mapa = folium.Map(location=[23.5, -101.5], zoom_start=5, tiles=None,
                      control_scale=True, prefer_canvas=True)
    agregar_mapa_base(mapa)
    # Capas base vacias: solo alimentan el selector (radio) del control de capas
    for i, (nombre, *_) in enumerate(CAPAS):
        folium.FeatureGroup(name=nombre, overlay=False, show=i == 0).add_to(mapa)

    geojson = folium.GeoJson(
        {"type": "FeatureCollection", "features": features}, name="celdas", control=False,
        tooltip=folium.GeoJsonTooltip(
            fields=campos_tooltip,
            aliases=["Celda", "Zona", "Registros", "Especies", "Obs. / esperadas",
                     "Endémicas", "En riesgo", f"Desde {ANIO_RECIENTE}", "Más registradas"],
            localize=True, sticky=True),
    ).add_to(mapa)
    agregar_zonas(mapa)
    folium.LayerControl(collapsed=False).add_to(mapa)
    mapa.add_child(_CambioDeCapa(geojson, campos, CAPAS[0][0]))

    raiz = mapa.get_root()
    raiz.header.add_child(Element(CSS))
    for i, (nombre, _, descripcion, _) in enumerate(CAPAS):
        clase, colores = clases[nombre]
        raiz.html.add_child(Element(_leyenda_html(
            nombre, descripcion, zip(clase.cat.categories, colores), visible=i == 0)))
    mapa.save(destino)


# ─────────────────────────────────────────
# Mapas estaticos de celdas (PNG)
# ─────────────────────────────────────────

def fig_celdas(celdas: pd.DataFrame, clases: dict, destino):
    ix = np.rint(celdas["lon"] / CELDA_GRADOS - 0.5).astype(int)
    iy = np.rint(celdas["lat"] / CELDA_GRADOS - 0.5).astype(int)
    ancho, alto = ix.max() - ix.min() + 1, iy.max() - iy.min() + 1
    extension = [ix.min() * CELDA_GRADOS, (ix.max() + 1) * CELDA_GRADOS,
                 iy.min() * CELDA_GRADOS, (iy.max() + 1) * CELDA_GRADOS]
    aspecto = 1 / np.cos(np.deg2rad(celdas["lat"].mean()))

    fig, ejes = plt.subplots(2, 3, figsize=(19, 9.5))
    for ax, (nombre, col, _, _) in zip(ejes.flat, CAPAS):
        clase, colores = clases[nombre]
        rejilla = np.full((alto, ancho), np.nan)
        codigos = clase.cat.codes.to_numpy().astype(float)
        if col == "razon_esperada":
            codigos[celdas["razon_esperada"].isna().to_numpy()] = np.nan
        codigos[codigos < 0] = np.nan
        rejilla[iy - iy.min(), ix - ix.min()] = codigos
        ax.imshow(rejilla, origin="lower", extent=extension, aspect=aspecto,
                  cmap=ListedColormap(colores), vmin=-0.5, vmax=len(colores) - 0.5,
                  interpolation="nearest")
        for lim in sorted({x for z in ZONAS_UTM.values() for x in z})[1:-1]:
            ax.axvline(lim, color=estilo.TINTA_TENUE, linewidth=0.8, zorder=0)
        for zona, (oeste, este) in ZONAS_UTM.items():
            ax.text((max(oeste, extension[0]) + este) / 2, extension[3], zona,
                    ha="center", va="bottom", fontsize=8, color=estilo.TINTA_2)
        ax.set_title(nombre, pad=18)
        ax.set_axis_off()
        ax.legend(handles=[Patch(color=c, label=e) for e, c in
                           zip(clase.cat.categories, colores)],
                  loc="lower left", fontsize=8, handlelength=1, handleheight=1,
                  borderaxespad=0.2)
    fig.suptitle("Mamíferos terrestres por celda de "
                 f"{CELDA_GRADOS}° (líneas: límites de zonas UTM)",
                 x=0.01, ha="left", fontsize=13, fontweight="semibold")
    fig.tight_layout()
    fig.savefig(destino)
    plt.close(fig)


# ─────────────────────────────────────────
# Mapa de una especie
# ─────────────────────────────────────────

PERIODOS = [("antes de 1980", estilo.CATEGORICA[0]),
            ("1980–1999", estilo.CATEGORICA[1]),
            ("2000 en adelante", estilo.CATEGORICA[2]),
            ("sin fecha", estilo.OTROS)]


def _periodo(anio):
    anio = anio.astype(float).to_numpy()  # Int16 con NA -> NaN (comparaciones False)
    return np.select([anio < 1980, anio < 2000, anio >= 2000],
                     [p for p, _ in PERIODOS[:3]], default="sin fecha")


def _estatus(df):
    partes = []
    if df["endemica_especie"].any():
        partes.append("Endémica de México")
    for col, etiqueta in [("nom059_cod", "NOM-059"), ("iucn_cod", "IUCN")]:
        valores = df[col].dropna().astype(str).unique()
        if len(valores):
            partes.append(f"{etiqueta}: {'/'.join(valores)}")
    return " · ".join(partes) or "Sin categoría de riesgo"


def mapa_especie(nombre: str, destino_dir=SALIDA):
    columnas = ["especie", "nombrecomun", "longitud", "latitud", "anio",
                "tipo_registro", "institucion", "estadomapa", "municipiomapa",
                "paismapa", "incertidumbre_m", "endemica_especie", "nom059_cod", "iucn_cod"]
    df = cargar_procesado(columnas=columnas)
    df = df[df["especie"] == nombre]
    if df.empty:
        raise ValueError(f"No hay registros de '{nombre}' (usa el binomio, p. ej. 'Lynx rufus')")

    df = df.assign(periodo=_periodo(df["anio"]),
                   lon=df["longitud"].round(4), lat=df["latitud"].round(4))
    puntos = (df.groupby(["lon", "lat", "periodo"])
              .agg(registros=("especie", "size"), anio_min=("anio", "min"),
                   anio_max=("anio", "max"),
                   tipo=("tipo_registro", lambda s: s.mode().iat[0]),
                   institucion=("institucion", "first"),
                   estado=("estadomapa", "first"), municipio=("municipiomapa", "first"),
                   pais=("paismapa", "first"), incert=("incertidumbre_m", "median"))
              .reset_index())

    mapa = folium.Map(tiles=None, control_scale=True, prefer_canvas=True)
    agregar_mapa_base(mapa)
    filas_leyenda = []
    for periodo, color in PERIODOS:
        sub = puntos[puntos["periodo"] == periodo]
        n_reg = int(sub["registros"].sum())
        if sub.empty:
            continue
        grupo = folium.FeatureGroup(name=f"{periodo} ({n_reg:,} registros)")
        for p in sub.itertuples():
            folium.CircleMarker(
                (p.lat, p.lon), radius=5, weight=1.5, color=estilo.SUPERFICIE,
                fill=True, fill_color=color, fill_opacity=0.9,
                tooltip=_tooltip_punto(p),
            ).add_to(grupo)
        grupo.add_to(mapa)
        filas_leyenda.append(
            f'<div class="fila-leyenda"><span class="punto" style="background:{color}">'
            f"</span>{periodo}<span style='margin-left:auto;color:#52514e'>{n_reg:,}</span></div>")

    if (df["paismapa"] == "MEXICO").any():
        agregar_zonas(mapa)
    folium.LayerControl(collapsed=False).add_to(mapa)
    mapa.fit_bounds([[puntos["lat"].min(), puntos["lon"].min()],
                     [puntos["lat"].max(), puntos["lon"].max()]], padding=(30, 30))

    comun = df["nombrecomun"].dropna()
    comun = comun.iat[0].split(",")[0] if len(comun) else ""
    leyenda = (f'<div class="caja-mapa" style="left:12px;bottom:44px">'
               f"<h4><i>{html.escape(nombre)}</i></h4>"
               f"<p>{html.escape(comun)}<br>{html.escape(_estatus(df))}<br>"
               f"{len(df):,} registros en {len(puntos):,} puntos</p>"
               f"{''.join(filas_leyenda)}</div>")
    mapa.get_root().header.add_child(Element(CSS))
    mapa.get_root().html.add_child(Element(leyenda))

    destino = destino_dir / f"especie_{re.sub(r'[^a-z0-9]+', '_', nombre.lower())}.html"
    mapa.save(destino)
    return destino


def _tooltip_punto(p):
    anios = ("sin fecha" if pd.isna(p.anio_min) else
             f"{int(p.anio_min)}" if p.anio_min == p.anio_max else
             f"{int(p.anio_min)}–{int(p.anio_max)}")
    lugar = ", ".join(str(v) for v in (p.municipio, p.estado, p.pais) if pd.notna(v))
    incert = "desconocida" if pd.isna(p.incert) else f"{p.incert:,.0f} m"
    filas = [("Año", anios), ("Registros", f"{p.registros:,}"), ("Tipo", p.tipo),
             ("Lugar", lugar), ("Institución", p.institucion), ("Incertidumbre", incert)]
    return "<br>".join(f"<b>{k}:</b> {html.escape(str(v))}"
                       for k, v in filas if pd.notna(v) and v != "")


# ─────────────────────────────────────────
# Ejecucion
# ─────────────────────────────────────────

def main(unidades, incluir_marinos=False, incluir_exoticas=False):
    SALIDA.mkdir(parents=True, exist_ok=True)
    estilo.aplicar()

    df = cargar_procesado(unidades, columnas=COLUMNAS)
    df = df[df["especie"].notna() & ~df["dup_evento"]]
    if not incluir_marinos:
        df = df[~df["es_marino"]]
    if not incluir_exoticas:
        df = df[~df["es_exotica"]]

    celdas = metricas_celdas(df)
    clases = clasificar(celdas)
    celdas.to_csv(SALIDA / "celdas.csv", index=False, encoding="utf-8-sig")
    mapa_celdas(celdas, clases, SALIDA / "celdas.html")
    fig_celdas(celdas, clases, SALIDA / "celdas.png")
    print(f"{len(celdas):,} celdas de {CELDA_GRADOS}° a partir de {len(df):,} registros")

    razon = celdas.dropna(subset=["razon_esperada"])
    print("\nCeldas con mas especies de las esperadas por su esfuerzo:")
    print(razon.nlargest(5, "razon_esperada")[
        ["celda_id", "zona", "registros", "especies", "razon_esperada"]].to_string(index=False))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--unidades", nargs="+", default=list(ZONAS_UTM),
                        help="zonas UTM y/o paises; por defecto las 7 zonas de Mexico")
    parser.add_argument("--especie", nargs="+",
                        help="genera solo los mapas de estas especies (binomio)")
    parser.add_argument("--incluir-marinos", action="store_true")
    parser.add_argument("--incluir-exoticas", action="store_true")
    args = parser.parse_args()

    if args.especie:
        SALIDA.mkdir(parents=True, exist_ok=True)
        for especie in args.especie:
            print(f"Mapa de {especie}: {mapa_especie(especie)}")
    else:
        main(args.unidades, args.incluir_marinos, args.incluir_exoticas)
        print(f"\nMapa de {ESPECIE_EJEMPLO}: {mapa_especie(ESPECIE_EJEMPLO)}")
