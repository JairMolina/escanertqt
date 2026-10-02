/**
 * sec_enlaces.js - Entradas de la barra lateral que por ahora abren otra pantalla (una etapa posterior les dará el mismo armazón):
 * Movimientos -> /admin#movimientos · Etiquetas -> /dymo · Administración -> /admin
 */
(function () {
    'use strict';
    const E = window.TQTEscritorio;
    E.registrar({ id: 'movimientos', titulo: 'Movimientos', icono: 'list', grupo: 'gestion', orden: 70, href: '/admin#movimientos' });
    E.registrar({ id: 'etiquetas', titulo: 'Etiquetas DYMO', icono: 'printer', grupo: 'gestion', orden: 80, href: '/dymo' });
    E.registrar({ id: 'admin', titulo: 'Administración', icono: 'shield', grupo: 'gestion', orden: 100, href: '/admin' });
})();
