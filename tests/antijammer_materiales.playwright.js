async (page, claveLocal) => {
    // Solo la instancia aislada de revisión con la muestra indicada en docs/ANTIJAMMER_COMPONENTES.md.
    const base = 'http://localhost:18095', c = await page.context().browser().newContext({ viewport: { width: 1440, height: 920 } });
    const ok = (x, msg) => { if (!x) throw Error(msg); };
    const p = await c.newPage(), errores = [], escrituras = [];
    p.on('pageerror', e => errores.push(e.message));
    p.on('request', r => { if (r.url().includes('/api/antijammer/') && r.method() !== 'GET') escrituras.push(r.url()); });
    try {
        ok(claveLocal, 'Indica la clave del entorno QA');
        ok((await c.request.post(base + '/api/auth/login', { data: { email: 'developer4@skyguardian.mx', password: claveLocal } })).ok(), 'Sesión QA');
        await p.goto(base + '/antijammer#materiales');
        const btn = nombre => p.getByRole('button', { name: nombre, exact: true });
        await btn('Componentes').click();
        await p.getByLabel('Buscar componente').fill('conector');
        ok(await p.locator('#mtCuerpo tbody tr').count() === 1, 'Búsqueda de componentes');
        await p.getByRole('link', { name: 'Inventario de PCB', exact: true }).click();
        await p.getByRole('heading', { name: 'Inventario de PCB', exact: true }).waitFor();
        await p.getByRole('link', { name: 'Inventario de componentes', exact: true }).click();
        await btn('Registro').click();
        await p.getByText(/Movimientos recientes/).click();
        await p.getByText(/Datos de ejemplo del piloto/).first().waitFor();
        await btn('Solicitud de material').click();
        const rx = p.getByLabel('Tarjetas RX', { exact: true }), tx = p.getByLabel('Tarjetas TX', { exact: true });
        const radio = texto => p.getByRole('radio', { name: new RegExp(texto) });
        const fila = material => p.getByRole('row', { name: new RegExp(material) });
        const pedir = async material => fila(material).locator('[data-l="A solicitar"]').textContent();
        await rx.fill('5'); await tx.fill('4');
        ok(await pedir('Conector de banco') === '10' && await pedir('Relevador de prueba') === '4' && await pedir('Cable de prueba') === '0', 'Saldo compartido solo una vez');
        async function descargar(sufijo) {
            const [archivo] = await Promise.all([p.waitForEvent('download'), btn('Descargar solicitud CSV').click()]);
            ok(archivo.suggestedFilename().endsWith(sufijo), 'Nombre del CSV');
            const flujo = await archivo.createReadStream(), bytes = [];
            for await (const parte of flujo) bytes.push(parte);
            const lineas = Buffer.concat(bytes).toString('utf8').split('\r\n');
            const tabla = p.getByRole('table', { name: 'Desglose de la solicitud' });
            const nombres = await tabla.locator('tbody th').allTextContents();
            ok(lineas.length === nombres.length + 1 && nombres.every((nombre, i) => lineas[i + 1].startsWith('"' + nombre + '",')),
                'CSV y tabla muestran las mismas filas en el mismo orden');
            return lineas;
        }
        const csv = await descargar('-con-existencias.csv');
        ok(csv.some(l => l.startsWith('"Conector de banco","pza","22","12","10",')) &&
            csv.some(l => l.startsWith('"Cable de prueba","m","1.25","4","0",')), 'CSV con faltantes y materiales cubiertos');
        await radio('Ignorar existencias').check();
        ok(await pedir('Conector de banco') === '22' && await pedir('Cable de prueba') === '1.25', 'Material bruto y fracciones');
        ok(!await p.getByRole('columnheader', { name: 'Disponible' }).count(), 'Modo bruto ignora existencias');
        const bruto = await descargar('-total.csv');
        ok(!bruto[0].includes('"Disponible"') && bruto.some(l => l.startsWith('"Conector de banco","pza","22","22",')), 'CSV sin descontar existencias');
        await radio('Descontar existencias').check();
        await rx.fill('1'); await tx.fill('0');
        await p.getByText('El stock cubre todas las tarjetas.', { exact: false }).waitFor();
        const cubierto = await descargar('-con-existencias.csv');
        ok(cubierto.slice(1).every(l => l.includes(',"0","RX: 1 / TX: 0",')), 'CSV disponible aunque todo esté cubierto');
        await rx.fill('-1'); await p.getByText(/Usa cantidades enteras/).waitFor();
        await rx.fill('1.5'); ok(!await p.getByRole('table', { name: 'Desglose de la solicitud' }).count(), 'Sin cálculos parciales inválidos');
        await rx.fill('5'); await tx.fill('4');
        await p.setViewportSize({ width: 390, height: 844 });
        ok(await p.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth), 'Sin desborde móvil');
        await p.locator('#bMas').click(); await p.getByRole('link', { name: 'Inventario de componentes', exact: true }).last().click();
        ok(await pedir('Conector de banco') === '10', 'Menú móvil');
        // Respuestas de borde en este navegador, nunca se toca el catálogo de QA.
        let defecto = 'negativo';
        await p.route('**/api/antijammer/materiales', async r => {
            const response = await r.fetch(), data = await response.json();
            const conector = data.materiales.find(m => m.descripcion === 'Conector de banco');
            if (defecto === 'negativo') conector.disponible = -2;
            if (defecto === 'unidad') conector.unidad_ambigua = true;
            if (defecto === 'sin_bom') data.materiales = [];
            await r.fulfill({ response, json: data });
        });
        await btn('Actualizar existencias').click();
        await p.waitForFunction(() => document.querySelector('.mt-pedir')?.textContent === '22');
        defecto = 'unidad'; await btn('Actualizar existencias').click(); await p.getByText(/unidades diferentes/).waitFor();
        defecto = 'sin_bom'; await btn('Actualizar existencias').click(); await p.getByText(/Falta la lista de materiales/).waitFor();
        ok(!await btn('Descargar solicitud CSV').count(), 'Sin solicitud parcial por BOM faltante');
        ok(!errores.length && !escrituras.length, 'Consola y consulta sin escrituras: ' + errores.concat(escrituras).join(', '));
        return 'OK: inventarios, búsqueda, registro, cálculo neto/bruto RX + TX, CSV, límites y unidades, escritorio/móvil, cero escrituras al planificar';
    } finally { await c.close(); }
}
