# naw-trucador

Herramienta de escritorio para Windows que permite explorar objetos de Mundo Gaturro, armar looks, preparar efectos y administrar lo que entrega Lola.

## Antes de instalar

Requisitos para usar el programa

- **Windows 10 u 11 de 64 bits.** Esta distribución no está preparada para macOS, Linux ni Windows de 32 bits.
- **Python se prepara automáticamente.** Si ya tenés Python 3.12, 3.13 o 3.14 x64 estándar, se reutiliza. Si el BAT solo encuentra una versión incompatible o no encuentra Python, descarga una copia privada en `.runtime/` y conserva tu instalación global.
- **Java 8 o superior** es obligatorio para instalar y abrir el programa. FFDec lo usa para modificar SWF. Se detecta desde `JAVA_HOME`, `PATH` o las carpetas de instalación habituales.
- **El cliente de escritorio de Mundo Gaturro**, instalado en esa PC, para aplicar las modificaciones dentro del juego.
- **Conexión a Internet** durante la instalación, para descargar recursos que falten y para jugar.

Para comprobar Java y listar las instalaciones de Python si ya tenés el lanzador `py`, abrí una terminal y ejecutá:

```bat
py -0p
java -version
```

Las librerías de Python y el motor de la ventana se instalan automáticamente. No hace falta instalar FFDec por separado: viene incluido.

## Instalar y abrir

1. Descargá este repositorio como ZIP y **extraelo completo**. No ejecutes los BAT desde dentro del ZIP.
2. Guardalo en una carpeta donde tu usuario pueda escribir, por ejemplo Documentos. Evitá `Archivos de programa`.
3. Ejecutá **`Instalar.bat`** y esperá el mensaje de instalación completada. La primera instalación puede tardar varios minutos.
4. Ejecutá **`Abrir naw.bat`** para abrir la aplicación.

Si abrís la aplicación antes de instalar, el iniciador hace la instalación primero. Si hay un error, el BAT muestra el motivo y termina con error; no informa éxito cuando falla una descarga o dependencia.

La instalación reutiliza el entorno Python y Electron en `.runtime/` si pasan las comprobaciones. Instala o repara cada componente por separado cuando hace falta. No instala los paquetes del proyecto en el Python global. La interfaz ya viene compilada.

## Primer uso

- Si en **Objetos** aparece el aviso de SWF faltantes, pulsá **Descargar faltantes** ahí mismo. La lista se actualiza al terminar. El ZIP trae un catálogo inicial y los archivos faltantes se descargan por separado.
- Las miniaturas se generan en segundo plano. En una instalación nueva, la búsqueda por imagen necesita que haya miniaturas disponibles y que termine de preparar su índice.
- En **Objetos**, abrir un SWF prioriza sus miniaturas pendientes. **Mejorar todas las miniaturas** recaptura las antiguas de todo el catálogo a hasta 120 píxeles. **Exportar** incluye las miniaturas ya guardadas y **Importar** conserva las que tengan mayor resolución.
- Los modelos de búsqueda visual y de eliminación de fondo se descargan al usar esas funciones. Si el modelo no está disponible, hay búsqueda clásica y eliminación de fondo de sprites como alternativas.
- Seleccioná objetos en **Objetos**. **Dar con Lola** pide cantidad y deja los objetos preparados. Las variantes con sufijo `_so` están excluidas de la selección y el envío normales.
- En **Lola** podés ver los preparados agrupados por SWF, desplegar su detalle, quitar un objeto, quitar un SWF o vaciar los preparados.
- En **Trucar** podés guardar looks y administrar efectos y cambios de clase.
- Para aplicarlo al juego, prepará la acción y pulsá **Abrir MG aplicado**. Entrá a un mundo y hablá con Lola.

Los NPCs que dependen de una misión o de otra sala se muestran para consulta. Los portales con destino explícito pueden preparar un salto directo; que el script esté preparado no confirma que el servidor permita el destino.

## Proxy y certificados

La herramienta usa un proxy local para reemplazar los recursos que recibe el cliente del juego. Al iniciarlo configura el proxy de Windows e instala el certificado de mitmproxy en el almacén de certificados de **tu usuario**. No copies certificados ni claves privadas desde otra PC.

Cerrá el juego y detení el proxy desde la aplicación al terminar. No ejecutes dos herramientas de proxy en el mismo puerto: naw avisa si el puerto está ocupado.

El inicio espera hasta 20 segundos al proceso del proxy. Si falla, tanto **Iniciar proxy** como **Abrir MG aplicado** muestran el motivo disponible y el código de salida, en lugar de un aviso genérico. En **Logs** queda la salida del proceso, incluso con nombres de usuario o carpetas con acentos.

El proxy escucha solo en `127.0.0.1`. Al detenerlo, al detectar que se cerró inesperadamente o al salir normalmente de la ventana, la aplicación intenta restaurar los valores de proxy de Windows que tenía antes de iniciarse. Si otra aplicación cambió el PAC mientras tanto, conserva ese cambio. Un cierre forzado de Windows o del Administrador de tareas puede impedir esta limpieza.

## Qué contiene esta distribución

En la raíz están los dos iniciadores y este README. El código, la interfaz compilada, los catálogos iniciales, Ruffle y FFDec están dentro de **`app/`**.

Se excluyen sesiones, rutas personales del juego, certificados, logs, trucos guardados, overrides, SWF descargados, miniaturas, modelos de IA, dependencias instaladas y carpetas de pruebas. Se crean en la PC de cada usuario según se necesiten.

**Para subirlo a otro GitHub:** usá esta carpeta `naw-trucador` como raíz del nuevo repositorio y subí también `app/`. El `.gitignore` excluye `.runtime/` y los datos generados. **No excluyas `app/frontend/dist/`**, porque contiene la interfaz lista para usar. Si volvés a compartirlo mediante un ZIP después de instalar, omití `.runtime/` y los datos locales generados en `app/data/`.

## Solución de problemas

- **Falló la descarga de Python local:** revisá la conexión o instalá manualmente [Python 3.12, 3.13 o 3.14 para Windows x64](https://www.python.org/downloads/windows/).
- **Java no encontrado:** configurá `JAVA_HOME` con tu instalación de Java 8 o superior, o agregá Java a `PATH`.
- **Falló la instalación:** revisá la conexión y volvé a ejecutar `Instalar.bat`. No hace falta borrar tus datos.
- **No encuentra Mundo Gaturro:** abrí el cliente del juego una vez y volvé a usar la herramienta. La ruta se detecta en esa PC; no se distribuye una ruta personal.
- **No aparecen objetos o miniaturas:** descargá los packs faltantes en Archivos y dejá completar el índice.
- **Actualizaste desde un ZIP:** extraé los archivos nuevos sobre tu carpeta existente si querés conservar el entorno y los datos locales. Una carpeta nueva prepara su propio entorno.
- **Puerto web ocupado:** el iniciador busca un puerto local libre entre 5500 y 5519. El proxy del juego usa 8080.
- **El proxy no inicia:** copiá el error completo y las líneas `[mitm-err]` / `[mitm-out]` de Logs. Un error de dependencia indica ejecutar `Instalar.bat` en esa misma carpeta; un puerto ocupado requiere cerrar la otra aplicación que lo usa. No hace falta borrar tus datos ni certificados para diagnosticarlo.

Para modificar y recompilar la interfaz, consultá [la guía de desarrollo](app/DEVELOPMENT.md). Los componentes incluidos y sus avisos están en [THIRD_PARTY.md](app/THIRD_PARTY.md).
