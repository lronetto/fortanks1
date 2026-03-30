
    function getCsrfToken() {
        const meta = document.querySelector('meta[name="csrf-token"]');
        return meta ? meta.getAttribute('content') : '';
    }

    function carregarOpcoesSimulacao() {
        const select = $('#selectSimulacaoOpcao');
        select.prop('disabled', true);
        select.html('<option value="">Carregando opções...</option>');
        return fetch('{{ url_for("estoque_terceiro.api_simulacao_opcoes") }}')
            .then(r => r.json())
            .then(data => {
                if (!data || data.success !== true || !Array.isArray(data.opcoes)) {
                    console.error('Falha ao carregar opções de simulação:', data);
                    select.html('<option value="">Falha ao carregar opções</option>');
                    return;
                }
                opcoesSimulacao = data.opcoes;
                select.empty();
                select.append('<option value="">Selecione...</option>');

                const gruposMap = {};
                const produtoIdsSet = new Set();
                data.opcoes.forEach((o, idx) => {
                    const grupoLabel = (o.grupo_label || 'Sem grupo');
                    if (!gruposMap[grupoLabel]) gruposMap[grupoLabel] = [];
                    gruposMap[grupoLabel].push({ o, idx });
                    if (o.produto_composto_id != null) {
                        produtoIdsSet.add(String(o.produto_composto_id));
                    }
                });

                Object.keys(gruposMap).sort((a, b) => a.localeCompare(b, 'pt-BR')).forEach((grupoLabel) => {
                    const optgroup = $(`<optgroup label="${grupoLabel}"></optgroup>`);
                    gruposMap[grupoLabel].forEach(({ o, idx }) => {
                        const label = `tipo: ${grupoLabel} | Tipo ${o.tipo_peca} | ${o.produto_composto_nome}`;
                        optgroup.append(`<option value="${idx}">${label}</option>`);
                    });
                    select.append(optgroup);
                });

                // Pré-carrega estrutura dos produtos (cache)
                const produtoIds = Array.from(produtoIdsSet).filter(Boolean);
                carregarEstruturasProdutos(produtoIds).catch(err => {
                    console.error('Erro ao pré-carregar estruturas:', err);
                });
            })
            .catch(err => {
                console.error('Erro ao carregar opções de simulação:', err);
                select.html('<option value="">Erro ao carregar opções</option>');
            })
            .finally(() => {
                select.prop('disabled', false);
            });
    }

    function carregarMateriaisParaSimulacaoAvulsa() {
        const sel = $('#selectMaterialAvulsoSimulacao');
        sel.prop('disabled', true).html('<option value="">Carregando...</option>');
        $.getJSON('{{ url_for("material.listar_json") }}')
            .done(function (data) {
                sel.empty().append('<option value="">Selecione o material...</option>');
                if (!Array.isArray(data)) {
                    sel.append('<option value="">Lista inválida</option>');
                    return;
                }
                data.sort(function (a, b) {
                    return (a.nome || '').localeCompare(b.nome || '', 'pt-BR');
                });
                data.forEach(function (m) {
                    if (!m || m.id == null) return;
                    const nome = (m.codigo ? m.codigo + ' — ' : '') + (m.nome || '');
                    sel.append($('<option></option>').attr('value', m.id).text(nome));
                });
            })
            .fail(function () {
                sel.html('<option value="">Erro ao carregar materiais</option>');
            })
            .always(function () {
                sel.prop('disabled', false);
            });
    }

    function carregarProdutosCompostosParaSimulacaoAvulsa() {
        const sel = $('#selectProdutoAvulsoSimulacao');
        sel.prop('disabled', true).html('<option value="">Carregando...</option>');
        const url = '{{ url_for("produto_composto.api_datatables") }}'
            + '?draw=1&start=0&length=3000&search[value]=&order[0][column]=3&order[0][dir]=asc';
        fetch(url)
            .then(function (r) { return r.json(); })
            .then(function (resp) {
                sel.empty().append('<option value="">Selecione o produto composto...</option>');
                const rows = (resp && resp.data) ? resp.data : [];
                rows.forEach(function (p) {
                    if (!p || p.id == null) return;
                    const nome = (p.nome || ('#' + p.id));
                    sel.append($('<option></option>').attr('value', p.id).text(nome));
                });
            })
            .catch(function () {
                sel.html('<option value="">Erro ao carregar produtos</option>');
            })
            .finally(function () {
                sel.prop('disabled', false);
            });
    }

    function carregarEstruturasProdutos(produtoIds) {
        const ids = (produtoIds || []).map(v => String(v)).filter(Boolean);
        if (!ids.length) return Promise.resolve();
        const faltantes = ids.filter(pid => !estruturaProdutosCache[pid]);
        if (!faltantes.length) return Promise.resolve();

        estruturasLoading = true;
        return fetch(`{{ url_for("estoque_terceiro.api_simulacao_produtos_estrutura") }}?ids=${encodeURIComponent(faltantes.join(','))}`)
            .then(r => r.json())
            .then(resp => {
                if (!resp || resp.success !== true) {
                    throw new Error((resp && resp.message) ? resp.message : 'Falha ao carregar estrutura dos produtos.');
                }
                estruturaProdutosCache = Object.assign({}, estruturaProdutosCache, resp.estruturas || {});
            })
            .finally(() => {
                estruturasLoading = false;
            });
    }

    function renderTabelaSimulacaoManual() {
        const tbody = $('#tabelaSimulacaoManual tbody');
        tbody.empty();
        const keys = Object.keys(simulacaoItens);
        if (!keys.length) {
            tbody.append(`
                <tr class="text-muted" id="linhaVaziaSimulacaoManual">
                    <td colspan="8">Nenhum item adicionado na simulação.</td>
                </tr>
            `);
            return;
        }

        keys.forEach((k) => {
            const it = simulacaoItens[k];
            const tipo = it.tipo_item || TIPO_SIM_TANQUE;
            const qtdTotal = Math.max((parseFloat(it.quantidade_simular) || 0), 0);
            const qtdProduzida = Math.max((parseFloat(it.quantidade_produzida) || 0), 0);
            const aProduzir = Math.max(qtdTotal - qtdProduzida, 0);
            let colGrupo = it.grupo_label || 'Sem grupo';
            let colTipo = `<span class="badge bg-secondary">${it.tipo_peca}</span>`;
            let colNome = it.produto_composto_nome || '';
            let colProduzidas = (it.quantidade_produzida || 0).toLocaleString('pt-BR');
            if (tipo === TIPO_SIM_MATERIAL_AVULSO) {
                colGrupo = 'Avulso';
                colTipo = '<span class="badge bg-info text-dark">Material</span>';
                colNome = it.material_nome || ('Material #' + (it.material_id || ''));
                colProduzidas = '—';
            } else if (tipo === TIPO_SIM_PRODUTO_AVULSO) {
                colGrupo = it.grupo_label || 'Avulso';
                colTipo = '<span class="badge bg-primary">Prod. composto</span>';
            }
            tbody.append(`
                <tr data-key="${k}">
                    <td>${colGrupo}</td>
                    <td>${colTipo}</td>
                    <td>${colNome}</td>
                    <td class="text-end">${colProduzidas}</td>
                    <td class="text-end">
                        <input type="number" class="form-control form-control-sm input-qtd-total text-end" min="0" step="${tipo === TIPO_SIM_MATERIAL_AVULSO ? 'any' : '1'}"
                               value="${it.quantidade_simular}" style="max-width: 140px; margin-left:auto;">
                    </td>
                    <td class="text-end"><strong>${aProduzir.toLocaleString('pt-BR')}</strong></td>
                    <td class="text-end">
                        ${tipoItemSemPesoSimulacao(tipo)
                            ? '<span class="text-muted" title="Avulso: consumo por quantidade / estrutura (sem peso na simulação e na planilha de índices)">—</span>'
                            : `<input type="number" class="form-control form-control-sm input-peso-simulacao text-end" min="0" step="0.01" max="100"
                               placeholder="auto"
                               value="${(it.peso != null && String(it.peso).trim() !== '') ? String(it.peso).replace(/"/g, '') : ''}" style="max-width: 96px; margin-left:auto;">`}
                    </td>
                    <td class="text-center">
                        <button type="button" class="btn btn-sm btn-outline-danger btn-remover-simulacao" title="Remover">
                            <i class="fas fa-trash"></i>
                        </button>
                    </td>
                </tr>
            `);
        });
    }

    /**
     * Peso efetivo (0–100) só para linhas de tanque (produto composto vinculado ao tanque).
     * Material avulso e produto composto avulso: peso 0 (não entram na ponderação; mesmo critério da planilha de índices).
     */
    function calcularPesosEfetivosSimulacao() {
        const keys = Object.keys(simulacaoItens);
        const out = {};
        keys.forEach(function (k) { out[k] = 0; });
        const keysPc = keys.filter(function (k) {
            return !tipoItemSemPesoSimulacao(simulacaoItens[k].tipo_item || TIPO_SIM_TANQUE);
        });
        const n = keysPc.length;
        if (n === 0) return out;
        const entries = keysPc.map(function (k) {
            const raw = simulacaoItens[k].peso;
            const s = raw === null || raw === undefined ? '' : String(raw).trim();
            if (s === '') return { key: k, explicit: null };
            const v = parseFloat(String(raw).replace(',', '.'));
            return { key: k, explicit: isNaN(v) ? null : v };
        });
        const allUnweighted = entries.every(function (e) { return e.explicit === null; });
        if (allUnweighted) {
            const p = 100 / n;
            keysPc.forEach(function (k) { out[k] = p; });
            return out;
        }
        let sumExp = 0;
        let countUn = 0;
        entries.forEach(function (e) {
            if (e.explicit === null) countUn++;
            else sumExp += e.explicit;
        });
        if (sumExp > 100 && countUn > 0) {
            const factor = 100 / sumExp;
            entries.forEach(function (e) {
                out[e.key] = e.explicit === null ? 0 : e.explicit * factor;
            });
            return out;
        }
        if (countUn > 0) {
            const rest = Math.max(0, 100 - sumExp);
            const each = countUn > 0 ? rest / countUn : 0;
            entries.forEach(function (e) {
                out[e.key] = e.explicit === null ? each : e.explicit;
            });
            return out;
        }
        if (sumExp > 0) {
            const factor = 100 / sumExp;
            entries.forEach(function (e) {
                out[e.key] = (e.explicit || 0) * factor;
            });
        } else {
            keysPc.forEach(function (k) { out[k] = 100 / n; });
        }
        return out;
    }

    function itemPayloadParaCalculo(k) {
        const it = simulacaoItens[k];
        if (!it) return null;
        const tipo = it.tipo_item || TIPO_SIM_TANQUE;
        const qtdTotal = Math.max(parseFloat(it.quantidade_simular) || 0, 0);
        const qtdProduzida = Math.max(parseFloat(it.quantidade_produzida) || 0, 0);
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
        return base;
    }

    async function consumoTerceiroPorItemSimulacao(itPayload, itemSimulado) {
        const out = {};
        if (!itPayload) return out;
        const tipo = itPayload.tipo_item || TIPO_SIM_TANQUE;
        if (tipo === TIPO_SIM_MATERIAL_AVULSO) {
            const mid = itemSimulado && itemSimulado.material_id != null
                ? String(itemSimulado.material_id)
                : (itPayload.material_id != null ? String(itPayload.material_id) : '');
            if (!mid) return out;
            const qtdTotal = Math.max(parseFloat(itPayload.quantidade_total) || 0, 0);
            const qtdTerceiro = qtdTotal;
            if (qtdTerceiro > 0) out[mid] = (out[mid] || 0) + qtdTerceiro;
            return out;
        }
        const pid = String(itPayload.produto_composto_id);
        let estrutura = itemSimulado ? itemSimulado.materiais_cache : null;
        if (!estrutura) estrutura = await garantirMateriaisDoItem(itemSimulado);
        if (!estrutura) estrutura = estruturaProdutosCache[pid];
        if (!estrutura) return out;
        const qtdTotal = Math.max(parseFloat(itPayload.quantidade_total) || 0, 0);
        const qtdTerceiro = qtdTotal;
        if (qtdTerceiro <= 0) return out;
        Object.keys(estrutura).forEach(function (mid) {
            const porUn = parseFloat(estrutura[mid]) || 0;
            if (porUn === 0) return;
            const key = String(mid);
            out[key] = (out[key] || 0) + porUn * qtdTerceiro;
        });
        return out;
    }
