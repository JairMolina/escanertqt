/* Private APK distribution. No catalog/firmware or credential is embedded here. */
(async function () {
    'use strict';
    const $ = (id) => document.getElementById(id);
    try {
        const response = await fetch('/api/android/apk/manifest', { credentials: 'same-origin' });
        if (response.status === 503) {
            $('apk-status').textContent = 'Publicación pendiente';
            $('apk-message').textContent = 'Todavía no hay una APK firmada y aprobada para distribución. La descarga se habilitará después de verificarla.';
            return;
        }
        if (!response.ok) throw new Error('No se pudo comprobar la versión aprobada. Vuelve a iniciar sesión o inténtalo más tarde.');
        const release = await response.json();
        if (!release.available || !/^[a-f0-9]{64}$/.test(release.sha256) || release.download_url !== '/api/android/apk/download') throw new Error('La publicación no tiene información de integridad válida.');
        $('apk-version').textContent = release.version_name;
        $('apk-sdk').textContent = 'API ' + release.min_sdk;
        $('apk-size').textContent = (release.bytes / 1048576).toFixed(1) + ' MB';
        $('apk-sha').value = release.sha256;
        $('apk-status').textContent = 'Versión aprobada';
        $('apk-message').textContent = 'Archivo y firma verificados por el servidor. Conserva la misma firma para futuras actualizaciones.';
        ['apk-metadata', 'apk-download', 'apk-integrity'].forEach((id) => { $(id).hidden = false; });
        $('apk-copy').addEventListener('click', async () => {
            try { await navigator.clipboard.writeText(release.sha256); $('apk-copy').textContent = 'Huella copiada'; }
            catch (_) { $('apk-sha').focus(); $('apk-sha').select(); $('apk-copy').textContent = 'Selecciona y copia la huella'; }
        });
    } catch (error) {
        $('apk-status').textContent = 'No disponible';
        $('apk-message').textContent = error.message || 'No se pudo consultar la descarga.';
    }
})();
