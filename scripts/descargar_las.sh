#!/bin/bash

# Cambiar al directorio donde están los scripts
cd /mnt/mariadb/autom_nov || { echo "No se pudo cambiar al directorio /mnt/mariadb/autom_nov/scripts"; exit 1; }

# Archivo de log para almacenar el tiempo de ejecución
LOG_FILE="/mnt/mariadb/autom_nov/tiempos_ejecucion.csv"

# Crear el archivo CSV si no existe
if [ ! -f "$LOG_FILE" ]; then
    echo "fecha_ejecucion,script,tiempo_segundos" > "$LOG_FILE"
fi

# Función para medir el tiempo y guardar en CSV
medir_tiempo() {
    local script=$1
    local inicio=$(date +%s)  # Obtener la fecha/hora de inicio en segundos

    # Ejecutar el script usando el intérprete del entorno virtual
    echo "Ejecutando $script..."
    /mnt/mariadb/autom_nov/venv/bin/python "$script"  # Mostrar la salida en la consola

    local fin=$(date +%s)  # Obtener la fecha/hora de finalización en segundos
    local tiempo_total=$((fin - inicio))  # Calcular el tiempo total en segundos

    # Guardar los tiempos en el archivo CSV
    echo "$(date '+%Y-%m-%d %H:%M:%S'),$script,$tiempo_total" >> "$LOG_FILE"
    echo "$script completado en $tiempo_total segundos."
}

# Medir el tiempo de ejecución de cada script
echo "=========================================="
echo "Inicio de la ejecución: $(date)"
for script in "load_well_data.py" "procesar_rig.py" "hist_bucle.py" "download_las_historic.py"; do
    if [ -f "$script" ]; then
        medir_tiempo "$script"
    else
        echo "Error: El script $script no existe."
    fi
done
echo "Fin de la ejecución: $(date)"
echo "=========================================="
