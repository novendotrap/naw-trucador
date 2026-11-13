# Desarrollo

La aplicación se distribuye con `frontend/dist` compilado. Para usarla, seguí el README de la raíz.

Solo para modificar el frontend se necesitan Node.js y npm:

```bat
npm --prefix app/frontend ci
npm --prefix app/frontend run build
```

Después de compilar, incluí los cambios de `app/frontend/dist` en el commit. No subas `node_modules`.

`app/bootstrap.py` administra el entorno privado de Python y descarga la distribución oficial de Electron, fijada a una versión y un SHA-256. `desktop/main.cjs` inicia Flask con ese Python y verifica que el backend corresponda a esta copia del proyecto.

El helper Java incluye el `.class` y el `.java`. No se necesita `javac` para el uso normal; solamente para modificar/recompilar ese helper. Compilalo con `javac --release 8` para que el binario siga funcionando con Java 8.

Los datos persistentes están en `app/data/`; los runtimes instalados y el perfil de Electron, en `.runtime/`. No publiques esos datos de usuario.

## Comprobar el proxy

Desde la raíz del repositorio, en Windows:

```bat
.runtime\python\Scripts\python.exe -m unittest discover -s app/tests -p "test_proxy*.py" -v
node --test app/tests/test_proxy_shutdown.cjs
```

Las pruebas Python usan puertos loopback y datos temporales, incluyendo rutas con espacios y caracteres Unicode. Simulan cambios del registro, fallos y procesos lentos; también ejecutan mitmproxy real para pasar HTTP a un servidor local. No instalan certificados en Windows, no modifican el proxy del sistema ni abren el juego. La prueba real genera su certificado únicamente dentro de su carpeta temporal.

Las pruebas API comprueban que el detalle llega a ambos botones y que un arranque fallido no abre ni cierra el juego. La prueba Node comprueba la petición de limpieza al backend y sus límites ante desconexión o falta de respuesta. Node se necesita para desarrollo y estas pruebas, no para usar la aplicación.

## Releases

Al publicar una release de un tag que incluya el workflow, GitHub Actions adjunta
`naw-trucador-windows.zip` y `thumbs_index.zip`. El ZIP de Windows sale de los
archivos del tag. El de miniaturas reutiliza el índice ya publicado en `v1.0.4`.
Para cambiar el índice de las próximas releases, subí uno actualizado a una
release y configurá `THUMBS_SOURCE_TAG` en **Settings → Secrets and variables →
Actions → Variables**. Si la release ya tiene alguno de los archivos, se conserva.
La subida posterior requiere que la release permita agregar archivos tras publicarse.
