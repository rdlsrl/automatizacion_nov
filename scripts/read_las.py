#!/usr/bin/env python3
import lasio
import json
import sys
import numpy as np
import argparse
from datetime import datetime

class NumpyEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, (np.integer,)):
            return int(obj)
        elif isinstance(obj, (np.floating,)):
            return float(obj)
        elif isinstance(obj, np.ndarray):
            return obj.tolist()
        return super(NumpyEncoder, self).default(obj)

def safe_convert(x):
    # Convierte el valor a string para poder analizarlo
    s = str(x).strip()  # Elimina espacios en blanco
    # Si contiene "/" o es una fecha, se trata como texto
    if "/" in s or ":" in s or "-" in s:
        try:
            # Intenta parsear la fecha (opcional)
            datetime.strptime(s, "%d/%b/%Y")  # Formato de fecha esperado
            return s  # Devuelve la fecha como texto
        except ValueError:
            return s  # Si no es una fecha válida, devuelve el texto tal cual
    try:
        f = float(x)
        if np.isnan(f):
            return -999.25  # Valor por defecto para NaN
        else:
            return f
    except Exception:
        return s

def main():
    # Configura el parser de argumentos
    parser = argparse.ArgumentParser(description="Procesa un archivo LAS y lo convierte a JSON.")
    parser.add_argument("input_file", help="Ruta al archivo LAS de entrada.")
    parser.add_argument("--output", "-o", default="output.json", help="Ruta al archivo JSON de salida.")
    args = parser.parse_args()

    # Validación del archivo de entrada
    if not args.input_file.endswith(".las"):
        print("Error: El archivo de entrada debe tener extensión .las", file=sys.stderr)
        sys.exit(1)

    print(f"Iniciando procesamiento de {args.input_file}...", file=sys.stderr)

    # Lectura del archivo LAS
    try:
        las = lasio.read(args.input_file)
        print("Archivo leído correctamente.", file=sys.stderr)
    except Exception as e:
        print(json.dumps({"error": str(e)}))
        sys.exit(1)

    # Conversión segura de los datos
    try:
        data_fixed = np.vectorize(safe_convert)(las.data)
    except Exception as e:
        print(json.dumps({"error": "Error al convertir datos: " + str(e)}))
        sys.exit(1)

    # Estructura del resultado
    result = {
        "version": [
            {"mnemonic": item.mnemonic, "value": item.value, "descr": item.descr}
            for item in las.version
        ],
        "well": [
            {"mnemonic": item.mnemonic, "value": item.value, "descr": item.descr}
            for item in las.well
        ],
        "curve": [
            {"mnemonic": c.mnemonic, "unit": c.unit, "descr": c.descr}
            for c in las.curves
        ],
        "data": data_fixed.tolist()
    }

    print("Procesamiento completado, generando JSON...", file=sys.stderr)

    # Convertir a JSON
    json_output = json.dumps(result, indent=2, cls=NumpyEncoder)
    print(json_output)

    # Guardar el archivo JSON
    try:
        with open(args.output, "w") as f:
            f.write(json_output)
        print(f"Archivo {args.output} guardado exitosamente.", file=sys.stderr)
    except Exception as e:
        print("Error al guardar el archivo:", str(e), file=sys.stderr)

if __name__ == '__main__':
    main()
