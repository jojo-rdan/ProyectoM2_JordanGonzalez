# Guía de integración en el repositorio existente

El ZIP contiene **archivos actualizados y la documentación del Avance #2**, no el repositorio entero. No sustituye los scripts Python, notebooks, archivos del Avance #1 ni la base PostgreSQL que ya tienes.

## Dónde copiar cada cosa

1. **En la raíz del repositorio:** reemplazar el antiguo `README.md` por el nuevo y actualizar `README_ETAPA4.md`.
2. **Documentación:** copiar todo `Documentacion/Avance_2/` dentro de la carpeta `Documentacion` del repositorio. Respetar `Datos/` y `Evidencias/` para mantener los enlaces relativos.
3. **SQL:** copiar `Scripts/Avance_2/` a la carpeta `Scripts` del repositorio. No sobrescribir el SQL original que ya exista en otra ruta.
4. **No modificar** los documentos y notebooks del Avance #1 salvo que sea necesario ajustar enlaces existentes.
5. El ZIP **no contiene** los 505.650 registros originales, archivos `.env`, contraseñas ni entornos virtuales.

## Comprobación de Git antes de subir

```bash
git status
# Revisa los nuevos archivos y comprueba que no hay secretos.
git add README.md README_ETAPA4.md Documentacion/Avance_2 Scripts/Avance_2
git diff --cached --stat
git commit -m "docs: actualizar README general y documentar avances FleetLogix"
git push
```

> El comando `git add` supone que los nombres de las carpetas coinciden con los del ZIP. Si usas otra estructura o ya tienes el SQL del Avance #2 en otra ruta, adapta esas rutas y verifica enlaces Markdown.

## Lo que sigue pendiente

Aunque las ocho consultas y los cinco índices ya fueron evaluados, no declarar cerrado el Avance #2 hasta completar el benchmark final homogéneo, las evidencias que faltan y los entregables exigidos por la rúbrica. Consulta `Documentacion/Avance_2/04_decisiones_y_pendientes.md`.
