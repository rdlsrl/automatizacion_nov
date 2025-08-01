import matplotlib
matplotlib.use('Agg')  # Usar backend sin GUI
import matplotlib.pyplot as plt
import lasio
import numpy as np
import pandas as pd
from datetime import datetime

# Leer datos
las = lasio.read('/mnt/mariadb/autom_nov/data/las/activos/SAI-225_PO-_825_29-07-2025_16-20_3.las')
presion = las['PRESION_DE_ZUNCHADO']
fechas = las['DATE:1']
horas = las['DATE:2']

print(f"Creando gráfico con {len(presion)} puntos...")

# Crear timestamps
timestamps = []
for i, (f, h) in enumerate(zip(fechas, horas)):
    try:
        fecha_dt = datetime.strptime(str(f), "%d/%b/%Y")
        hora_dt = datetime.strptime(str(h), "%H:%M:%S").time()
        timestamps.append(datetime.combine(fecha_dt.date(), hora_dt))
    except:
        timestamps.append(datetime(2025, 7, 28, 0, 0, 0) + pd.Timedelta(seconds=i*5))

# Crear gráfico grande
fig, ax = plt.subplots(figsize=(20, 12))

# Plotear TODOS los puntos - sin filtros
ax.plot(timestamps, presion, 'b-', linewidth=0.8, alpha=0.8)
ax.scatter(timestamps, presion, s=0.5, c='blue', alpha=0.6)

# Configurar gráfico
ax.set_title(f'PRESION DE ZUNCHADO - TODOS LOS {len(presion)} PUNTOS\n28 Julio 2025', 
             fontsize=16, fontweight='bold')
ax.set_xlabel('Hora del día', fontsize=14)
ax.set_ylabel('Presión', fontsize=14)
ax.grid(True, alpha=0.3)

# Formatear eje X cada 2 horas
import matplotlib.dates as mdates
ax.xaxis.set_major_formatter(mdates.DateFormatter('%H:%M'))
ax.xaxis.set_major_locator(mdates.HourLocator(interval=2))
plt.xticks(rotation=45)

# Estadísticas
valid_data = presion[~np.isnan(presion)]
stats = f"""DATOS COMPLETOS:
Total: {len(presion):,} puntos
Válidos: {len(valid_data):,}
NaN: {len(presion) - len(valid_data):,}
Min: {np.nanmin(presion):.3f}
Max: {np.nanmax(presion):.3f}"""

ax.text(0.02, 0.98, stats, transform=ax.transAxes, fontsize=12,
        verticalalignment='top', bbox=dict(boxstyle='round', facecolor='yellow', alpha=0.8))

plt.tight_layout()
plt.savefig('grafico_completo_zunchado.png', dpi=150, bbox_inches='tight')
print("Gráfico guardado como: grafico_completo_zunchado.png")
plt.close()

# También crear una imagen de prueba simple
fig2, ax2 = plt.subplots(figsize=(10, 6))
ax2.plot(range(100), presion[:100], 'ro-', markersize=3)
ax2.set_title('TEST - Primeros 100 puntos de presión')
ax2.grid(True)
plt.savefig('test_primeros_100.png', dpi=100)
print("Test guardado como: test_primeros_100.png")
plt.close()
