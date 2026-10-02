# Inicio de sesión (v1.3.16)

Toda la app exige iniciar sesión con **correo y contraseña**.

| Cuenta | Contraseña inicial |
|---|---|
| developer@skyguardian.mx, developer4@…, developer5@…, developer6@… | la acordada (cámbiala al entrar) |

- **Pública**: `/login`, `/api/auth/login`, `/api/health`, `/cert`, `/ca`, `/static/css|fonts|icons` y `/static/js/login.js`.
- **Todo lo demás** (páginas, API, WebSocket, JS/HTML): sin sesión → `302 /login?next=…` (páginas) o `401` con cabecera `X-Auth: login` (API, que el navegador convierte en redirección). El WebSocket se rechaza antes de aceptar.
- Sesión: cookie `tqt_sesion` firmada HMAC (HttpOnly, Secure, SameSite=Lax, 12 h, `TQT_SESION_HORAS`). Cambiar la clave o desactivar la cuenta la invalida. Cerrar sesión borra la cookie del equipo (no revoca copias ya robadas: caducan a las 12 h o al cambiar la clave).
- Intentos: 5 fallos por equipo o por correo → bloqueo de 5 min (`TQT_ADMIN_MAX_FALLOS`, `TQT_ADMIN_BLOQUEO_SEG`); el mismo mensaje para correo desconocido y clave incorrecta.
- `/admin` conserva su contraseña de supervisor (`TQT_ADMIN_PASSWORD`) además de la sesión.
- Cambiar contraseña: candado en la consola o `/login?cambiar=1` (mínimo 10 caracteres, `TQT_USER_MIN_CLAVE`).
- Cuentas nuevas o desactivar una: tabla `usuarios` (campo `activo`); `usuarios.sembrar()` solo crea las que faltan y nunca pisa una clave cambiada. Contraseña inicial: `TQT_USER_SEED_PASSWORD`.
- Pruebas: `tests/test_auth_seguridad.py`, `tests/e2e/login_flujo.py`.
