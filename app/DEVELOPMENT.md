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

## Releases

Al publicar una release de un tag que incluya el workflow, GitHub Actions adjunta
`naw-trucador-windows.zip` y `thumbs_index.zip`. El ZIP de Windows sale de los
archivos del tag. El de miniaturas reutiliza el índice ya publicado en `v1.0.4`.
Para cambiar el índice de las próximas releases, subí uno actualizado a una
release y configurá `THUMBS_SOURCE_TAG` en **Settings → Secrets and variables →
Actions → Variables**. Si la release ya tiene alguno de los archivos, se conserva.
La subida posterior requiere que la release permita agregar archivos tras publicarse.
