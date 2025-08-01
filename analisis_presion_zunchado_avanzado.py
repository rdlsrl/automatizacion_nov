import lasio
import numpy as np
import matplotlib.pyplot as plt
import pandas as pd
from pathlib import Path

# Ruta al archivo LAS (ajustar si es necesario)
RUTA_LAS = '/mnt/mariadb/autom_nov/data/las/activos/SAI-225_PO-_825_29-07-2025_16-20_3.las'

# Nombre de la curva a analizar (ajustar si es necesario)
CURVA = 'PRESION_DE_ZUNCHADO'

# Leer archivo LAS
las = lasio.read(RUTA_LAS)

# Buscar la curva (case-insensitive)
curva_keys = [c.mnemonic for c in las.curves]
if CURVA not in curva_keys:
    # Buscar por lower
    for c in curva_keys:
        if c.lower() == CURVA.lower():
            CURVA = c
            break

if CURVA not in las.curves:
    raise Exception(f'Curva {CURVA} no encontrada en el archivo LAS.')

# Extraer datos
valores = las[CURVA]

# Si hay índice de tiempo o profundidad, usarlo para graficar
eje_x = None
if 'DEPTH' in las.curves:
    eje_x = las['DEPTH']
    eje_x_label = 'Profundidad'
elif 'TIME' in las.curves:
    eje_x = las['TIME']
    eje_x_label = 'Tiempo'
else:
    eje_x = np.arange(len(valores))
    eje_x_label = 'Índice'

# Estadísticas extendidas
print(f'Curva: {CURVA}')
print(f'Total de puntos: {len(valores)}')
print(f'Mínimo: {np.nanmin(valores)}')
print(f'Máximo: {np.nanmax(valores)}')
print(f'Promedio: {np.nanmean(valores)}')
print(f'Mediana: {np.nanmedian(valores)}')
print(f'Desviación estándar: {np.nanstd(valores)}')
print(f'Cuartiles: {np.nanpercentile(valores, [25, 50, 75])}')
print(f'Valores únicos: {np.unique(valores).size}')

# Histograma
plt.figure(figsize=(8,4))
plt.hist(valores, bins=50, color='skyblue', edgecolor='k')
plt.title(f'Histograma de {CURVA}')
plt.xlabel('Valor')
plt.ylabel('Frecuencia')
plt.tight_layout()
plt.savefig('histograma_presion_zunchado.png')
plt.close()

# Boxplot
plt.figure(figsize=(6,2))
plt.boxplot(valores, vert=False)
plt.title(f'Boxplot de {CURVA}')
plt.xlabel('Valor')
plt.tight_layout()
plt.savefig('boxplot_presion_zunchado.png')
plt.close()

# Serie temporal
plt.figure(figsize=(12,4))
plt.plot(eje_x, valores, lw=0.7)
plt.title(f'Serie de {CURVA}')
plt.xlabel(eje_x_label)
plt.ylabel('Valor')
plt.tight_layout()
plt.savefig('serie_presion_zunchado.png')
plt.close()

print('Gráficos guardados:')
print(' - histograma_presion_zunchado.png')
print(' - boxplot_presion_zunchado.png')
print(' - serie_presion_zunchado.png')

# Detección de outliers (IQR)
q1 = np.nanpercentile(valores, 25)
q3 = np.nanpercentile(valores, 75)
iqr = q3 - q1
outliers = ((valores < (q1 - 1.5*iqr)) | (valores > (q3 + 1.5*iqr)))
print(f'Cantidad de outliers detectados (IQR): {np.sum(outliers)}')

# Mostrar algunos valores extremos
if np.sum(outliers) > 0:
    print('Ejemplos de outliers:')
    print(valores[outliers][:10])

# Guardar resumen a CSV
df = pd.DataFrame({CURVA: valores})
df.to_csv('presion_zunchado_valores.csv', index=False)
print('Valores exportados a presion_zunchado_valores.csv')
