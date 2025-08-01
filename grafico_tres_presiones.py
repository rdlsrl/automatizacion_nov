import lasio
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from datetime import datetime, timedelta

# Leer archivo LAS completo
las = lasio.read('/mnt/mariadb/autom_nov/data/las/activos/SAI-225_PO-_825_29-07-2025_16-20_3.las')

# Obtener datos de las tres presiones
presion_zunchado = las['PRESION_DE_ZUNCHADO']
presion_hidraulica = las['PRESION_CIRCULACION_HIDRAULICA']
presion_raw = las['RAW_PRESION']
fechas_raw = las['DATE:1']
horas_raw = las['DATE:2']

print(f"DATOS COMPLETOS:")
print(f"PRESION_DE_ZUNCHADO: {len(presion_zunchado)} puntos")
print(f"PRESION_CIRCULACION_HIDRAULICA: {len(presion_hidraulica)} puntos")
print(f"RAW_PRESION: {len(presion_raw)} puntos")

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

# Analizar datos de las nuevas presiones
hidraulica_validos = presion_hidraulica[~np.isnan(presion_hidraulica)]
raw_validos = presion_raw[~np.isnan(presion_raw)]

print(f"PRESION_CIRCULACION_HIDRAULICA - Válidos: {len(hidraulica_validos)}, Rango: {np.min(hidraulica_validos):.3f} a {np.max(hidraulica_validos):.3f}")
if len(raw_validos) > 0:
    print(f"RAW_PRESION - Válidos: {len(raw_validos)}, Rango: {np.min(raw_validos):.3f} a {np.max(raw_validos):.3f}")
else:
    print(f"RAW_PRESION - Válidos: {len(raw_validos)} (todos son NaN)")
    # Usar valores originales con NaN para el gráfico
    raw_validos = presion_raw

# Crear gráfico con tres presiones
fig, (ax1, ax2, ax3) = plt.subplots(3, 1, figsize=(20, 16), sharex=True)

# GRÁFICO 1: PRESIÓN DE ZUNCHADO
ax1.scatter(timestamps, presion_zunchado, s=1, alpha=0.8, c='blue', label=f'Zunchado ({len(presion_zunchado)} puntos)')
ax1.plot(timestamps, presion_zunchado, 'b-', linewidth=0.3, alpha=0.6)

# Resaltar activos en zunchado
for i, (ts, valor) in enumerate(zip(timestamps, presion_zunchado)):
    if not np.isnan(valor) and valor > 0:
        ax1.scatter(ts, valor, s=2, color='red', alpha=0.9, zorder=5)

ax1.set_ylabel('Presión de Zunchado', fontsize=12)
ax1.set_title('PRESIÓN DE ZUNCHADO vs CIRCULACIÓN HIDRÁULICA vs RAW PRESIÓN\n17,280 puntos del 28/Jul/2025', fontsize=16, fontweight='bold')
ax1.grid(True, alpha=0.3)
ax1.legend()

# GRÁFICO 2: PRESIÓN CIRCULACIÓN HIDRÁULICA
ax2.scatter(timestamps, presion_hidraulica, s=1, alpha=0.8, c='green', label=f'Circulación Hidráulica ({len(presion_hidraulica)} puntos)')
ax2.plot(timestamps, presion_hidraulica, 'g-', linewidth=0.3, alpha=0.6)

# Resaltar valores altos en hidráulica
if len(hidraulica_validos) > 0:
    hidraulica_max = np.max(hidraulica_validos)
    umbral_alto = hidraulica_max * 0.8  # 80% del máximo
    for i, (ts, valor) in enumerate(zip(timestamps, presion_hidraulica)):
        if not np.isnan(valor) and valor > umbral_alto:
            ax2.scatter(ts, valor, s=2, color='orange', alpha=0.9, zorder=5)

ax2.set_ylabel('Presión Circulación Hidráulica', fontsize=12)
ax2.grid(True, alpha=0.3)
ax2.legend()

# GRÁFICO 3: RAW PRESIÓN
ax3.scatter(timestamps, presion_raw, s=1, alpha=0.8, c='purple', label=f'RAW Presión ({len(presion_raw)} puntos)')
ax3.plot(timestamps, presion_raw, color='purple', linewidth=0.3, alpha=0.6)

# Resaltar valores altos en RAW
raw_data_count = len(presion_raw[~np.isnan(presion_raw)])
if raw_data_count > 0:
    raw_max = np.nanmax(presion_raw)
    umbral_alto_raw = raw_max * 0.8  # 80% del máximo
    for i, (ts, valor) in enumerate(zip(timestamps, presion_raw)):
        if not np.isnan(valor) and valor > umbral_alto_raw:
            ax3.scatter(ts, valor, s=2, color='red', alpha=0.9, zorder=5)

ax3.set_ylabel('RAW Presión', fontsize=12)
ax3.set_xlabel('Fecha y Hora (28/Jul/2025)', fontsize=12)
ax3.grid(True, alpha=0.3)
ax3.legend()

# Formatear eje X
import matplotlib.dates as mdates
ax3.xaxis.set_major_formatter(mdates.DateFormatter('%H:%M'))
ax3.xaxis.set_major_locator(mdates.HourLocator(interval=2))
plt.xticks(rotation=45)

# Estadísticas combinadas
zunchado_validos = presion_zunchado[~np.isnan(presion_zunchado)]
zunchado_activos = sum(1 for v in zunchado_validos if v > 0)

stats_text = f"""ANÁLISIS TRES PRESIONES:
ZUNCHADO:
• Total: {len(presion_zunchado):,} puntos
• Activos: {zunchado_activos:,} ({zunchado_activos/len(zunchado_validos)*100:.1f}%)
• Rango: {np.nanmin(presion_zunchado):.3f} - {np.nanmax(presion_zunchado):.3f}

CIRCULACIÓN HIDRÁULICA:
• Total: {len(presion_hidraulica):,} puntos
• Válidos: {len(hidraulica_validos):,}
• Rango: {np.nanmin(presion_hidraulica):.3f} - {np.nanmax(presion_hidraulica):.3f}

RAW PRESIÓN:
• Total: {len(presion_raw):,} puntos
• Válidos: {len(presion_raw[~np.isnan(presion_raw)]):,}
• Rango: {np.nanmin(presion_raw) if not np.all(np.isnan(presion_raw)) else 'Sin datos'} - {np.nanmax(presion_raw) if not np.all(np.isnan(presion_raw)) else 'Sin datos'}"""

ax1.text(0.02, 0.98, stats_text, transform=ax1.transAxes, fontsize=10,
         verticalalignment='top', bbox=dict(boxstyle='round', facecolor='lightyellow', alpha=0.9))

plt.tight_layout()
plt.savefig('tres_presiones_zunchado_hidraulica_raw.png', dpi=200, bbox_inches='tight')
plt.close()

print(f"\n✅ Gráfico con 3 presiones guardado: tres_presiones_zunchado_hidraulica_raw.png")
print(f"✅ Zunchado - Puntos activos: {zunchado_activos:,}")
print(f"✅ Hidráulica - Puntos válidos: {len(hidraulica_validos):,}")
print(f"✅ RAW - Puntos válidos: {len(raw_validos):,}")
print(f"✅ Rango temporal: {timestamps[0]} a {timestamps[-1]}")
