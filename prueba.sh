#!/bin/bash

# Definir la carpeta donde están los archivos CSV
csv_folder="/mnt/mariadb/mariadb_csv_rigs"
# Buscar el archivo CSV más reciente en la carpeta
latest_file=$(ls -t $csv_folder/WELL_PAE_*.csv | head -n 1)

# Verificar si encontramos el archivo más reciente
if [ -z "$latest_file" ]; then
  echo "No se encontró ningún archivo CSV en la carpeta."
  exit 1
fi

# Mostrar el nombre del archivo que estamos procesando
echo "Procesando el archivo: $latest_file"

# Variables de conexión a MariaDB
DB_USER="root"
DB_PASS="Partediario20"
DB_NAME="rdl_import"

# Crear una tabla temporal para visualizar los datos antes de insertarlos
mysql -u $DB_USER -p$DB_PASS $DB_NAME -e "
  CREATE TEMPORARY TABLE temp_well_data (
    operator VARCHAR(255),
    well_name VARCHAR(255),
    contractor VARCHAR(255),
    rig VARCHAR(255),
    spud_date DATE,
    latest_edr DATETIME,
    total_depth DECIMAL(10, 2),
    import_datetime DATETIME
  );
"

# Cargar los datos del CSV a la tabla temporal sin insertarlos en la tabla original
mysql -u $DB_USER -p$DB_PASS $DB_NAME -e "
  LOAD DATA LOCAL INFILE '$latest_file'
  INTO TABLE temp_well_data
  FIELDS TERMINATED BY ',' ENCLOSED BY '\"'
  LINES TERMINATED BY '\n'
  IGNORE 1 ROWS
  (@operator, @well_name, @contractor, @rig, @spud_date, @latest_edr, @total_depth)
  SET 
    operator = @operator,
    well_name = @well_name,
    contractor = @contractor,
    rig = @rig,
    spud_date = STR_TO_DATE(@spud_date, '%d-%b-%y'),
    latest_edr = CASE 
        WHEN @latest_edr REGEXP '^[0-9]{2}:[0-9]{2}$' 
        THEN STR_TO_DATE(CONCAT(CURDATE(), ' ', @latest_edr), '%Y-%m-%d %H:%i')
        ELSE STR_TO_DATE(@latest_edr, '%d-%b-%y')
    END,
    total_depth = CAST(@total_depth AS DECIMAL(10,2)), 
    import_datetime = CURRENT_TIMESTAMP;
"

# Visualizar los datos cargados en la tabla temporal (no insertados en la tabla original)
mysql -u $DB_USER -p$DB_PASS $DB_NAME -e "
  SELECT * FROM temp_well_data;
"

# Eliminar la tabla temporal después de la visualización
mysql -u $DB_USER -p$DB_PASS $DB_NAME -e "
  DROP TEMPORARY TABLE IF EXISTS temp_well_data;
"

# Fin del script
echo "Visualización completa de los datos cargados desde $latest_file."
