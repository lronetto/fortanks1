
    /** Metadados da tabela comparativa (material_id → nome, codigo_erp, unidade). */
    function mapaMateriaisMetaDaTabela() {
        const map = {};
        if (!table) return map;
        try {
            table.rows({ search: 'applied' }).every(function () {
                const row = this.data();
                if (row && row.material_id != null) {
                    const sid = String(row.material_id);
                    map[sid] = {
                        nome: (row.material_nome || '').trim(),
                        codigo_erp: formatarCodigoErpInteiro(row.codigo_erp),
                        unidade: (row.unidade_sistema || '').trim(),
                        valor_unitario: parseFloat(row.valor_unitario) || 0
                    };
                }
            });
        } catch (e) {}
        return map;
    }

    async function mapaMateriaisMetaParaExport() {
        const map = {};
        const daTabela = mapaMateriaisMetaDaTabela();
        Object.keys(daTabela).forEach(function (sid) {
            map[sid] = Object.assign({}, daTabela[sid]);
        });
        Object.keys(simulacaoItens).forEach(function (k) {
            const it = simulacaoItens[k];
            if ((it.tipo_item || TIPO_SIM_TANQUE) === TIPO_SIM_MATERIAL_AVULSO && it.material_id != null) {
                const sid = String(it.material_id);
                if (!map[sid]) map[sid] = {};
                if (it.material_nome) map[sid].nome = String(it.material_nome).trim();
            }
        });
        try {
            const resp = await fetch('{{ url_for("material.listar_json") }}');
            const data = await resp.json();
            if (Array.isArray(data)) {
                data.forEach(function (m) {
                    if (!m || m.id == null) return;
                    const sid = String(m.id);
                    const nome = (m.nome || '').trim();
                    const codigoErp = formatarCodigoErpInteiro(m.codigo_erp);
                    const un = (m.unidade || '').trim();
                    if (!map[sid]) map[sid] = {};
                    if (nome) map[sid].nome = nome;
                    if (codigoErp) map[sid].codigo_erp = codigoErp;
                    if (un) map[sid].unidade = un;
                });
            }
        } catch (e) {
            console.warn('mapaMateriaisMetaParaExport:', e);
        }
        return map;
    }

    function metaMaterialExport(metaMap, mid) {
        const m = metaMap[String(mid)] || {};
        const nome = (m.nome || '').trim();
        return {
            nome: nome || ('Material #' + mid),
            codigo_erp: formatarCodigoErpInteiro(m.codigo_erp),
            unidade: (m.unidade || '').trim(),
            valor_unitario: parseFloat(m.valor_unitario) || 0
        };
    }

    /** Formatos numéricos estilo contábil (Excel / locale pt-BR). */
    const XLSX_FMT_MOEDA_CONTABIL = '[$R$-416] #,##0.00';
    const XLSX_FMT_DECIMAL_4 = '#,##0.0000';
    const XLSX_FMT_DECIMAL_2 = '#,##0.00';

    function xlsxAplicarNumFmtCelula(ws, r, c, numFmt) {
        if (!ws || numFmt == null) return;
        const addr = XLSX.utils.encode_cell({ r: r, c: c });
        const cell = ws[addr];
        if (!cell || cell.v === '' || cell.v == null) return;
        if (typeof cell.v === 'number' && !isNaN(cell.v)) {
            cell.t = 'n';
            cell.z = numFmt;
        }
    }

    function xlsxFormatarAbaPesosLinhas(ws) {
        if (!ws || !ws['!ref']) return;
        const d = XLSX.utils.decode_range(ws['!ref']);
        for (let r = 1; r <= d.e.r; r++) {
            xlsxAplicarNumFmtCelula(ws, r, 8, XLSX_FMT_DECIMAL_2);
            xlsxAplicarNumFmtCelula(ws, r, 9, XLSX_FMT_DECIMAL_2);
            xlsxAplicarNumFmtCelula(ws, r, 10, XLSX_FMT_DECIMAL_2);
        }
    }

    /** Bloco "Chave / Qtd total / Peso" nas abas por PC. */
    function xlsxFormatarAbaPcBlocoLinhasSimulacao(ws) {
        if (!ws || !ws['!ref']) return;
        const d = XLSX.utils.decode_range(ws['!ref']);
        let headerRow = -1;
        for (let r = d.s.r; r <= d.e.r; r++) {
            const c0 = ws[XLSX.utils.encode_cell({ r: r, c: 0 })];
            const c3 = ws[XLSX.utils.encode_cell({ r: r, c: 3 })];
            if (c0 && String(c0.v) === 'Chave' && c3 && String(c3.v) === 'Qtd total') {
                headerRow = r;
                break;
            }
        }
        if (headerRow < 0) return;
        for (let r = headerRow + 1; r <= d.e.r; r++) {
            const c0 = ws[XLSX.utils.encode_cell({ r: r, c: 0 })];
            if (!c0 || c0.v === '' || c0.v == null) break;
            const t0 = String(c0.v);
            if (t0.indexOf('Materiais') === 0) break;
            xlsxAplicarNumFmtCelula(ws, r, 3, XLSX_FMT_DECIMAL_2);
            xlsxAplicarNumFmtCelula(ws, r, 4, XLSX_FMT_DECIMAL_2);
            xlsxAplicarNumFmtCelula(ws, r, 5, XLSX_FMT_DECIMAL_2);
        }
    }

    function xlsxEncontrarLinhaColATexto(ws, contem) {
        if (!ws || !ws['!ref']) return -1;
        const d = XLSX.utils.decode_range(ws['!ref']);
        const s = String(contem);
        for (let r = d.s.r; r <= d.e.r; r++) {
            const c0 = ws[XLSX.utils.encode_cell({ r: r, c: 0 })];
            if (c0 && String(c0.v).indexOf(s) !== -1) return r;
        }
        return -1;
    }

    function xlsxAplicarNumFmtCelulaOuFormula(ws, r, c, numFmt) {
        if (!ws || numFmt == null) return;
        const addr = XLSX.utils.encode_cell({ r: r, c: c });
        const cell = ws[addr];
        if (!cell) return;
        if (cell.f) {
            cell.z = numFmt;
            return;
        }
        xlsxAplicarNumFmtCelula(ws, r, c, numFmt);
    }

    /** Fórmulas na tabela de materiais da aba PC (10 colunas A–J). Ordem: … unidade, indice_ponderado, valor_unitario, consumo_total_qtd, … */
    function xlsxAplicarFormulasTabelaMateriaisPc(ws, numLinhasMateriais) {
        if (!ws || !ws['!ref'] || !numLinhasMateriais) return;
        let headerRow = -1;
        const d = XLSX.utils.decode_range(ws['!ref']);
        for (let r = d.s.r; r <= d.e.r; r++) {
            const c0 = ws[XLSX.utils.encode_cell({ r: r, c: 0 })];
            if (c0 && String(c0.v) === 'material_id') {
                headerRow = r;
                break;
            }
        }
        if (headerRow < 0) return;
        const r0 = headerRow + 1;
        const r1 = headerRow + numLinhasMateriais;
        const rTot = r1 + 1;
        const rSum = xlsxEncontrarLinhaColATexto(ws, 'Soma Qtd (linhas tanque)');
        if (rSum < 0) return;
        const bSum = '$B$' + (rSum + 1);
        const colE = XLSX.utils.encode_col(4);
        const colF = XLSX.utils.encode_col(5);
        const colG = XLSX.utils.encode_col(6);
        const colH = XLSX.utils.encode_col(7);
        const colI = XLSX.utils.encode_col(8);
        const colJ = XLSX.utils.encode_col(9);
        let r;
        for (r = r0; r <= r1; r++) {
            const rx = r + 1;
            ws[XLSX.utils.encode_cell({ r: r, c: 6 })] = { f: colI + rx + '+' + colJ + rx, t: 'n', z: XLSX_FMT_DECIMAL_4 };
            ws[XLSX.utils.encode_cell({ r: r, c: 4 })] = {
                // indice_ponderado = consumo_total_qtd / quantidade_total
                f: 'IF(' + bSum + '>0,' + colG + rx + '/' + bSum + ',0)',
                t: 'n',
                z: XLSX_FMT_DECIMAL_4
            };
            ws[XLSX.utils.encode_cell({ r: r, c: 7 })] = { f: colF + rx + '*' + colG + rx, t: 'n', z: XLSX_FMT_MOEDA_CONTABIL };
        }
        const r0x = r0 + 1;
        const r1x = r1 + 1;
        ws[XLSX.utils.encode_cell({ r: rTot, c: 6 })] = { f: 'SUM(' + colG + r0x + ':' + colG + r1x + ')', t: 'n', z: XLSX_FMT_DECIMAL_4 };
        ws[XLSX.utils.encode_cell({ r: rTot, c: 7 })] = { f: 'SUM(' + colH + r0x + ':' + colH + r1x + ')', t: 'n', z: XLSX_FMT_MOEDA_CONTABIL };
    }

    /** Fórmulas na aba só avulsos: valor = VU × consumo; totais SUM. */
    function xlsxAplicarFormulasTabelaMateriaisAvulsos(ws, numLinhasMateriais) {
        if (!ws || !ws['!ref'] || !numLinhasMateriais) return;
        let headerRow = -1;
        const d = XLSX.utils.decode_range(ws['!ref']);
        for (let r = d.s.r; r <= d.e.r; r++) {
            const c0 = ws[XLSX.utils.encode_cell({ r: r, c: 0 })];
            if (c0 && String(c0.v) === 'material_id') {
                headerRow = r;
                break;
            }
        }
        if (headerRow < 0) return;
        const r0 = headerRow + 1;
        const r1 = headerRow + numLinhasMateriais;
        const rTot = r1 + 1;
        const colE = XLSX.utils.encode_col(4);
        const colF = XLSX.utils.encode_col(5);
        const colG = XLSX.utils.encode_col(6);
        let r;
        for (r = r0; r <= r1; r++) {
            const rx = r + 1;
            ws[XLSX.utils.encode_cell({ r: r, c: 6 })] = { f: colE + rx + '*' + colF + rx, t: 'n', z: XLSX_FMT_MOEDA_CONTABIL };
        }
        const r0x = r0 + 1;
        const r1x = r1 + 1;
        ws[XLSX.utils.encode_cell({ r: rTot, c: 5 })] = { f: 'SUM(' + colF + r0x + ':' + colF + r1x + ')', t: 'n', z: XLSX_FMT_DECIMAL_4 };
        ws[XLSX.utils.encode_cell({ r: rTot, c: 6 })] = { f: 'SUM(' + colG + r0x + ':' + colG + r1x + ')', t: 'n', z: XLSX_FMT_MOEDA_CONTABIL };
    }

    /** Tabela material_id: aba PC (10 colunas) ou só avulsos (7 colunas). */
    function xlsxFormatarAbaTabelaMateriais(ws) {
        if (!ws || !ws['!ref']) return;
        const d = XLSX.utils.decode_range(ws['!ref']);
        let headerRow = -1;
        for (let r = d.s.r; r <= d.e.r; r++) {
            const c0 = ws[XLSX.utils.encode_cell({ r: r, c: 0 })];
            if (c0 && String(c0.v) === 'material_id') {
                headerRow = r;
                break;
            }
        }
        if (headerRow < 0) return;
        const h4 = ws[XLSX.utils.encode_cell({ r: headerRow, c: 4 })];
        const layoutPc = h4 && String(h4.v) === 'indice_ponderado';
        for (let r = headerRow + 1; r <= d.e.r; r++) {
            const a2 = ws[XLSX.utils.encode_cell({ r: r, c: 2 })];
            if (a2 && String(a2.v) === 'TOTAL') break;
            if (layoutPc) {
                xlsxAplicarNumFmtCelulaOuFormula(ws, r, 4, XLSX_FMT_DECIMAL_4);
                xlsxAplicarNumFmtCelulaOuFormula(ws, r, 5, XLSX_FMT_MOEDA_CONTABIL);
                xlsxAplicarNumFmtCelulaOuFormula(ws, r, 6, XLSX_FMT_DECIMAL_4);
                xlsxAplicarNumFmtCelulaOuFormula(ws, r, 7, XLSX_FMT_MOEDA_CONTABIL);
                xlsxAplicarNumFmtCelula(ws, r, 8, XLSX_FMT_DECIMAL_4);
                xlsxAplicarNumFmtCelula(ws, r, 9, XLSX_FMT_DECIMAL_4);
            } else {
                xlsxAplicarNumFmtCelulaOuFormula(ws, r, 4, XLSX_FMT_MOEDA_CONTABIL);
                xlsxAplicarNumFmtCelulaOuFormula(ws, r, 5, XLSX_FMT_DECIMAL_4);
                xlsxAplicarNumFmtCelulaOuFormula(ws, r, 6, XLSX_FMT_MOEDA_CONTABIL);
            }
        }
        let rTot = -1;
        for (let r = headerRow + 1; r <= d.e.r; r++) {
            const a2tot = ws[XLSX.utils.encode_cell({ r: r, c: 2 })];
            if (a2tot && String(a2tot.v) === 'TOTAL') {
                rTot = r;
                break;
            }
        }
        if (rTot >= 0) {
            if (layoutPc) {
                xlsxAplicarNumFmtCelulaOuFormula(ws, rTot, 6, XLSX_FMT_DECIMAL_4);
                xlsxAplicarNumFmtCelulaOuFormula(ws, rTot, 7, XLSX_FMT_MOEDA_CONTABIL);
            } else {
                xlsxAplicarNumFmtCelulaOuFormula(ws, rTot, 5, XLSX_FMT_DECIMAL_4);
                xlsxAplicarNumFmtCelulaOuFormula(ws, rTot, 6, XLSX_FMT_MOEDA_CONTABIL);
            }
        }
    }

    async function exportarIndicesMateriaisSimulacaoExcel() {
        if (typeof XLSX === 'undefined') {
            alert('Biblioteca Excel não disponível. Recarregue a página.');
            return;
        }
        const keys = Object.keys(simulacaoItens);
        if (!keys.length) {
            alert('Adicione itens na simulação antes de exportar.');
            return;
        }
        const produtoIds = Array.from(new Set(
            keys
                .map(function (k) {
                    const it = simulacaoItens[k];
                    const t = it.tipo_item || TIPO_SIM_TANQUE;
                    if (t === TIPO_SIM_MATERIAL_AVULSO || !it.produto_composto_id) return null;
                    return String(it.produto_composto_id);
                })
                .filter(Boolean)
        ));
        try {
            await carregarEstruturasProdutos(produtoIds);
        } catch (e) {
            console.error(e);
            alert('Não foi possível carregar estruturas de produtos para a exportação.');
            return;
        }
        const pesosEf = calcularPesosEfetivosSimulacao();
        const consumoPorLinha = {};
        for (let i = 0; i < keys.length; i++) {
            const k = keys[i];
            const pl = itemPayloadParaCalculo(k);
            consumoPorLinha[k] = await consumoTerceiroPorItemSimulacao(pl, simulacaoItens[k]);
        }
        const metaMap = await mapaMateriaisMetaParaExport();

        /** Origem do consumo no material: BOM do produto composto explodido (API estrutura) ou material avulso direto. */
        function metaFonteLinha(k) {
            const it = simulacaoItens[k];
            if (!it) return { fonte: '', fonte_label: '', pc_id: '', pc_nome: '', mav_id: '' };
            const tipo = it.tipo_item || TIPO_SIM_TANQUE;
            if (tipo === TIPO_SIM_MATERIAL_AVULSO) {
                return {
                    fonte: 'material_avulso',
                    fonte_label: 'Material avulso (direto)',
                    pc_id: '',
                    pc_nome: '',
                    mav_id: it.material_id != null ? it.material_id : ''
                };
            }
            if (tipo === TIPO_SIM_PRODUTO_AVULSO) {
                return {
                    fonte: 'produto_avulso',
                    fonte_label: 'Produto composto avulso (explodido)',
                    pc_id: it.produto_composto_id != null ? it.produto_composto_id : '',
                    pc_nome: it.produto_composto_nome || '',
                    mav_id: ''
                };
            }
            return {
                fonte: 'pc_explodido',
                fonte_label: 'Produto composto (tanque, explodido)',
                pc_id: it.produto_composto_id != null ? it.produto_composto_id : '',
                pc_nome: it.produto_composto_nome || '',
                mav_id: ''
            };
        }

        const wb = XLSX.utils.book_new();
        const nomesAbasUsados = {};

        function sanitizarNomeAba(nome, maxLen) {
            let x = String(nome || 'Aba').replace(/[:\\\/\?\*\[\]]/g, ' ').replace(/\s+/g, ' ').trim();
            if (x.length > maxLen) x = x.slice(0, maxLen);
            return x || 'Aba';
        }
        function nomeAbaUnico(base) {
            let n = sanitizarNomeAba(base, 31);
            let orig = n;
            let i = 2;
            while (nomesAbasUsados[n]) {
                const suf = ' ' + i;
                n = sanitizarNomeAba(orig.slice(0, Math.max(1, 31 - suf.length)) + suf, 31);
                i++;
            }
            nomesAbasUsados[n] = true;
            return n;
        }

        const linhasPesos = [[
            'Chave', 'Fonte consumo', 'Produto composto (id)', 'Produto composto (nome)', 'Material avulso (id)',
            'Grupo', 'Tipo peça', 'Descrição', 'Qtd total', 'Peso informado (%)', 'Peso efetivo (%)'
        ]];
        keys.forEach(function (k) {
            const it = simulacaoItens[k];
            const pl = itemPayloadParaCalculo(k);
            const raw = it.peso;
            const informado = raw === null || raw === undefined || String(raw).trim() === '' ? '' : String(raw).trim();
            const tipo = it.tipo_item || TIPO_SIM_TANQUE;
            const semPeso = tipoItemSemPesoSimulacao(tipo);
            let desc = it.produto_composto_nome || '';
            if (tipo === TIPO_SIM_MATERIAL_AVULSO) desc = it.material_nome || desc;
            const meta = metaFonteLinha(k);
            const peInf = semPeso
                ? '—'
                : (informado === '' ? '(automático)' : (parseFloat(informado.replace(',', '.')) || 0));
            const peEf = semPeso ? '—' : (pesosEf[k] != null ? pesosEf[k] : 0);
            linhasPesos.push([
                k,
                meta.fonte_label,
                meta.pc_id,
                meta.pc_nome,
                meta.mav_id,
                it.grupo_label || '',
                it.tipo_peca || '',
                desc,
                pl ? pl.quantidade_total : 0,
                peInf,
                peEf
            ]);
        });
        nomesAbasUsados['Pesos linhas'] = true;
        (function () {
            const wsP = XLSX.utils.aoa_to_sheet(linhasPesos);
            xlsxFormatarAbaPesosLinhas(wsP);
            XLSX.utils.book_append_sheet(wb, wsP, 'Pesos linhas');
        })();

        // Mesmo tratamento na planilha: material avulso + produto avulso (consumo explodido em materiais, sem aba por PC).
        const keysMav = keys.filter(function (k) {
            return tipoItemSemPesoSimulacao(simulacaoItens[k].tipo_item || TIPO_SIM_TANQUE);
        });
        const keysPc = keys.filter(function (k) {
            return !tipoItemSemPesoSimulacao(simulacaoItens[k].tipo_item || TIPO_SIM_TANQUE);
        });
        let wTotalPc = 0;
        keysPc.forEach(function (k) {
            wTotalPc += pesosEf[k] != null ? pesosEf[k] : 0;
        });
        const consumoMavPorMid = {};
        keysMav.forEach(function (k) {
            const om = consumoPorLinha[k] || {};
            Object.keys(om).forEach(function (mid) {
                const v = parseFloat(om[mid]) || 0;
                if (v <= 0) return;
                consumoMavPorMid[mid] = (consumoMavPorMid[mid] || 0) + v;
            });
        });

        const porPc = {};
        keys.forEach(function (k) {
            const it = simulacaoItens[k];
            const t = it.tipo_item || TIPO_SIM_TANQUE;
            if (tipoItemSemPesoSimulacao(t) || !it.produto_composto_id) return;
            const pid = String(it.produto_composto_id);
            if (!porPc[pid]) porPc[pid] = [];
            porPc[pid].push(k);
        });
        Object.keys(porPc).sort(function (a, b) { return parseInt(a, 10) - parseInt(b, 10); }).forEach(function (pid) {
            const lineKeys = porPc[pid];
            const it0 = simulacaoItens[lineKeys[0]];
            const nomePc = (it0 && it0.produto_composto_nome) ? String(it0.produto_composto_nome) : ('ID ' + pid);
            const aoa = [];
            aoa.push(['Produto composto (id)', pid, '', '']);
            aoa.push(['Nome', nomePc, '', '']);
            aoa.push([]);
            aoa.push(['Linhas de simulação com este produto', '', '', '', '', '']);
            aoa.push(['Chave', 'Grupo', 'Tipo peça', 'Qtd total', 'Peso informado (%)', 'Peso efetivo (%)']);
            lineKeys.forEach(function (k) {
                const it = simulacaoItens[k];
                const pl = itemPayloadParaCalculo(k);
                const raw = it.peso;
                const informado = raw === null || raw === undefined || String(raw).trim() === '' ? '' : String(raw).trim();
                aoa.push([
                    k,
                    it.grupo_label || '',
                    it.tipo_peca || '',
                    pl ? pl.quantidade_total : 0,
                    informado === '' ? '(automático)' : (parseFloat(informado.replace(',', '.')) || 0),
                    pesosEf[k] != null ? pesosEf[k] : 0
                ]);
            });
            aoa.push([]);
            aoa.push(['Materiais (estrutura explodida + avulsos rateados pelo peso PC)', '', '', '', '', '', '', '', '', '']);
            aoa.push(['material_id', 'codigo_erp', 'material_nome', 'unidade', 'indice_ponderado', 'valor_unitario', 'consumo_total_qtd', 'valor_total_consumo', 'consumo_tanque', 'consumo_avulso_rateado']);
            const aggMat = {};
            const midsBom = new Set();
            lineKeys.forEach(function (k) {
                Object.keys(consumoPorLinha[k] || {}).forEach(function (mid) { midsBom.add(mid); });
            });
            Array.from(midsBom).forEach(function (mid) {
                let consTot = 0;
                lineKeys.forEach(function (k) {
                    const c = (consumoPorLinha[k] && consumoPorLinha[k][mid]) ? consumoPorLinha[k][mid] : 0;
                    consTot += c;
                });
                if (consTot > 0) {
                    aggMat[mid] = { consBom: consTot, consMav: 0 };
                }
            });
            Object.keys(consumoMavPorMid).forEach(function (mid) {
                const cMav = consumoMavPorMid[mid];
                if (cMav <= 0) return;
                let wPid = 0;
                lineKeys.forEach(function (k) {
                    wPid += pesosEf[k] != null ? pesosEf[k] : 0;
                });
                let consRateio = 0;
                if (wTotalPc > 0) {
                    consRateio = cMav * (wPid / wTotalPc);
                } else if (lineKeys.length > 0) {
                    consRateio = cMav / Object.keys(porPc).length;
                }
                if (consRateio <= 0) return;
                if (!aggMat[mid]) aggMat[mid] = { consBom: 0, consMav: 0 };
                aggMat[mid].consMav += consRateio;
            });
            const sumQtdTotalAba = lineKeys.reduce(function (acc, k) {
                const pl = itemPayloadParaCalculo(k);
                const Qk = pl ? Math.max(parseFloat(pl.quantidade_total) || 0, 0) : 0;
                return acc + Qk;
            }, 0);
            const pesoEfetivoMedio = sumQtdTotalAba > 0
                ? lineKeys.reduce(function (acc, k) {
                    const pl = itemPayloadParaCalculo(k);
                    const Qk = pl ? Math.max(parseFloat(pl.quantidade_total) || 0, 0) : 0;
                    const pe = pesosEf[k] != null ? pesosEf[k] : 0;
                    return acc + Qk * pe;
                }, 0) / sumQtdTotalAba
                : 0;
            const chavesMatPc = Object.keys(aggMat).sort(function (a, b) {
                return parseInt(a, 10) - parseInt(b, 10);
            });
            chavesMatPc.forEach(function (mid) {
                const a = aggMat[mid];
                const consBom = a.consBom != null ? a.consBom : 0;
                const consMav = a.consMav != null ? a.consMav : 0;
                const meta = metaMaterialExport(metaMap, mid);
                const vu = meta.valor_unitario;
                aoa.push([mid, meta.codigo_erp, meta.nome, meta.unidade, '', vu, '', '', consBom, consMav]);
            });
            aoa.push(['', '', 'TOTAL', '', '', '', '', '', '', '']);
            aoa.push([]);
            aoa.push(['Soma Qtd (linhas tanque)', sumQtdTotalAba]);
            aoa.push(['Peso médio efetivo (%)', pesoEfetivoMedio]);
            const nomeAba = nomeAbaUnico('PC' + pid + ' ' + nomePc);
            const nMatPc = chavesMatPc.length;
            (function () {
                const wsPc = XLSX.utils.aoa_to_sheet(aoa);
                xlsxAplicarFormulasTabelaMateriaisPc(wsPc, nMatPc);
                xlsxFormatarAbaPcBlocoLinhasSimulacao(wsPc);
                xlsxFormatarAbaTabelaMateriais(wsPc);
                XLSX.utils.book_append_sheet(wb, wsPc, nomeAba);
            })();
        });

        if (Object.keys(porPc).length === 0 && keysMav.length > 0) {
            const aoaAv = [];
            aoaAv.push(['Materiais (material avulso + produto composto avulso explodido)', '', '', '', '', '', '']);
            aoaAv.push(['material_id', 'codigo_erp', 'material_nome', 'unidade', 'valor_unitario', 'consumo_qtd', 'valor_total_consumo']);
            const chavesAv = Object.keys(consumoMavPorMid).sort(function (a, b) {
                return parseInt(a, 10) - parseInt(b, 10);
            }).filter(function (mid) {
                return (parseFloat(consumoMavPorMid[mid]) || 0) > 0;
            });
            chavesAv.forEach(function (mid) {
                const c = consumoMavPorMid[mid];
                const meta = metaMaterialExport(metaMap, mid);
                const vu = meta.valor_unitario;
                aoaAv.push([mid, meta.codigo_erp, meta.nome, meta.unidade, vu, c, '']);
            });
            aoaAv.push(['', '', 'TOTAL', '', '', '', '']);
            const nMatAv = chavesAv.length;
            (function () {
                const wsAv = XLSX.utils.aoa_to_sheet(aoaAv);
                xlsxAplicarFormulasTabelaMateriaisAvulsos(wsAv, nMatAv);
                xlsxFormatarAbaTabelaMateriais(wsAv);
                XLSX.utils.book_append_sheet(wb, wsAv, nomeAbaUnico('Materiais avulsos'));
            })();
        }

        const ts = new Date().toISOString().slice(0, 19).replace(/[:-]/g, '').replace('T', '_');
        XLSX.writeFile(wb, 'simulacao_indice_material_pc_avulso_' + ts + '.xlsx', { bookType: 'xlsx' });
    }
