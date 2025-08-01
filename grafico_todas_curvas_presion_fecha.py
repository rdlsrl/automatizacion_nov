import lasio
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from pathlib import Path
from datetime import datetime, timedelta

# Ruta al archivo LAS (ajustar si es necesario)
RUTA_LAS = '/mnt/mariadb/autom_nov/data/las/activos/SAI-225_PO-_825_29-07-2025_16-20_3.las'

# Leer archivo LAS
las = lasio.read(RUTA_LAS)

# Buscar todas las curvas de tipo presión (case-insensitive, contiene 'PRESION')
curvas_presion = [c.mnemonic for c in las.curves if 'PRESION' in c.mnemonic.upper()]
if not curvas_presion:
    raise Exception('No se encontraron curvas de presión en el archivo LAS.')

# Buscar columnas de fecha y hora
fecha_cols = [c.mnemonic for c in las.curves if 'FECHA' in c.mnemonic.upper() or 'DATE' in c.mnemonic.upper()]
hora_cols = [c.mnemonic for c in las.curves if 'HORA' in c.mnemonic.upper() or 'TIME' in c.mnemonic.upper()]

print(f"Columnas de fecha encontradas: {fecha_cols}")
print(f"Columnas de hora encontradas: {hora_cols}")

if fecha_cols and hora_cols:
    # Usar la primera columna de fecha y hora encontradas
    col_fecha = fecha_cols[0]
    col_hora = hora_cols[0]
    print(f"Usando columnas: {col_fecha} + {col_hora}")
    
    fechas_raw = las[col_fecha]
    horas_raw = las[col_hora]
    
    print(f"Primeros 5 valores fecha: {fechas_raw[:5]}")
    print(f"Primeros 5 valores hora: {horas_raw[:5]}")
    
    # Combinar fecha y hora
    fechas = []
    for fecha_val, hora_val in zip(fechas_raw, horas_raw):
        try:
            # Parsear fecha
            fecha_str = str(fecha_val)
            for fmt_fecha in ("%d/%b/%Y", "%d/%m/%Y", "%Y-%m-%d"):
                try:
                    fecha_parsed = datetime.strptime(fecha_str, fmt_fecha)
                    break
                except:
                    continue
            else:
                fecha_parsed = datetime(2025, 7, 28)  # Fecha por defecto
            
            # Parsear hora
            hora_str = str(hora_val)
            for fmt_hora in ("%H:%M:%S", "%H:%M", "%H.%M.%S", "%H.%M"):
                try:
                    hora_parsed = datetime.strptime(hora_str, fmt_hora).time()
                    break
                except:
                    continue
            else:
                hora_parsed = datetime.now().time()  # Hora por defecto
            
            # Combinar fecha y hora
            fecha_hora = datetime.combine(fecha_parsed.date(), hora_parsed)
            fechas.append(fecha_hora)
            
        except Exception as e:
            # Si falla, usar timestamp incremental
            fechas.append(datetime(2025, 7, 28) + timedelta(seconds=len(fechas)*10))
    
    eje_x = pd.Series(fechas)
    print(f"Primeras 5 fechas combinadas: {eje_x[:5]}")
    print(f"Últimas 5 fechas combinadas: {eje_x[-5:]}")
    eje_x_label = f'{col_fecha} + {col_hora}'
elif fecha_cols:
    # Solo fecha disponible
    col_fecha = fecha_cols[0]
    print(f"Solo fecha disponible: {col_fecha}")
    fechas_raw = las[col_fecha]
    fechas = []
    for i, val in enumerate(fechas_raw):
        try:
            fecha_str = str(val)
            for fmt in ("%d/%b/%Y", "%d/%m/%Y", "%Y-%m-%d"):
                try:
                    parsed_date = datetime.strptime(fecha_str, fmt)
                    parsed_date = parsed_date + timedelta(seconds=i*10)
                    fechas.append(parsed_date)
                    break
                except:
                    continue
            else:
                fechas.append(datetime(2025, 7, 28) + timedelta(seconds=i*10))
        except:
            fechas.append(datetime(2025, 7, 28) + timedelta(seconds=i*10))
    
    eje_x = pd.Series(fechas)
    eje_x_label = f'{col_fecha} (simulado con tiempo)'
else:
    eje_x = np.arange(len(las[curvas_presion[0]]))
    eje_x_label = 'Índice'

plt.figure(figsize=(14, 7))
for curva in curvas_presion:
    valores = las[curva]
    plt.plot(eje_x, valores, label=curva, lw=0.8)

plt.title('Curvas de presión vs Fecha/Hora')
plt.xlabel(eje_x_label)
plt.ylabel('Valor')
plt.legend(loc='upper right', fontsize='small', ncol=2)
plt.tight_layout()
plt.savefig('todas_las_curvas_presion_fecha.png')
plt.close()

print(f'Se graficaron {len(curvas_presion)} curvas de presión contra fecha/hora.')
print('Gráfico guardado como todas_las_curvas_presion_fecha.png')
print('Curvas incluidas:')
for c in curvas_presion:
    print(f' - {c}')
