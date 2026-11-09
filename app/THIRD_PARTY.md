# Componentes externos

- **FFDec / JPEXS Free Flash Decompiler**: `ffdec/ffdec.jar`, bibliotecas en `ffdec/lib/`. Proyecto y fuentes: https://github.com/jindrapetrik/jpexs-decompiler. Se conservan los archivos de licencia incluidos con las bibliotecas.
- **Ruffle**: `static/ruffle/ruffle.js`, módulos JavaScript y WebAssembly. Proyecto y fuentes: https://github.com/ruffle-rs/ruffle. Licencias MIT / Apache-2.0, incluidas en `licenses/`.
- **Electron**: se descarga al instalar, desde https://github.com/electron/electron/releases. El instalador verifica el SHA-256 oficial. La descarga conserva sus avisos y licencias.
- **playerglobal32_0.swc**: definiciones de la API de Flash usadas por el compilador; no es el reproductor Flash.
- **Recursos del juego**: los SWF de vista previa contienen recursos necesarios para visualizar al personaje. Los recursos y marcas de Mundo Gaturro pertenecen a sus titulares; no se declara propiedad sobre ellos.
- **Python y Java**: se instalan por separado. Los paquetes Python conservan sus licencias en el entorno local.
- Los modelos CLIP y RMBG se obtienen desde sus repositorios al usarlos, bajo sus respectivas condiciones: https://huggingface.co/Xenova/clip-vit-base-patch32 y https://huggingface.co/briaai/RMBG-1.4.

Este archivo no cambia las licencias de los componentes externos ni les asigna la licencia del código de la aplicación.
