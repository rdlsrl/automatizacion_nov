#!/usr/bin/env python3
"""
Análisis avanzado de curvas LAS - Detección de patrones y eventos
"""
import lasio
import numpy as np
from pathlib import Path

def analizar_curva_inteligente(archivo_las):
    """Análisis inteligente de PRESION_DE_ZUNCHADO usando técnicas avanzadas"""
    print(f"\n{'='*60}")
    print(f"📂 ARCHIVO: {Path(archivo_las).name}")
    print(f"{'='*60}")
    
    try:
        las = lasio.read(archivo_las, ignore_header_errors=True)
        
        if 'PRESION_DE_ZUNCHADO' not in [c.mnemonic for c in las.curves]:
            print("❌ No tiene PRESION_DE_ZUNCHADO")
            return
            
        # Obtener datos
        presion = las['PRESION_DE_ZUNCHADO']
        depth = las['DEPTH']
        
        # Limpiar datos
        mask_validos = ~np.isnan(presion) & ~np.isnan(depth)
        presion_limpia = presion[mask_validos]
        depth_limpia = depth[mask_validos]
        
        if len(presion_limpia) < 100:
            print("❌ Pocos datos válidos")
            return
            
        print(f"🔍 ANÁLISIS INTELIGENTE DE PATRONES:")
        print(f"  🏷️  Unidad: {las.curves['PRESION_DE_ZUNCHADO'].unit}")
        print(f"  📊 Puntos válidos: {len(presion_limpia):,}")
        
        # 1. ANÁLISIS DE DISTRIBUCIÓN
        print(f"\n📊 DISTRIBUCIÓN DE VALORES:")
        percentiles = np.percentile(presion_limpia, [1, 5, 25, 50, 75, 95, 99])
        print(f"  📈 P1: {percentiles[0]:.1f} | P5: {percentiles[1]:.1f} | P25: {percentiles[2]:.1f}")
        print(f"  📈 P50: {percentiles[3]:.1f} | P75: {percentiles[4]:.1f} | P95: {percentiles[5]:.1f} | P99: {percentiles[6]:.1f}")
        
        # 2. DETECCIÓN DE EVENTOS (cambios bruscos)
        print(f"\n🔍 DETECCIÓN DE EVENTOS:")
        
        # Calcular gradiente (derivada)
        gradiente = np.gradient(presion_limpia)
        gradiente_abs = np.abs(gradiente)
        
        # Detectar picos en el gradiente (cambios bruscos) - método manual
        umbral_cambio = np.percentile(gradiente_abs, 95)  # Top 5% de cambios
        
        # Encontrar eventos (picos) manualmente
        eventos = []
        for i in range(1, len(gradiente_abs)-1):
            if (gradiente_abs[i] > umbral_cambio and 
                gradiente_abs[i] > gradiente_abs[i-1] and 
                gradiente_abs[i] > gradiente_abs[i+1]):
                # Evitar eventos muy cercanos
                if not eventos or i - eventos[-1] > 50:
                    eventos.append(i)
        
        eventos = np.array(eventos)
        
        print(f"  🎯 Eventos detectados: {len(eventos)}")
        print(f"  🎯 Umbral de cambio: {umbral_cambio:.2f}")
        
        if len(eventos) > 0:
            print(f"  📍 Profundidades de eventos: {depth_limpia[eventos][:10]} ...")
            print(f"  📈 Valores en eventos: {presion_limpia[eventos][:10]} ...")
            
        # 3. ANÁLISIS DE REGÍMENES (clustering)
        print(f"\n🔄 ANÁLISIS DE REGÍMENES:")
        
        # Detectar valores "base" vs "activos"
        mediana = np.median(presion_limpia)
        q1 = np.percentile(presion_limpia, 25)
        q3 = np.percentile(presion_limpia, 75)
        iqr = q3 - q1
        
        # Definir regímenes
        regime_bajo = presion_limpia < (q1 - 0.5*iqr)  # Valores muy bajos
        regime_normal = (presion_limpia >= (q1 - 0.5*iqr)) & (presion_limpia <= (q3 + 0.5*iqr))
        regime_alto = presion_limpia > (q3 + 0.5*iqr)  # Valores altos
        
        print(f"  🔵 Régimen BAJO (<{q1 - 0.5*iqr:.1f}): {np.sum(regime_bajo):,} puntos ({100*np.sum(regime_bajo)/len(presion_limpia):.1f}%)")
        print(f"  🟡 Régimen NORMAL: {np.sum(regime_normal):,} puntos ({100*np.sum(regime_normal)/len(presion_limpia):.1f}%)")
        print(f"  🔴 Régimen ALTO (>{q3 + 0.5*iqr:.1f}): {np.sum(regime_alto):,} puntos ({100*np.sum(regime_alto)/len(presion_limpia):.1f}%)")
        
        # 4. ANÁLISIS DE CORRELACIÓN CON PROFUNDIDAD
        print(f"\n📏 CORRELACIÓN CON PROFUNDIDAD:")
        correlacion = np.corrcoef(depth_limpia, presion_limpia)[0,1]
        print(f"  📊 Correlación depth-presión: {correlacion:.3f}")
        
        if abs(correlacion) > 0.3:
            print(f"  ⚠️  Correlación significativa - Posible tendencia con profundidad")
        else:
            print(f"  ✅ Baja correlación - Independiente de profundidad")
            
        # 5. DETECCIÓN DE SEGMENTOS CONSTANTES
        print(f"\n📏 ANÁLISIS DE SEGMENTOS:")
        
        # Detectar segmentos donde el valor es casi constante
        ventana = 100  # puntos de ventana
        if len(presion_limpia) > ventana:
            varianza_movil = np.array([np.var(presion_limpia[i:i+ventana]) 
                                     for i in range(0, len(presion_limpia)-ventana, ventana//2)])
            
            segmentos_constantes = np.sum(varianza_movil < 1.0)  # Varianza muy baja
            print(f"  📊 Segmentos analizados: {len(varianza_movil)}")
            print(f"  📊 Segmentos constantes: {segmentos_constantes} ({100*segmentos_constantes/len(varianza_movil):.1f}%)")
            
        # 6. DETECCIÓN DE OUTLIERS
        print(f"\n🎯 DETECCIÓN DE OUTLIERS:")
        
        # Método IQR
        outliers_iqr = (presion_limpia < (q1 - 1.5*iqr)) | (presion_limpia > (q3 + 1.5*iqr))
        
        # Método Z-score
        z_scores = np.abs((presion_limpia - np.mean(presion_limpia)) / np.std(presion_limpia))
        outliers_z = z_scores > 3
        
        print(f"  📊 Outliers (IQR): {np.sum(outliers_iqr):,} ({100*np.sum(outliers_iqr)/len(presion_limpia):.1f}%)")
        print(f"  📊 Outliers (Z-score): {np.sum(outliers_z):,} ({100*np.sum(outliers_z)/len(presion_limpia):.1f}%)")
        
        if np.sum(outliers_iqr) > 0:
            outlier_values = presion_limpia[outliers_iqr]
            print(f"  🔢 Valores outliers: {np.sort(outlier_values)[-10:]} ...")
            
        # 7. ANÁLISIS DE FRECUENCIA (FFT)
        print(f"\n🌊 ANÁLISIS DE FRECUENCIA:")
        
        # Aplicar FFT para detectar periodicidades
        fft = np.fft.fft(presion_limpia - np.mean(presion_limpia))
        freqs = np.fft.fftfreq(len(presion_limpia))
        power = np.abs(fft)**2
        
        # Encontrar frecuencias dominantes
        idx_max = np.argsort(power)[-5:]  # Top 5 frecuencias
        print(f"  📊 Frecuencias dominantes: {freqs[idx_max][::-1]}")
        
        # 8. CONCLUSIONES INTELIGENTES
        print(f"\n🎯 CONCLUSIONES INTELIGENTES:")
        
        # Determinar tipo de señal
        cv = np.std(presion_limpia) / np.mean(presion_limpia)  # Coeficiente de variación
        print(f"  📊 Coeficiente de variación: {cv:.3f}")
        
        if cv < 0.1:
            print(f"  ✅ SEÑAL ESTABLE - Poca variabilidad")
        elif cv > 0.5:
            print(f"  ⚠️  SEÑAL VARIABLE - Alta variabilidad")
        else:
            print(f"  🟡 SEÑAL MODERADA - Variabilidad normal")
            
        # Análisis de unidad basado en comportamiento
        if np.sum(regime_bajo) > 0.7 * len(presion_limpia):
            print(f"  ✅ COMPORTAMIENTO TÍPICO de presión de zunchado (mayoría valores bajos)")
        elif correlacion > 0.5:
            print(f"  ⚠️  POSIBLE CONFUSIÓN con otra variable (correlación con depth)")
        elif len(eventos) > len(presion_limpia) // 1000:
            print(f"  ✅ EVENTOS DETECTADOS - Comportamiento esperado en conexiones")
        else:
            print(f"  ❓ COMPORTAMIENTO ATÍPICO - Revisar manualmente")
            
    except Exception as e:
        print(f"❌ ERROR: {e}")

if __name__ == "__main__":
    archivos = [
        "/mnt/mariadb/autom_nov/data/las/activos/DLS-083_PE-_1070_29-07-2025_16-09_2.las",
        "/mnt/mariadb/autom_nov/data/las/activos/DLS-075_PJ-_865_i_29-07-2025_16-06_2.las"
    ]
    
    print("🧠 ANÁLISIS INTELIGENTE DE CURVAS LAS")
    print("=" * 80)
    
    for archivo in archivos:
        if Path(archivo).exists():
            analizar_curva_inteligente(archivo)
        else:
            print(f"❌ Archivo no encontrado: {archivo}")
    
    print(f"\n{'='*80}")
    print("✅ ANÁLISIS COMPLETADO")
