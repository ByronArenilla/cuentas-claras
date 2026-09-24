import os

# La configuración se lee al importar `app`, así que el entorno de pruebas se
# fija antes de cualquier import de la app. Se sobrescribe a propósito: los
# tests nunca deben depender del `.env` local ni tocar una base de datos real.
os.environ["DATABASE_URL"] = "sqlite://"
os.environ["TZ"] = "America/Bogota"
