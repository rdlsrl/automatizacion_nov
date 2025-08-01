import lasio
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from datetime import datetime, timedelta

# Leer archivo LAS completo
las = lasio.read('/mnt/mariadb/autom_nov/data/las/activos/SAI-225_PO-_825_29-07-2025_16-20_3.las')

# Obtener datos de las presiones y fechas
presion_zunchado = las['PRESION_DE_ZUNCHADO']
presion_hidraulica = las['PRESION_CIRCULACION_HIDRAULICA']
presion_guinche = las['PRESION_GUINCHE'] if 'PRESION_GUINCHE' in las.keys() else presion_hidraulica  # Usar hidráulica como alternativa
fechas_raw = las['DATE:1']
horas_raw = las['DATE:2']

print(f"DATOS COMPLETOS:")
print(f"PRESION_DE_ZUNCHADO: {len(presion_zunchado)} puntos")
print(f"PRESION_DE_GUINCHE: {len(presion_guinche)} puntos")

# Crear timestamps
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
        timestamps.append(datetime(2025, 7, 28) + timedelta(seconds=i*5))

# Analizar datos de guinche
guinche_validos = presion_guinche[~np.isnan(presion_guinche)]
print(f"PRESION_DE_GUINCHE - Válidos: {len(guinche_validos)}, Rango: {np.min(guinche_validos):.3f} a {np.max(guinche_validos):.3f}")

# Crear gráfico con dos presiones
fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(20, 14), sharex=True)

# GRÁFICO 1: PRESIÓN DE ZUNCHADO
ax1.scatter(timestamps, presion_zunchado, s=1, alpha=0.8, c='blue', label=f'Zunchado ({len(presion_zunchado)} puntos)')
ax1.plot(timestamps, presion_zunchado, 'b-', linewidth=0.3, alpha=0.6)

# Resaltar activos en zunchado
for i, (ts, valor) in enumerate(zip(timestamps, presion_zunchado)):
    if not np.isnan(valor) and valor > 0:
        ax1.scatter(ts, valor, s=2, color='red', alpha=0.9, zorder=5)

ax1.set_ylabel('Presión de Zunchado', fontsize=12)
ax1.set_title('PRESIÓN DE ZUNCHADO vs PRESIÓN DE GUINCHE - CONEXIONES OPERACIONALES\n17,280 puntos del 28/Jul/2025', fontsize=16, fontweight='bold')
ax1.grid(True, alpha=0.3)
ax1.legend()

# GRÁFICO 2: PRESIÓN DE GUINCHE
ax2.scatter(timestamps, presion_guinche, s=1, alpha=0.8, c='green', label=f'Guinche ({len(presion_guinche)} puntos)')
ax2.plot(timestamps, presion_guinche, 'g-', linewidth=0.3, alpha=0.6)

# Resaltar valores altos en guinche
guinche_max = np.nanmax(presion_guinche)
umbral_alto = guinche_max * 0.8  # 80% del máximo
for i, (ts, valor) in enumerate(zip(timestamps, presion_guinche)):
    if not np.isnan(valor) and valor > umbral_alto:
        ax2.scatter(ts, valor, s=2, color='orange', alpha=0.9, zorder=5)

ax2.set_ylabel('Presión de Guinche', fontsize=12)
ax2.set_xlabel('Fecha y Hora (28/Jul/2025)', fontsize=12)
ax2.grid(True, alpha=0.3)
ax2.legend()

# Formatear eje X
import matplotlib.dates as mdates
ax2.xaxis.set_major_formatter(mdates.DateFormatter('%H:%M'))
ax2.xaxis.set_major_locator(mdates.HourLocator(interval=2))
plt.xticks(rotation=45)

# Estadísticas combinadas
zunchado_validos = presion_zunchado[~np.isnan(presion_zunchado)]
zunchado_activos = sum(1 for v in zunchado_validos if v > 0)

stats_text = f"""ANÁLISIS CONEXIONES:
ZUNCHADO:
• Total: {len(presion_zunchado):,} puntos
• Activos: {zunchado_activos:,} ({zunchado_activos/len(zunchado_validos)*100:.1f}%)
• Rango: {np.nanmin(presion_zunchado):.3f} - {np.nanmax(presion_zunchado):.3f}

GUINCHE:
• Total: {len(presion_guinche):,} puntos
• Válidos: {len(guinche_validos):,}
• Rango: {np.nanmin(presion_guinche):.3f} - {np.nanmax(presion_guinche):.3f}
• Máximo: {np.nanmax(presion_guinche):.1f}"""

ax1.text(0.02, 0.98, stats_text, transform=ax1.transAxes, fontsize=10,
         verticalalignment='top', bbox=dict(boxstyle='round', facecolor='lightyellow', alpha=0.9))

plt.tight_layout()
plt.savefig('presiones_zunchado_guinche_conexiones.png', dpi=200, bbox_inches='tight')
plt.close()

print(f"\n✅ Gráfico con conexiones guardado: presiones_zunchado_guinche_conexiones.png")
print(f"✅ Zunchado - Puntos activos: {zunchado_activos:,}")
print(f"✅ Guinche - Puntos válidos: {len(guinche_validos):,}")
print(f"✅ Rango temporal: {timestamps[0]} a {timestamps[-1]}")
