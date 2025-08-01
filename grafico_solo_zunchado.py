import lasio
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from datetime import datetime, timedelta

# Ruta al archivo LAS
RUTA_LAS = '/mnt/mariadb/autom_nov/data/las/activos/SAI-225_PO-_825_29-07-2025_16-20_3.las'

# Leer archivo LAS
las = lasio.read(RUTA_LAS)

# Obtener datos de PRESION_DE_ZUNCHADO
presion_zunchado = las['PRESION_DE_ZUNCHADO']

# Buscar columnas de fecha y hora
fecha_cols = [c.mnemonic for c in las.curves if 'FECHA' in c.mnemonic.upper() or 'DATE' in c.mnemonic.upper()]
hora_cols = [c.mnemonic for c in las.curves if 'HORA' in c.mnemonic.upper() or 'TIME' in c.mnemonic.upper()]

print(f"Datos de PRESION_DE_ZUNCHADO:")
print(f"Total puntos: {len(presion_zunchado)}")

# Mostrar información sobre todos los valores (incluyendo NaN)
valores_validos = presion_zunchado[~np.isnan(presion_zunchado)]
valores_nan = np.sum(np.isnan(presion_zunchado))
print(f"Puntos válidos: {len(valores_validos)}")
print(f"Puntos NaN: {valores_nan}")
print(f"Rango valores válidos: {np.min(valores_validos):.3f} a {np.max(valores_validos):.3f}")
print(f"TODOS los puntos se mostrarán en el gráfico: {len(presion_zunchado)}")

# Crear eje temporal usando DATE:1 (fecha) + DATE:2 (hora)
if fecha_cols:
    # Usar DATE:1 para fecha y DATE:2 para hora (los datos reales)
    col_fecha = 'DATE:1'  # Fecha 
    col_hora = 'DATE:2'   # Hora real (no BIT_TIME que tiene NaN)
    
    print(f"Usando columnas: {col_fecha} + {col_hora}")
    
    fechas_raw = las[col_fecha]
    horas_raw = las[col_hora]
    
    print(f"Primeros 5 valores fecha: {fechas_raw[:5]}")
    print(f"Primeros 5 valores hora: {horas_raw[:5]}")
    
    # Combinar fecha y hora reales
    fechas = []
    for fecha_val, hora_val in zip(fechas_raw, horas_raw):
        try:
            # Parsear fecha (28/Jul/2025)
            fecha_str = str(fecha_val)  
            fecha_parsed = datetime.strptime(fecha_str, "%d/%b/%Y")
            
            # Parsear hora (00:00:00, 00:00:05, etc.)
            hora_str = str(hora_val)
            hora_parsed = datetime.strptime(hora_str, "%H:%M:%S").time()
            
            # Combinar fecha y hora real
            fecha_hora = datetime.combine(fecha_parsed.date(), hora_parsed)
            fechas.append(fecha_hora)
            
        except Exception as e:
            # Fallback si algo falla
            fechas.append(datetime(2025, 7, 28) + timedelta(seconds=len(fechas)*5))
    
    eje_x = pd.Series(fechas)
    print(f"Primeras 5 fechas combinadas: {eje_x[:5]}")
    print(f"Últimas 5 fechas combinadas: {eje_x[-5:]}")
    eje_x_label = f'{col_fecha} + {col_hora}'
else:
    eje_x = np.arange(len(presion_zunchado))
    eje_x_label = 'Índice'

# Crear el gráfico con TODOS los puntos sin filtrar nada
plt.figure(figsize=(16, 10))

# Usar puntos individuales para mostrar cada valor
plt.scatter(eje_x, presion_zunchado, s=1, alpha=0.7, c='blue', label=f'PRESION_DE_ZUNCHADO ({len(presion_zunchado)} puntos)')

# También línea conectando todos los puntos
plt.plot(eje_x, presion_zunchado, 'b-', linewidth=0.5, alpha=0.5)

# Resaltar estados activos con scatter
mask_activo = (~np.isnan(presion_zunchado)) & (presion_zunchado > 0)
if np.any(mask_activo):
    plt.scatter(eje_x[mask_activo], presion_zunchado[mask_activo], 
                s=2, color='red', alpha=0.8, label=f'Activo ({np.sum(mask_activo)} puntos)')

# Mostrar puntos NaN como cruces
mask_nan = np.isnan(presion_zunchado)
if np.any(mask_nan):
    plt.scatter(eje_x[mask_nan], [0]*np.sum(mask_nan), 
                marker='x', s=10, color='gray', alpha=0.7, label=f'NaN ({np.sum(mask_nan)} puntos)')

plt.title('TODOS los Puntos de Presión de Zunchado vs Fecha/Hora', fontsize=14, fontweight='bold')
plt.xlabel('Fecha y Hora (28/Jul/2025)', fontsize=12)
plt.ylabel('Presión de Zunchado', fontsize=12)
plt.grid(True, alpha=0.3)
plt.legend(fontsize=9)

# Simplificar el eje X para mejor visualización
import matplotlib.dates as mdates
plt.gca().xaxis.set_major_formatter(mdates.DateFormatter('%H:%M'))
plt.gca().xaxis.set_major_locator(mdates.HourLocator(interval=2))
plt.xticks(rotation=45)

# Añadir estadísticas de TODOS los puntos
valores_validos = presion_zunchado[~np.isnan(presion_zunchado)]
stats_text = f"""Estadísticas (TODOS los puntos):
• Total puntos: {len(presion_zunchado):,}
• Puntos válidos: {len(valores_validos):,}
• Puntos NaN: {np.sum(np.isnan(presion_zunchado)):,}
• Mín: {np.nanmin(presion_zunchado):.3f}
• Máx: {np.nanmax(presion_zunchado):.3f}
• Promedio: {np.nanmean(presion_zunchado):.3f}
• Tiempo activo: {np.sum(valores_validos > 0)/len(valores_validos)*100:.1f}%"""

plt.text(0.02, 0.98, stats_text, transform=plt.gca().transAxes, 
         fontsize=9, verticalalignment='top', 
         bbox=dict(boxstyle='round', facecolor='wheat', alpha=0.8))

plt.tight_layout()
plt.savefig('grafico_solo_zunchado.png', dpi=300, bbox_inches='tight')
plt.close()

print(f"\nGráfico guardado como 'grafico_solo_zunchado.png'")
print(f"Valores únicos en la curva: {np.unique(valores_validos)}")

# Análisis de transiciones ON/OFF
transiciones = []
estado_anterior = valores_validos[0]
for i, valor in enumerate(valores_validos[1:], 1):
    if valor != estado_anterior:
        transiciones.append((i, estado_anterior, valor))
        estado_anterior = valor

print(f"\nTransiciones detectadas: {len(transiciones)}")
if len(transiciones) <= 10:
    for i, (idx, antes, despues) in enumerate(transiciones):
        print(f"  {i+1}. Índice {idx}: {antes:.3f} → {despues:.3f}")
else:
    print("Primeras 5 transiciones:")
    for i, (idx, antes, despues) in enumerate(transiciones[:5]):
        print(f"  {i+1}. Índice {idx}: {antes:.3f} → {despues:.3f}")
