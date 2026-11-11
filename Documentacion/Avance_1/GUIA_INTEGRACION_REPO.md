# Cómo incorporar este paquete al repositorio FleetLogix

El contenido se diseñó como **carpeta complementaria del Avance #2**. No modifica por sí solo el repositorio remoto.

## Opción conservadora (recomendada)

1. Descomprimir `FleetLogix_Avance2_Repo.zip`.
2. Copiar la carpeta completa `FleetLogix_Avance2_Repo/` dentro de la raíz de tu repositorio existente. Si ya existe una estructura propia para Avance 2, adapta las rutas respetando enlaces relativos.
3. Desde el `README.md` principal, añadir un enlace hacia `FleetLogix_Avance2_Repo/README_AVANCE_2.md`.
4. Verificar el estado de cambios y que no incluyes secretos:

```bash
git status
git diff --stat
git add FleetLogix_Avance2_Repo
git commit -m "docs: documentar analisis SQL y optimizacion de FleetLogix avance 2"
git push
```

> Si integras **el contenido** en carpetas ya existentes de la raíz en vez de conservar el subdirectorio, ajusta rutas de `git add` y enlaces.

## Recomendaciones

- Conserva el `Scripts/02_queries_analysis.sql` original como referencia histórica sin reemplazarlo si ya está en el repositorio: puedes omitir el duplicado de este paquete.
- No reejecutes el DDL de índices ni las cargas de datos para 'subir la documentación'. Un commit de Markdown, CSV y capturas no requiere tocar PostgreSQL.
- Antes de entregar académicamente, valida los pendientes de `Documentacion/04_decisiones_y_pendientes.md`.
