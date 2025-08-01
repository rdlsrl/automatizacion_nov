import pandas as pd

# Lee el archivo Excel
df = pd.read_excel("datos_geolog.xlsx")

# Revisa los valores únicos en la columna "litologia"
litologias_unicas = df["litologia"].unique()
print("Total de litologías:", len(litologias_unicas))
print(litologias_unicas)
