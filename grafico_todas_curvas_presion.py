import lasio
import matplotlib.pyplot as plt
import numpy as np
from pathlib import Path

# Ruta al archivo LAS (ajustar si es necesario)
RUTA_LAS = '/mnt/mariadb/autom_nov/data/las/activos/SAI-225_PO-_825_29-07-2025_16-20_3.las'

# Leer archivo LAS
las = lasio.read(RUTA_LAS)

# Buscar todas las curvas de tipo presión (case-insensitive, contiene 'PRESION')
curvas_presion = [c.mnemonic for c in las.curves if 'PRESION' in c.mnemonic.upper()]

if not curvas_presion:
    raise Exception('No se encontraron curvas de presión en el archivo LAS.')

# Eje X: profundidad si existe, sino índice
if 'DEPTH' in las.curves:
    eje_x = las['DEPTH']
    eje_x_label = 'Profundidad'
else:
    eje_x = np.arange(len(las[curvas_presion[0]]))
    eje_x_label = 'Índice'

plt.figure(figsize=(14, 7))
for curva in curvas_presion:
    valores = las[curva]
    plt.plot(eje_x, valores, label=curva, lw=0.8)

plt.title('Curvas de presión (todas las que contienen PRESION)')
plt.xlabel(eje_x_label)
plt.ylabel('Valor')
plt.legend(loc='upper right', fontsize='small', ncol=2)
plt.tight_layout()
plt.savefig('todas_las_curvas_presion.png')
plt.close()

print(f'Se graficaron {len(curvas_presion)} curvas de presión.')
print('Gráfico guardado como todas_las_curvas_presion.png')
print('Curvas incluidas:')
for c in curvas_presion:
    print(f' - {c}')
