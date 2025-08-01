import lasio
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from datetime import datetime, timedelta

# Leer archivo LAS completo
las = lasio.read('/mnt/mariadb/autom_nov/data/las/activos/SAI-225_PO-_825_29-07-2025_16-20_3.las')

# Obtener TODOS los datos sin filtrar nada
presion_zunchado = las['PRESION_DE_ZUNCHADO']
fechas_raw = las['DATE:1']
horas_raw = las['DATE:2']

print(f"DATOS COMPLETOS:")
print(f"Total puntos presión: {len(presion_zunchado)}")
print(f"Total puntos fecha: {len(fechas_raw)}")
print(f"Total puntos hora: {len(horas_raw)}")

# Crear timestamps para CADA punto
timestamps = []
for i, (fecha_val, hora_val) in enumerate(zip(fechas_raw, horas_raw)):
    try:
        fecha_str = str(fecha_val)
        fecha_parsed = datetime.strptime(fecha_str, "%d/%b/%Y")
        
        hora_str = str(hora_val)
        hora_parsed = datetime.strptime(hora_str, "%H:%M:%S").time()
        
        timestamp = datetime.combine(fecha_parsed.date(), hora_parsed)
        timestamps.append(timestamp)
    except Exception as e:
        # Fallback: timestamp incremental cada 5 segundos
        timestamps.append(datetime(2025, 7, 28) + timedelta(seconds=i*5))

print(f"Timestamps creados: {len(timestamps)}")
print(f"Primer timestamp: {timestamps[0]}")
print(f"Último timestamp: {timestamps[-1]}")

# Verificar que tenemos exactamente los mismos puntos
assert len(timestamps) == len(presion_zunchado), f"Error: {len(timestamps)} timestamps vs {len(presion_zunchado)} presiones"

# Crear gráfico SIN filtros - mostrar cada punto individual
plt.figure(figsize=(20, 12))

# Plotear CADA punto como scatter
plt.scatter(timestamps, presion_zunchado, s=1, alpha=0.8, c='blue', label=f'Cada punto ({len(presion_zunchado)} total)')

# Conectar puntos con línea muy fina
plt.plot(timestamps, presion_zunchado, 'b-', linewidth=0.3, alpha=0.6)

# Resaltar puntos donde presión > 0 (sin filtrar NaN primero)
indices_activos = []
valores_activos = []
timestamps_activos = []

for i, (ts, valor) in enumerate(zip(timestamps, presion_zunchado)):
    if not np.isnan(valor) and valor > 0:
        indices_activos.append(i)
        valores_activos.append(valor)
        timestamps_activos.append(ts)

if timestamps_activos:
    plt.scatter(timestamps_activos, valores_activos, s=2, color='red', alpha=0.9, 
                label=f'Activos ({len(timestamps_activos)} puntos)', zorder=5)

# Marcar puntos NaN
indices_nan = []
timestamps_nan = []
for i, (ts, valor) in enumerate(zip(timestamps, presion_zunchado)):
    if np.isnan(valor):
        indices_nan.append(i)
        timestamps_nan.append(ts)

if timestamps_nan:
    plt.scatter(timestamps_nan, [0]*len(timestamps_nan), marker='x', s=15, 
                color='gray', alpha=0.7, label=f'NaN ({len(timestamps_nan)} puntos)')

# Configurar gráfico
plt.title(f'PRESIÓN DE ZUNCHADO - TODOS LOS PUNTOS INDIVIDUALES\n{len(presion_zunchado):,} puntos del 28/Jul/2025', 
          fontsize=16, fontweight='bold')
plt.xlabel('Fecha y Hora', fontsize=14)
plt.ylabel('Presión de Zunchado', fontsize=14)
plt.grid(True, alpha=0.3)
plt.legend(fontsize=12)

# Formatear eje X para mostrar horas
import matplotlib.dates as mdates
plt.gca().xaxis.set_major_formatter(mdates.DateFormatter('%H:%M'))
plt.gca().xaxis.set_major_locator(mdates.HourLocator(interval=2))
plt.xticks(rotation=45)

# Estadísticas detalladas
valores_validos = [v for v in presion_zunchado if not np.isnan(v)]
stats_text = f"""ESTADÍSTICAS COMPLETAS:
• Total puntos: {len(presion_zunchado):,}
• Puntos válidos: {len(valores_validos):,}
• Puntos NaN: {len(timestamps_nan):,}
• Mínimo: {min(valores_validos):.3f}
• Máximo: {max(valores_validos):.3f}
• Promedio: {sum(valores_validos)/len(valores_validos):.3f}
• Puntos activos (>0): {len(timestamps_activos):,}
• % tiempo activo: {len(timestamps_activos)/len(valores_validos)*100:.1f}%"""

plt.text(0.02, 0.98, stats_text, transform=plt.gca().transAxes, fontsize=11,
         verticalalignment='top', bbox=dict(boxstyle='round', facecolor='lightyellow', alpha=0.9))

plt.tight_layout()
plt.savefig('presion_zunchado_completo.png', dpi=200, bbox_inches='tight')
plt.close()

print(f"\n✅ Gráfico completo guardado: presion_zunchado_completo.png")
print(f"✅ Puntos graficados: {len(presion_zunchado):,}")
print(f"✅ Puntos activos: {len(timestamps_activos):,}")
print(f"✅ Puntos NaN: {len(timestamps_nan):,}")
print(f"✅ Rango temporal: {timestamps[0]} a {timestamps[-1]}")
