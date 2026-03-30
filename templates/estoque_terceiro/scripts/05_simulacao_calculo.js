
    function montarPayloadSimulacao() {
        const itens = [];
        Object.keys(simulacaoItens).forEach((k) => {
            const it = simulacaoItens[k];
            const tipo = it.tipo_item || TIPO_SIM_TANQUE;
            const qtdTotal = Math.max((parseFloat(it.quantidade_simular) || 0), 0);
            const qtdProduzida = Math.max((parseFloat(it.quantidade_produzida) || 0), 0);
            if (qtdTotal <= 0) return;
            const base = {
                chave_item: k,
                tipo_item: tipo,
                grupo_label: it.grupo_label,
                tipo_peca: it.tipo_peca,
                quantidade_total: qtdTotal,
                quantidade_produzida: qtdProduzida
            };
            if (tipo === TIPO_SIM_MATERIAL_AVULSO) {
                base.material_id = it.material_id;
                base.produto_composto_id = null;
            } else {
                base.produto_composto_id = it.produto_composto_id;
            }
            itens.push(base);
        });
        return { itens };
    }

    async function garantirMateriaisDoItem(item) {
        if (!item) return null;
        if (item.tipo_item === TIPO_SIM_MATERIAL_AVULSO && item.material_id != null) {
            const mid = String(item.material_id);
            const one = { [mid]: 1 };
            item.materiais_cache = one;
            return one;
        }
        if (!item.produto_composto_id) return null;
        if (item.materiais_cache && Object.keys(item.materiais_cache).length) {
            return item.materiais_cache;
        }
        const pid = String(item.produto_composto_id);
        if (!estruturaProdutosCache[pid]) {
            await carregarEstruturasProdutos([pid]);
        }
        const estrutura = estruturaProdutosCache[pid] || null;
        if (estrutura) {
            item.materiais_cache = estrutura;
        }
        return estrutura;
    }

    /** Nome exibido para material que só aparece na simulação (ex.: material avulso). */
    function nomeMaterialParaSimulacao(materialKeyStr) {
        var k, it;
        for (k in simulacaoItens) {
            if (!Object.prototype.hasOwnProperty.call(simulacaoItens, k)) continue;
            it = simulacaoItens[k];
            if ((it.tipo_item || '') === TIPO_SIM_MATERIAL_AVULSO && it.material_id != null
                && String(it.material_id) === materialKeyStr) {
                return it.material_nome || ('Material #' + materialKeyStr);
            }
        }
        return 'Material #' + materialKeyStr;
    }

    function criarLinhaComparativoSintetica(materialKeyStr) {
        var midNum = parseInt(materialKeyStr, 10);
        return {
            material_id: isNaN(midNum) ? materialKeyStr : midNum,
            material_nome: nomeMaterialParaSimulacao(materialKeyStr),
            codigo_erp: '',
            tipo: '',
            estoque_sistema: 0,
            estoque_terceiro: 0,
            estoque_terceiro_original: 0,
            diferenca: 0,
            diferenca_percentual: 0,
            valor_diferenca: 0,
            consumo_futuro: 0,
            estoque_futuro: 0,
            estoque_terceiro_futuro: 0,
            diferenca_futura: 0,
            unidade_sistema: '',
            unidade_terceiro: '',
            unidade_convertida: false,
            fator_conversao: 1,
            valor_unitario: 0,
            valor_sistema: 0,
            valor_terceiro: 0,
            valor_estoque_futuro_sistema: 0,
            valor_estoque_futuro_terceiro: 0,
            diferenca_valor_futuro: 0,
            diferenca_futura_terceiro: 0,
            data_estoque_terceiro: '',
            _linha_apenas_simulacao: true
        };
    }

    /** Aplica consumo da simulação em uma linha (mesma lógica da dataSrc do comparativo). */
    function aplicarConsumoSimulacaoRow(row) {
        if (!row) return;
        var consumoFuturoSistema = 0;
        var consumoFuturoTerceiro = 0;
        var materialKey = (row.material_id != null) ? String(row.material_id) : null;
        if (consumoPorMaterialSimulacao && materialKey) {
            consumoFuturoSistema = (consumoPorMaterialSimulacao[materialKey] || 0);
            if (consumoPorMaterialSimulacaoTerceiro) {
                consumoFuturoTerceiro = (consumoPorMaterialSimulacaoTerceiro[materialKey] || 0);
            } else {
                consumoFuturoTerceiro = consumoFuturoSistema;
            }
        }
        var estoqueSistema = parseFloat(row.estoque_sistema) || 0;
        var estoqueTerceiro = parseFloat(row.estoque_terceiro) || 0;
        row.consumo_futuro = consumoFuturoTerceiro;
        row.estoque_futuro = estoqueSistema - consumoFuturoSistema;
        row.estoque_terceiro_futuro = estoqueTerceiro - consumoFuturoTerceiro;
        var valorUnitario = parseFloat(row.valor_unitario) || 0;
        row.valor_estoque_futuro_sistema = row.estoque_futuro * valorUnitario;
        row.valor_estoque_futuro_terceiro = row.estoque_terceiro_futuro * valorUnitario;
        row.diferenca_valor_futuro = row.valor_estoque_futuro_terceiro - row.valor_estoque_futuro_sistema;
        row.diferenca_futura = estoqueTerceiro - row.estoque_futuro;
        row.diferenca_futura_terceiro = row.estoque_terceiro_futuro - row.estoque_futuro;
    }

    function mesclarLinhasSinteticasComparativo(jsonDataArray) {
        if (!Array.isArray(jsonDataArray) || !consumoPorMaterialSimulacao) return;
        var idsPresentes = new Set();
        jsonDataArray.forEach(function (r) {
            if (r && r.material_id != null) idsPresentes.add(String(r.material_id));
        });
        var chaves = new Set(Object.keys(consumoPorMaterialSimulacao));
        if (consumoPorMaterialSimulacaoTerceiro) {
            Object.keys(consumoPorMaterialSimulacaoTerceiro).forEach(function (k) { chaves.add(k); });
        }
        chaves.forEach(function (mk) {
            var cs = consumoPorMaterialSimulacao[mk] || 0;
            var ct = (consumoPorMaterialSimulacaoTerceiro && consumoPorMaterialSimulacaoTerceiro[mk]) || 0;
            if (!(cs > 0 || ct > 0)) return;
            if (idsPresentes.has(mk)) return;
            idsPresentes.add(mk);
            jsonDataArray.push(criarLinhaComparativoSintetica(mk));
        });
    }

    function aplicarConsumoSimulacaoNaTabela(consumoPorMaterialSistema, consumoPorMaterialTerceiro) {
        consumoPorMaterialSimulacao = consumoPorMaterialSistema || null;
        consumoPorMaterialSimulacaoTerceiro = consumoPorMaterialTerceiro || null;
        if (!table) return;
        var idxRem = [];
        table.rows().every(function () {
            var d = this.data();
            if (d && d._linha_apenas_simulacao) idxRem.push(this.index());
        });
        for (var ir = idxRem.length - 1; ir >= 0; ir--) {
            table.row(idxRem[ir]).remove();
        }
        var idsComLinha = new Set();
        table.rows().every(function () {
            var row = this.data();
            if (!row) return;
            aplicarConsumoSimulacaoRow(row);
            this.data(row);
            if (row.material_id != null) idsComLinha.add(String(row.material_id));
        });
        if (consumoPorMaterialSimulacao && consumoPorMaterialSimulacaoTerceiro) {
            var chavesAdd = new Set(Object.keys(consumoPorMaterialSimulacao));
            Object.keys(consumoPorMaterialSimulacaoTerceiro).forEach(function (k) { chavesAdd.add(k); });
            chavesAdd.forEach(function (mk) {
                var cs = consumoPorMaterialSimulacao[mk] || 0;
                var ct = consumoPorMaterialSimulacaoTerceiro[mk] || 0;
                if (!(cs > 0 || ct > 0)) return;
                if (idsComLinha.has(mk)) return;
                var nova = criarLinhaComparativoSintetica(mk);
                aplicarConsumoSimulacaoRow(nova);
                table.row.add(nova);
                idsComLinha.add(mk);
            });
        }
        table.draw(false);
        atualizarCardsEstatisticas(table.rows({ search: 'applied' }).data().toArray());
    }

    function setSimulacaoPendente(val) {
        simulacaoPendente = !!val;
        $('#badgeSimulacaoPendente').toggle(simulacaoPendente);
    }

    async function recalcularSimulacao() {
        const payload = montarPayloadSimulacao();
        if (!payload.itens.length) {
            aplicarConsumoSimulacaoNaTabela(null, null);
            return;
        }

        const produtoIds = Array.from(new Set(
            payload.itens
                .filter((row) => (row.tipo_item || TIPO_SIM_TANQUE) !== TIPO_SIM_MATERIAL_AVULSO && row.produto_composto_id)
                .map((row) => String(row.produto_composto_id))
                .filter(Boolean)
        ));
        try {
            await carregarEstruturasProdutos(produtoIds);
        } catch (e) {
            console.error('Erro ao garantir estruturas antes da simulação:', e);
            alert('Não foi possível carregar a estrutura dos produtos compostos para a simulação.');
            return;
        }

        // Cálculo 100% no frontend a partir da estrutura cacheada
        const consumoPorMaterialSistema = {};
        const consumoPorMaterialTerceiro = {};
        const simularApenasTerceiro = $('#chkSimularApenasTerceiro').is(':checked');
        const semEstrutura = [];
        for (const it of payload.itens) {
            const itemSimulado = simulacaoItens[it.chave_item];
            const tipo = it.tipo_item || TIPO_SIM_TANQUE;

            if (tipo === TIPO_SIM_MATERIAL_AVULSO) {
                const mid = itemSimulado && itemSimulado.material_id != null
                    ? String(itemSimulado.material_id)
                    : (it.material_id != null ? String(it.material_id) : '');
                if (!mid) continue;
                const qtdTotal = Math.max(parseFloat(it.quantidade_total) || 0, 0);
                const qtdProduzida = 0;
                const qtdSistema = simularApenasTerceiro ? 0 : Math.max(qtdTotal - qtdProduzida, 0);
                const qtdTerceiro = qtdTotal;
                const porUn = 1;
                if (qtdSistema > 0) {
                    consumoPorMaterialSistema[mid] = (consumoPorMaterialSistema[mid] || 0) + porUn * qtdSistema;
                }
                if (qtdTerceiro > 0) {
                    consumoPorMaterialTerceiro[mid] = (consumoPorMaterialTerceiro[mid] || 0) + porUn * qtdTerceiro;
                }
                continue;
            }

            const pid = String(it.produto_composto_id);
            let estrutura = itemSimulado ? itemSimulado.materiais_cache : null;
            if (!estrutura) {
                estrutura = await garantirMateriaisDoItem(itemSimulado);
            }
            if (!estrutura) {
                estrutura = estruturaProdutosCache[pid];
            }
            if (!estrutura) {
                semEstrutura.push(pid);
                continue;
            }
            const qtdTotal = Math.max(parseFloat(it.quantidade_total) || 0, 0);
            const qtdProduzida = Math.max(parseFloat(it.quantidade_produzida) || 0, 0);
            const qtdSistema = simularApenasTerceiro ? 0 : Math.max(qtdTotal - qtdProduzida, 0);
            const qtdTerceiro = qtdTotal;
            if (qtdSistema <= 0 && qtdTerceiro <= 0) continue;
            Object.keys(estrutura).forEach((mid) => {
                const porUn = parseFloat(estrutura[mid]) || 0;
                if (porUn === 0) return;
                const key = String(mid);
                if (qtdSistema > 0) {
                    const totalSistema = porUn * qtdSistema;
                    consumoPorMaterialSistema[key] = (consumoPorMaterialSistema[key] || 0) + totalSistema;
                }
                if (qtdTerceiro > 0) {
                    const totalTerceiro = porUn * qtdTerceiro;
                    consumoPorMaterialTerceiro[key] = (consumoPorMaterialTerceiro[key] || 0) + totalTerceiro;
                }
            });
        }

        if (semEstrutura.length) {
            console.warn('Produtos sem estrutura para simulação:', Array.from(new Set(semEstrutura)));
        }

        aplicarConsumoSimulacaoNaTabela(consumoPorMaterialSistema, consumoPorMaterialTerceiro);
    }
