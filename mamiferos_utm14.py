import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns

# Cargar datos desde el Parquet maestro del SNIB (contiene TODOS los ejemplares:
# las 7 zonas UTM de Mexico + Centroamerica + EUA), filtrando por el mismo
# criterio geografico + pais que usa CONABIO para armar mamiferosutm14a.csv
# (verificado por idejemplar: coincide 1:1 con el CSV original de la zona).
# Ruta relativa: el parquet vive dentro de este mismo proyecto.
PARQUET_MAESTRO = "mamiferos.202503.parquet/mamiferos.parquet"

df = pd.read_parquet(PARQUET_MAESTRO)
df = df[
    (df["longitud"] > -102) & (df["longitud"] <= -99) &
    (df["latitud"] >= 12) & (df["latitud"] <= 32) &
    (df["paismapa"] == "MEXICO")
]

#Exploración de datos
#print(df.head(5))
#print(list(df.columns))

# Filtrar por subgrupobio
perritos = df[df["subgrupobio"] == "ardillas, marmotas, perritos de la pradera"]

# Seleccionar solo las columnas de interés
columnas = ["familiavalida", "generovalido", "longitud", "latitud", 
            "estadomapa", "nombrecomun", "ambiente"]

# Extraer solo esas columnas
perritos_info = perritos[columnas]

# ─────────────────────────────────────────
# Corroborar que se extraen correctamente
# ─────────────────────────────────────────

# Ver las primeras filas
print(perritos_info.head(10))

# Ver familias únicas
print("\nFamilias encontradas:")
print(perritos_info["familiavalida"].unique())

# Ver géneros únicos
print("\nGéneros encontrados:")
print(perritos_info["generovalido"].unique())

# Ver nombres comunes únicos
print("\nNombres comunes encontrados:")
print(perritos_info["nombrecomun"].unique())

# Verificar rango de coordenadas (sanity check)
print("\nRango de Longitud:", perritos_info["longitud"].min(), "a", perritos_info["longitud"].max())
print("Rango de Latitud:", perritos_info["latitud"].min(), "a", perritos_info["latitud"].max())

# Revisar si hay valores nulos en las columnas clave
print("\nValores nulos por columna:")
print(perritos_info[["familiavalida", "generovalido", "longitud", "latitud", "nombrecomun"]].isnull().sum())
