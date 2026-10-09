# Configuración devsky

Estos archivos son copias sin credenciales de la configuración del servidor. Se usan copiándolos a `servidor/Dockerfile` y `servidor/compose.yml`, desde donde las rutas relativas apuntan al proyecto y sus datos. Conservar el archivo privado `servidor/.env` y los volúmenes. No ejecutar compose directamente desde deploy/devsky.

La configuración monta app, station y firmware/stm32_r1 en solo lectura sobre la imagen existente para evitar reconstrucciones grandes en el entorno de desarrollo.
