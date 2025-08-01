import lasio
import sys
import os # Necesario para os.path.exists y os.path.isfile

def test_lasio_mnemonics(filepath: str):
    print(f"--- Probando archivo LAS: {filepath} ---")
    try:
        # Intentar leer con algunos encodings comunes, empezando por utf-8
        las_file = None
        encodings_to_try = ['utf-8-sig', 'utf-8', 'cp1252', 'latin-1']
        for enc in encodings_to_try:
            try:
                print(f"Intentando leer con encoding: {enc}...")
                las_file = lasio.read(filepath, encoding=enc)
                print(f"Archivo leído exitosamente con encoding: {enc}")
                break 
            except Exception as e_enc:
                print(f"  Fallo al leer con {enc}: {e_enc}")
        
        if not las_file:
            print("No se pudo leer el archivo LAS con los encodings probados. Intentando autodetect de lasio...")
            las_file = lasio.read(filepath) # Fallback a autodetect de lasio
            print(f"Archivo leído con autodetect de lasio (encoding detectado: {las_file.encoding})")

        print(f"\nArchivo leído. {len(las_file.curves)} curvas encontradas.")
        print("Formato de los mnemónicos según lasio (curva.mnemonic):")
        print("------------------------------------------------------")
        for i, curva in enumerate(las_file.curves):
            # Imprimimos el mnemónico tal cual lo da lasio, y su representación para ver caracteres ocultos
            print(f"  Curva #{i+1:03d}: Mnemónico='{curva.mnemonic}' "
                  f"(repr: {repr(curva.mnemonic)}), "
                  f"Unidad='{curva.unit}', "
                  f"Descripción='{curva.descr[:40]}...'")
        
        print("------------------------------------------------------")

    except Exception as e:
        print(f"Error al leer o procesar el archivo LAS '{filepath}': {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    if len(sys.argv) > 1:
        las_filepath_arg = sys.argv[1]
        if os.path.exists(las_filepath_arg) and os.path.isfile(las_filepath_arg):
            test_lasio_mnemonics(las_filepath_arg)
        else:
            print(f"Error: Archivo no encontrado en la ruta proporcionada por argumento: {las_filepath_arg}")
    else:
        # Pídele al usuario que reemplace esto con la ruta a su archivo LAS de prueba
        # Por ejemplo, el que estabas usando:
        default_ruta_prueba = "/mnt/mariadb/autom_nov/data/las/activos/SAI-225_PLMS-_804_27-05-2025_11-16_4.las"
        
        print("No se especificó un archivo LAS como argumento.")
        ruta_ingresada = input(f"Por favor, ingresa la ruta completa a tu archivo LAS de prueba (o presiona Enter para usar '{default_ruta_prueba}'): ")
        
        if not ruta_ingresada.strip(): # Si el usuario presiona Enter sin escribir nada
            las_filepath_input = default_ruta_prueba
            print(f"Usando ruta por defecto: {las_filepath_input}")
        else:
            las_filepath_input = ruta_ingresada

        if os.path.exists(las_filepath_input) and os.path.isfile(las_filepath_input):
            test_lasio_mnemonics(las_filepath_input)
        else:
            print(f"Error: Archivo no encontrado en la ruta: {las_filepath_input}")
            print("Por favor, ejecuta el script de nuevo y proporciona una ruta válida.")