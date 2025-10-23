#!/bin/bash
# Script para automatizar la descarga completa de datos de pozos
# Usar con cron: 0 */6 * * * /ruta/to/automatizar_descarga_completa.sh

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
LOG_FILE="$PROJECT_ROOT/logs/automatizacion_$(date +%Y%m%d_%H%M%S).log"

# Crear directorio de logs si no existe
mkdir -p "$PROJECT_ROOT/logs"

echo "=== INICIANDO AUTOMATIZACIÓN COMPLETA $(date) ===" | tee -a "$LOG_FILE"

# 0. Sincronizar datos desde rdl_import
echo "0. Sincronizando datos desde rdl_import..." | tee -a "$LOG_FILE"
cd "$SCRIPT_DIR"
python3 sync_datos_simple.py 2>&1 | tee -a "$LOG_FILE"
SYNC_EXIT_CODE=$?

if [ $SYNC_EXIT_CODE -eq 0 ]; then
    echo "✅ Sincronización de datos exitosa" | tee -a "$LOG_FILE"
else
    echo "⚠️ Sincronización completada con advertencias (código: $SYNC_EXIT_CODE)" | tee -a "$LOG_FILE"
    echo "⚠️ Continuando con el resto del proceso..." | tee -a "$LOG_FILE"
fi

# 1. Actualizar datos de WellData (load_well_data.py)
echo "1. Actualizando datos de WellData..." | tee -a "$LOG_FILE"
cd "$SCRIPT_DIR"
python3 load_well_data.py --log-level INFO 2>&1 | tee -a "$LOG_FILE"
LOAD_EXIT_CODE=$?

if [ $LOAD_EXIT_CODE -eq 0 ]; then
    echo "✅ Actualización de WellData exitosa" | tee -a "$LOG_FILE"
    
    # 2. Procesar rigs (descarga de LAS)
    echo "2. Procesando rigs para descarga de LAS..." | tee -a "$LOG_FILE"
    python3 procesar_rig.py 2>&1 | tee -a "$LOG_FILE"
    PROCESAR_EXIT_CODE=$?
    
    if [ $PROCESAR_EXIT_CODE -eq 0 ]; then
        echo "✅ Procesamiento de rigs completado exitosamente" | tee -a "$LOG_FILE"
        
        # 3. Procesar datos históricos (secuencia completa)
        echo "3. Procesando datos históricos..." | tee -a "$LOG_FILE"
        
        # 3.1. Procesar fechas históricas
        echo "3.1. Ejecutando fechas_history.py..." | tee -a "$LOG_FILE"
        python3 fechas_history.py 2>&1 | tee -a "$LOG_FILE"
        FECHAS_EXIT_CODE=$?
        
        if [ $FECHAS_EXIT_CODE -eq 0 ]; then
            echo "✅ fechas_history.py completado exitosamente" | tee -a "$LOG_FILE"
            
            # 3.2. Procesar bucle histórico
            echo "3.2. Ejecutando hist_bucle.py..." | tee -a "$LOG_FILE"
            python3 hist_bucle.py 2>&1 | tee -a "$LOG_FILE"
            BUCLE_EXIT_CODE=$?
            
            if [ $BUCLE_EXIT_CODE -eq 0 ]; then
                echo "✅ hist_bucle.py completado exitosamente" | tee -a "$LOG_FILE"
                
                # 3.3. Descargar archivos históricos
                echo "3.3. Ejecutando download_las_historic.py..." | tee -a "$LOG_FILE"
                python3 download_las_historic.py 2>&1 | tee -a "$LOG_FILE"
                DOWNLOAD_EXIT_CODE=$?
                
                if [ $DOWNLOAD_EXIT_CODE -eq 0 ]; then
                    echo "✅ Secuencia completa de históricos completada exitosamente" | tee -a "$LOG_FILE"
                else
                    echo "⚠️ download_las_historic.py completado con advertencias (código: $DOWNLOAD_EXIT_CODE)" | tee -a "$LOG_FILE"
                fi
            else
                echo "⚠️ hist_bucle.py completado con advertencias (código: $BUCLE_EXIT_CODE)" | tee -a "$LOG_FILE"
                echo "⚠️ Saltando download_las_historic.py debido a errores en hist_bucle.py" | tee -a "$LOG_FILE"
            fi
        else
            echo "⚠️ fechas_history.py completado con advertencias (código: $FECHAS_EXIT_CODE)" | tee -a "$LOG_FILE"
            echo "⚠️ Saltando resto de secuencia histórica debido a errores en fechas_history.py" | tee -a "$LOG_FILE"
        fi
    else
        echo "⚠️ Procesamiento de rigs completado con advertencias (código: $PROCESAR_EXIT_CODE)" | tee -a "$LOG_FILE"
        
        # Ejecutar históricos incluso si hay advertencias en rigs
        echo "3. Procesando datos históricos (tras advertencias en rigs)..." | tee -a "$LOG_FILE"
        
        # 3.1. Procesar fechas históricas
        echo "3.1. Ejecutando fechas_history.py..." | tee -a "$LOG_FILE"
        python3 fechas_history.py 2>&1 | tee -a "$LOG_FILE"
        FECHAS_EXIT_CODE=$?
        
        if [ $FECHAS_EXIT_CODE -eq 0 ]; then
            echo "✅ fechas_history.py completado exitosamente" | tee -a "$LOG_FILE"
            
            # 3.2. Procesar bucle histórico
            echo "3.2. Ejecutando hist_bucle.py..." | tee -a "$LOG_FILE"
            python3 hist_bucle.py 2>&1 | tee -a "$LOG_FILE"
            BUCLE_EXIT_CODE=$?
            
            if [ $BUCLE_EXIT_CODE -eq 0 ]; then
                echo "✅ hist_bucle.py completado exitosamente" | tee -a "$LOG_FILE"
                
                # 3.3. Descargar archivos históricos
                echo "3.3. Ejecutando download_las_historic.py..." | tee -a "$LOG_FILE"
                python3 download_las_historic.py 2>&1 | tee -a "$LOG_FILE"
                DOWNLOAD_EXIT_CODE=$?
                
                if [ $DOWNLOAD_EXIT_CODE -eq 0 ]; then
                    echo "✅ Secuencia completa de históricos completada exitosamente" | tee -a "$LOG_FILE"
                else
                    echo "⚠️ download_las_historic.py completado con advertencias (código: $DOWNLOAD_EXIT_CODE)" | tee -a "$LOG_FILE"
                fi
            else
                echo "⚠️ hist_bucle.py completado con advertencias (código: $BUCLE_EXIT_CODE)" | tee -a "$LOG_FILE"
                echo "⚠️ Saltando download_las_historic.py debido a errores en hist_bucle.py" | tee -a "$LOG_FILE"
            fi
        else
            echo "⚠️ fechas_history.py completado con advertencias (código: $FECHAS_EXIT_CODE)" | tee -a "$LOG_FILE"
            echo "⚠️ Saltando resto de secuencia histórica debido a errores en fechas_history.py" | tee -a "$LOG_FILE"
        fi
    fi
else
    echo "❌ Error en actualización de WellData (código: $LOAD_EXIT_CODE). Abortando procesamiento." | tee -a "$LOG_FILE"
    exit $LOAD_EXIT_CODE
fi

echo "=== AUTOMATIZACIÓN FINALIZADA $(date) ===" | tee -a "$LOG_FILE"
echo "Log completo en: $LOG_FILE"