/**
 * Código JavaScript para a página de Notas Fiscais
 * Gerencia todas as interações, modais e chamadas AJAX
 */

document.addEventListener('DOMContentLoaded', function() {
    // URLs base possíveis para as APIs, em ordem de tentativa
    const possiveisURLs = [
        '/nota_fiscal/api_',
        '/api/nota_fiscal/',
        '/nota-fiscal/api/',
        '/api/notas-fiscais/'
    ];
    
    // Objeto para armazenar os endpoints testados e válidos
    const urlsValidas = {};
    
    // Função para testar as URLs até encontrar uma válida
    async function obterURLValida(endpoint) {
        // Se já testamos este endpoint antes, retorna a URL válida
        if (urlsValidas[endpoint]) {
            return urlsValidas[endpoint];
        }
        
        // Testa cada possível prefixo até encontrar um que funcione
        for (const baseURL of possiveisURLs) {
            const urlTeste = `${baseURL}${endpoint}`;
            console.log(`Testando URL: ${urlTeste}`);
            
            try {
                // Faz uma solicitação HEAD para verificar se o endpoint existe
                const response = await fetch(urlTeste, { method: 'HEAD' });
                if (response.ok) {
                    console.log(`URL válida encontrada: ${urlTeste}`);
                    urlsValidas[endpoint] = urlTeste;
                    return urlTeste;
                }
            } catch (error) {
                console.log(`Erro ao testar ${urlTeste}:`, error);
            }
        }
        
        // Se nenhuma URL for válida, retorna o primeiro formato como fallback
        console.warn(`Nenhuma URL válida encontrada para ${endpoint}, usando padrão.`);
        const urlPadrao = `${possiveisURLs[0]}${endpoint}`;
        urlsValidas[endpoint] = urlPadrao;
        return urlPadrao;
    }
    
    // Função wrapper para fetch que tenta descobrir a URL correta
    async function fetchAPI(endpoint, options = {}) {
        try {
            // Debug: mostrar a URL atual sendo chamada
            const urlCompleta = `/nota_fiscal/${endpoint}`;
            console.log(`Chamando API: ${urlCompleta}`);
            
            // Fazer a requisição com a URL fixa por enquanto
            const response = await fetch(urlCompleta, options);
            console.log(`Resposta de ${urlCompleta}:`, response.status);
            
            if (!response.ok) {
                throw new Error(`Erro de rede: ${response.status}`);
            }
            
            try {
                const data = await response.json();
                return data;
            } catch (e) {
                console.error('Erro ao fazer parse do JSON:', e);
                throw new Error('Resposta inválida do servidor: não é um JSON válido');
            }
        } catch (error) {
            console.error(`Erro na chamada para ${endpoint}:`, error);
            throw error;
        }
    }
    
    // Verificar se o jQuery está disponível
    if (typeof jQuery === 'undefined') {
        console.error('jQuery não está carregado');
        return;
    }

    // Verificar se o DataTables está disponível
    if (typeof $.fn.DataTable === 'undefined') {
        console.warn('DataTables não está disponível, a tabela funcionará sem recursos avançados');
        // Não inicializar o DataTable para evitar erros
    } else {
        // Adicionar o plugin de ordenação para datas no formato brasileiro
        $.extend($.fn.dataTable.ext.type.order, {
            "date-br-pre": function(data) {
                if (!data) {
                    return 0;
                }
                
                // Converter formato dd/mm/yyyy para formato sortável
                const partes = data.split('/');
                if (partes.length < 3) {
                    return 0;
                }
                
                return new Date(partes[2], partes[1] - 1, partes[0]).getTime();
            },
            
            // Ordenação para valores monetários em formato brasileiro
            "currency-br-pre": function(data) {
                // Remover 'R$' e qualquer caractere não numérico exceto o ponto decimal
                if (!data) {
                    return 0;
                }
                
                const valor = data.replace(/[^\d,.-]/g, '').replace(',', '.');
                return parseFloat(valor) || 0;
            }
        });
        
        // Inicialização da tabela com DataTables
        try {
            const tabelaNotasFiscais = $('#tabelaNotasFiscais').DataTable({
                language: {
                    url: '/static/js/plugins/datatables/pt-BR.json'
                },
                order: [[1, 'desc']], // Ordenar por data de emissão (desc)
                pageLength: 100,
                responsive: false,
                paging: false,
                searching: false,
                info: false,
                columnDefs: [
                    {
                        // Coluna de data (índice 1)
                        targets: 1,
                        type: 'date-br'
                    },
                    {
                        // Coluna de número da NF (índice 0)
                        targets: 0,
                        type: 'num'
                    },
                    {
                        // Coluna de valor total (índice 3)
                        targets: 3,
                        type: 'currency-br'
                    }
                ]
            });
        } catch (error) {
            console.error('Erro ao inicializar DataTable:', error);
        }
    }

    // Verificar se o Select2 está disponível
    if (typeof $.fn.select2 !== 'undefined') {
        // Inicialização dos selects com Select2
        $('.select2').select2({
            theme: 'bootstrap4',
            width: '100%'
        });
    } else {
        console.warn('Select2 não está disponível');
    }

    // ===== MODAL DE VISUALIZAÇÃO DE ITENS =====
    // Carrega itens da nota fiscal para visualização
    document.querySelectorAll('.visualizar-itens').forEach(function(button) {
        button.addEventListener('click', function() {
            const notaId = this.getAttribute('data-id');
            carregarItensModal(notaId, 'visualizar');
        });
    });

    // ===== MODAL DE IMPORTAÇÃO DE ITENS =====
    // Carrega itens e centros de custo para importação
    

    // Selecionar/deselecionar todos os itens
    const selecionarTodos = document.getElementById('selecionarTodos');
    if (selecionarTodos) {
        selecionarTodos.addEventListener('change', function() {
            const isChecked = this.checked;
            document.querySelectorAll('.item-checkbox').forEach(function(checkbox) {
                checkbox.checked = isChecked;
            });
        });
    }

    // Submissão do formulário de importação
    const formImportacao = document.getElementById('formImportacao');
    if (formImportacao) {
        formImportacao.addEventListener('submit', function(e) {
            e.preventDefault();
            
            const centroCusto = document.getElementById('centro_custo_id').value;
            if (!centroCusto) {
                mostrarAlerta('Erro', 'Selecione um centro de custo para importação.', 'error');
                return false;
            }
            
            const itensSelecionados = document.querySelectorAll('.item-checkbox:checked').length;
            if (itensSelecionados === 0) {
                mostrarAlerta('Erro', 'Selecione pelo menos um item para importação.', 'error');
                return false;
            }
            
            // Verifica se todos os itens selecionados têm material vinculado
            let todosVinculados = true;
            document.querySelectorAll('.item-checkbox:checked').forEach(function(checkbox) {
                const itemId = checkbox.value;
                const materialId = document.getElementById(`material_id_${itemId}`).value;
                if (!materialId) {
                    todosVinculados = false;
                }
            });
            
            if (!todosVinculados) {
                mostrarAlerta('Erro', 'Todos os itens selecionados precisam ter um material vinculado.', 'error');
                return false;
            }
            
            // Confirmação antes de importar
            if (typeof Swal !== 'undefined') {
                Swal.fire({
                    title: 'Confirmar importação',
                    text: `Deseja importar ${itensSelecionados} item(ns) para o estoque?`,
                    icon: 'question',
                    showCancelButton: true,
                    confirmButtonText: 'Sim, importar',
                    cancelButtonText: 'Cancelar'
                }).then((result) => {
                    if (result.isConfirmed) {
                        importarItens();
                    }
                });
            } else {
                if (confirm(`Deseja importar ${itensSelecionados} item(ns) para o estoque?`)) {
                    importarItens();
                }
            }
        });
    }

    // ===== MODAL DE SELEÇÃO DE MATERIAL =====
    // Abrir modal para vincular material
    document.addEventListener('click', function(e) {
        if (e.target && e.target.closest('.btn-vincular-material')) {
            const button = e.target.closest('.btn-vincular-material');
            const itemId = button.getAttribute('data-item-id');
            document.getElementById('item_id_para_vincular').value = itemId;
            
            const buscarMaterial = document.getElementById('buscarMaterial');
            buscarMaterial.value = '';
            buscarMaterial.focus();
            
            document.getElementById('corpoTabelaMateriais').innerHTML = '';
            
            // Abre o modal usando Bootstrap 5
            const modal = new bootstrap.Modal(document.getElementById('modalSelecionarMaterial'));
            modal.show();
        }
    });

    // Buscar materiais
    let timeoutBusca;
    const buscarMaterial = document.getElementById('buscarMaterial');
    if (buscarMaterial) {
        buscarMaterial.addEventListener('keyup', function() {
            clearTimeout(timeoutBusca);
            const termo = this.value;
            
            if (termo.length < 3) return;
            
            timeoutBusca = setTimeout(function() {
                buscarMateriais(termo);
            }, 500);
        });
    }

    // Vincular material ao item
    document.addEventListener('click', function(e) {
        if (e.target && e.target.closest('.btn-selecionar-material')) {
            const button = e.target.closest('.btn-selecionar-material');
            const materialId = button.getAttribute('data-material-id');
            const materialNome = button.getAttribute('data-material-nome');
            const materialUnidade = button.getAttribute('data-material-unidade');
            const itemId = document.getElementById('item_id_para_vincular').value;
            
            // Obter a unidade do item
            const unidadeElemento = document.getElementById(`unidade_${itemId}`);
            const itemUnidade = unidadeElemento ? unidadeElemento.textContent : '';
            
            // Vincular material ao item
            document.getElementById(`material_id_${itemId}`).value = materialId;
            
            const materialNomeElemento = document.getElementById(`material_nome_${itemId}`);
            if (materialNomeElemento) materialNomeElemento.textContent = materialNome;
            
            const btnVincular = document.getElementById(`btn_vincular_${itemId}`);
            if (btnVincular) {
                btnVincular.innerHTML = '<i class="fas fa-edit"></i>';
                btnVincular.classList.remove('btn-primary');
                btnVincular.classList.add('btn-warning');
            }
            
            // Fechar modal de seleção
            const modalSelecionar = bootstrap.Modal.getInstance(document.getElementById('modalSelecionarMaterial'));
            if (modalSelecionar) modalSelecionar.hide();
            
            // Verificar se precisa de conversão de unidades
            if (materialUnidade && itemUnidade && !compararUnidades(itemUnidade, materialUnidade)) {
                abrirModalConversao(itemId, materialId, itemUnidade, materialUnidade);
            }
        }
    });
    function compararUnidades(unidadeNota, unidadeMaterial) {
        fetch('/notas-fiscais/api/comparar_unidades', {
            method: 'POST',
            body: JSON.stringify({unidadeNota, unidadeMaterial})
        })
        .then(response => response.json())
        .then(data => {
            if (data.success) {
                return true;
            } else {
                return false;
            }
        })
        .catch(error => {
            console.error('Erro ao comparar unidades:', error);
            return false;
        });
    }
                

    // ===== MODAL DE CONVERSÃO DE UNIDADES =====
    // Abrir modal de conversão de unidades
    function abrirModalConversao(itemId, materialId, unidadeNota, unidadeMaterial) {
        document.getElementById('conversao_item_id').value = itemId;
        document.getElementById('conversao_material_id').value = materialId;
        
        const unidadeNotaElemento = document.getElementById('unidadeNota');
        if (unidadeNotaElemento) unidadeNotaElemento.textContent = unidadeNota;
        
        const unidadeMaterialElemento = document.getElementById('unidadeMaterial');
        if (unidadeMaterialElemento) unidadeMaterialElemento.textContent = unidadeMaterial;
        
        const unidadeOrigemEx = document.getElementById('unidadeOrigemEx');
        if (unidadeOrigemEx) unidadeOrigemEx.textContent = unidadeNota;
        
        const unidadeDestinoEx = document.getElementById('unidadeDestinoEx');
        if (unidadeDestinoEx) unidadeDestinoEx.textContent = unidadeMaterial;
        
        const unidadeNovaDesc = document.getElementById('unidadeNovaDesc');
        if (unidadeNovaDesc) unidadeNovaDesc.textContent = unidadeMaterial;
        
        // Carregar conversões existentes
        carregarConversoesMaterial(materialId);
        
        // Abrir modal usando Bootstrap 5
        const modal = new bootstrap.Modal(document.getElementById('modalConversaoUnidades'));
        modal.show();
    }

    // Aplicar conversão de unidades
    const btnAplicarConversao = document.getElementById('btnAplicarConversao');
    if (btnAplicarConversao) {
        btnAplicarConversao.addEventListener('click', function() {
            const itemId = document.getElementById('conversao_item_id').value;
            const materialId = document.getElementById('conversao_material_id').value;
            const unidadeConversaoId = document.getElementById('unidade_conversao_id').value;
            const fatorConversao = document.getElementById('fator_conversao').value;
            
            if (!unidadeConversaoId && (!fatorConversao || fatorConversao <= 0)) {
                mostrarAlerta('Erro', 'Informe um fator de conversão válido ou selecione uma conversão existente.', 'error');
                return;
            }
            
            const formData = new FormData();
            formData.append('csrf_token', document.querySelector('input[name="csrf_token"]').value);
            formData.append('item_id', itemId);
            formData.append('material_id', materialId);
            formData.append('unidade_conversao_id', unidadeConversaoId);
            formData.append('fator_conversao', fatorConversao);
            
            fetch('/notas-fiscais/api/aplicar_conversao', {
                method: 'POST',
                body: formData
            })
            .then(response => {
                if (!response.ok) {
                    throw new Error(`Erro de rede: ${response.status}`);
                }
                return response.json().catch(e => {
                    console.error('Erro ao fazer parse do JSON:', e);
                    throw new Error('Resposta inválida do servidor: não é um JSON válido');
                });
            })
            .then(data => {
                if (data.success) {
                    const modalConversao = bootstrap.Modal.getInstance(document.getElementById('modalConversaoUnidades'));
                    if (modalConversao) modalConversao.hide();
                    mostrarAlerta('Sucesso', 'Conversão aplicada com sucesso.', 'success');
                } else {
                    mostrarAlerta('Erro', data.message, 'error');
                }
            })
            .catch(error => {
                console.error('Erro ao aplicar conversão:', error);
                mostrarAlerta('Erro', `Ocorreu um erro ao aplicar a conversão: ${error.message}`, 'error');
            })
            .finally(() => {
                if (typeof Swal !== 'undefined') {
                    Swal.close();
                }
            });
        });
    }

    
    // ===== MODAL DE EXCLUSÃO DE NOTA FISCAL =====
    // Abrir modal de exclusão
    document.querySelectorAll('.excluir-nota').forEach(function(button) {
        button.addEventListener('click', function() {
            const notaId = this.getAttribute('data-id');
            const numeroNota = this.getAttribute('data-numero');
            
            document.getElementById('excluir_nf_id').value = notaId;
            document.getElementById('numeroNotaExcluir').textContent = numeroNota;
            
            // Abrir modal usando Bootstrap 5
            const modal = new bootstrap.Modal(document.getElementById('modalExcluirNota'));
            modal.show();
        });
    });

    // Confirmar exclusão de nota fiscal
    const btnConfirmarExclusao = document.getElementById('btnConfirmarExclusao');
    if (btnConfirmarExclusao) {
        btnConfirmarExclusao.addEventListener('click', function() {
            const notaId = document.getElementById('excluir_nf_id').value;
            
            const formData = new FormData();
            formData.append('csrf_token', document.querySelector('input[name="csrf_token"]').value);
            formData.append('nf_id', notaId);
            
            fetch('/nota_fiscal/api_excluir', {
                method: 'POST',
                body: formData
            })
            .then(response => {
                if (!response.ok) {
                    throw new Error(`Erro de rede: ${response.status}`);
                }
                return response.json().catch(e => {
                    console.error('Erro ao fazer parse do JSON:', e);
                    throw new Error('Resposta inválida do servidor: não é um JSON válido');
                });
            })
            .then(data => {
                if (data.success) {
                    const modalExcluir = bootstrap.Modal.getInstance(document.getElementById('modalExcluirNota'));
                    if (modalExcluir) modalExcluir.hide();
                    
                    mostrarAlerta('Sucesso', data.message, 'success', function() {
                        // Recarregar a página após exclusão
                        window.location.reload();
                    });
                } else {
                    mostrarAlerta('Erro', data.message, 'error');
                }
            })
            .catch(error => {
                console.error('Erro ao excluir nota fiscal:', error);
                mostrarAlerta('Erro', `Ocorreu um erro ao excluir a nota fiscal: ${error.message}`, 'error');
            });
        });
    }

    // ===== FUNÇÕES AUXILIARES =====
    // Carrega itens da nota fiscal
    function carregarItensModal(notaId, modo) {
        console.log(`Carregando itens para nota ID: ${notaId}, modo: ${modo}`);
        
        // Mostrar carregamento
        const corpoTabela = modo === 'visualizar' ? 'corpoTabelaItens' : 'corpoTabelaItensImportacao';
        document.getElementById(corpoTabela).innerHTML = '<tr><td colspan="7" class="text-center">Carregando itens...</td></tr>';
        
        // Abrir o modal
        const modalId = modo === 'visualizar' ? 'modalVisualizarItens' : 'modalImportarItens';
        const modal = new bootstrap.Modal(document.getElementById(modalId));
        modal.show();
        
        // Testar diferentes formatos de URL
        const urls = [
            `/notas-fiscais/api/itens/${notaId}`,
            `/api/nota_fiscal/itens/${notaId}`,
            `/api/notas-fiscais/${notaId}/itens`,
            `/nota_fiscal/itens/${notaId}`
        ];
        
        // Tentar cada URL até uma funcionar
        tentarURLs(urls, 0);
        
        function tentarURLs(urls, index) {
            if (index >= urls.length) {
                // Todos os formatos falharam
                document.getElementById(corpoTabela).innerHTML = `<tr><td colspan="7" class="text-center text-danger">Erro ao carregar itens: Não foi possível conectar ao servidor.</td></tr>`;
                return;
            }
            
            const url = urls[index];
            console.log(`Tentando URL (${index+1}/${urls.length}): ${url}`);
            
            fetch(url)
                .then(response => {
                    console.log(`Resposta para ${url}:`, response.status);
                    if (!response.ok) {
                        // Se esta URL falhou, tente a próxima
                        throw new Error(`Erro de rede: ${response.status}`);
                    }
                    return response.json().catch(e => {
                        console.error('Erro ao analisar JSON:', e);
                        throw new Error('Resposta inválida do servidor');
                    });
                })
                .then(data => {
                    console.log('Dados recebidos:', data);
                    if (data.success) {
                        if (modo === 'visualizar') {
                            preencherTabelaVisualizacao(data.itens);
                        } else {
                            preencherTabelaImportacao(data.itens);
                        }
                        // Registrar URL bem-sucedida para uso futuro
                        console.log(`URL bem-sucedida: ${url}`);
                    } else {
                        document.getElementById(corpoTabela).innerHTML = `<tr><td colspan="7" class="text-center text-danger">${data.message || 'Erro ao carregar itens.'}</td></tr>`;
                    }
                })
                .catch(error => {
                    console.warn(`Falha ao usar ${url}:`, error);
                    // Tentar próxima URL
                    tentarURLs(urls, index + 1);
                });
        }
    }

    // Preenche a tabela de visualização de itens
    function preencherTabelaVisualizacao(itens) {
        if (!itens || itens.length === 0) {
            document.getElementById('corpoTabelaItens').innerHTML = '<tr><td colspan="7" class="text-center">Nenhum item encontrado.</td></tr>';
            return;
        }
        
        // Armazenar todos os itens em uma variável global para uso no filtro
        window.todosOsItensNota = itens;
        
        renderizarItensVisualizacao(itens);
        
        // Configurar eventos de filtro
        configurarFiltroItens();
    }
    
    // Função para renderizar os itens na tabela de visualização
    function renderizarItensVisualizacao(itens) {
        let html = '';
        
        itens.forEach(function(item) {
            const valorUnitario = parseFloat(item.valor_unitario).toLocaleString('pt-BR', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
            const valorTotal = parseFloat(item.valor_total).toLocaleString('pt-BR', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
            
            let status = '';
            if (item.importado_estoque) {
                status = '<span class="badge bg-success">Importado</span>';
            } else if (item.material_id) {
                status = '<span class="badge bg-warning">Vinculado</span>';
            } else {
                status = '<span class="badge bg-danger">Pendente</span>';
            }
            
            html += `
                <tr>
                    <td>${item.codigo || '-'}</td>
                    <td>${item.cfop || '-'}</td>
                    <td>${item.descricao}</td>
                    <td>${item.quantidade}</td>
                    <td>${item.unidade}</td>
                    <td>R$ ${valorUnitario}</td>
                    <td>R$ ${valorTotal}</td>
                    <td>${status}</td>
                </tr>
            `;
        });
        
        document.getElementById('corpoTabelaItens').innerHTML = html;
    }
    
    // Configurar eventos para o filtro de itens
   

    

    
    // Carrega centros de custo
    
    // Busca materiais por termo
    function buscarMateriais(termo) {
        document.getElementById('corpoTabelaMateriais').innerHTML = '<tr><td colspan="4" class="text-center">Buscando materiais...</td></tr>';
        
        // Testar diferentes formatos de URL
        const urls = [
            `/notas-fiscais/api/materiais?termo=${encodeURIComponent(termo)}`,
            `/api/nota_fiscal/materiais?termo=${encodeURIComponent(termo)}`,
            `/api/notas-fiscais/materiais?termo=${encodeURIComponent(termo)}`,
            `/nota_fiscal/materiais?termo=${encodeURIComponent(termo)}`
        ];
        
        // Tentar cada URL até uma funcionar
        tentarURLs(urls, 0);
        
        function tentarURLs(urls, index) {
            if (index >= urls.length) {
                // Todos os formatos falharam
                document.getElementById('corpoTabelaMateriais').innerHTML = '<tr><td colspan="4" class="text-center text-danger">Não foi possível conectar ao servidor.</td></tr>';
                return;
            }
            
            const url = urls[index];
            console.log(`Tentando URL para materiais (${index+1}/${urls.length}): ${url}`);
            
            fetch(url)
                .then(response => {
                    console.log(`Resposta para ${url}:`, response.status);
                    if (!response.ok) {
                        // Se esta URL falhou, tente a próxima
                        throw new Error(`Erro de rede: ${response.status}`);
                    }
                    return response.json().catch(e => {
                        console.error('Erro ao analisar JSON:', e);
                        throw new Error('Resposta inválida do servidor');
                    });
                })
                .then(data => {
                    if (data.success) {
                        if (!data.materiais || data.materiais.length === 0) {
                            document.getElementById('corpoTabelaMateriais').innerHTML = '<tr><td colspan="4" class="text-center">Nenhum material encontrado.</td></tr>';
                            return;
                        }
                        
                        let html = '';
                        
                        data.materiais.forEach(function(material) {
                            html += `
                                <tr>
                                    <td>${material.id}</td>
                                    <td>${material.nome}</td>
                                    <td>${material.unidade}</td>
                                    <td>
                                        <button type="button" class="btn btn-sm btn-success btn-selecionar-material" 
                                                data-material-id="${material.id}" 
                                                data-material-nome="${material.descricao}" 
                                                data-material-unidade="${material.unidade}">
                                            <i class="fas fa-check"></i>
                                        </button>
                                    </td>
                                </tr>
                            `;
                        });
                        
                        document.getElementById('corpoTabelaMateriais').innerHTML = html;
                        
                        // Registrar URL bem-sucedida para uso futuro
                        console.log(`URL bem-sucedida para materiais: ${url}`);
                    } else {
                        document.getElementById('corpoTabelaMateriais').innerHTML = `<tr><td colspan="4" class="text-center text-danger">${data.message}</td></tr>`;
                    }
                })
                .catch(error => {
                    console.warn(`Falha ao usar ${url}:`, error);
                    // Tentar próxima URL
                    tentarURLs(urls, index + 1);
                });
        }
    }

    // Carrega conversões de unidades do material
    function carregarConversoesMaterial(materialId) {
        fetch(`/notas-fiscais/api/unidades_conversao/${materialId}`)
            .then(response => {
                if (!response.ok) {
                    throw new Error(`Erro de rede: ${response.status}`);
                }
                return response.json().catch(e => {
                    console.error('Erro ao fazer parse do JSON:', e);
                    throw new Error('Resposta inválida do servidor: não é um JSON válido');
                });
            })
            .then(data => {
                if (data.success && data.conversoes) {
                    let options = '<option value="">Selecione uma conversão existente</option>';
                    
                    data.conversoes.forEach(function(conversao) {
                        options += `<option value="${conversao.id}">${conversao.descricao} (Fator: ${conversao.fator})</option>`;
                    });
                    
                    document.getElementById('unidade_conversao_id').innerHTML = options;
                }
            })
            .catch(error => {
                console.error('Erro ao carregar conversões:', error);
            });
    }

    // Exibe alerta com SweetAlert2 ou alert normal
    function mostrarAlerta(titulo, mensagem, tipo, callback) {
        if (typeof Swal !== 'undefined') {
            Swal.fire({
                title: titulo,
                text: mensagem,
                icon: tipo,
                confirmButtonText: 'OK'
            }).then(() => {
                if (callback) callback();
            });
        } else {
            alert(`${titulo}: ${mensagem}`);
            if (callback) callback();
        }
    }

    // Exibe carregamento com SweetAlert2 ou mensagem normal
    function mostrarCarregando(mensagem) {
        if (typeof Swal !== 'undefined') {
            Swal.fire({
                title: 'Aguarde',
                text: mensagem,
                allowOutsideClick: false,
                allowEscapeKey: false,
                showConfirmButton: false,
                willOpen: () => {
                    Swal.showLoading();
                }
            });
        } else {
            console.log(`Carregando: ${mensagem}`);
        }
    }

    // Adicionar Bootstrap manualmente se necessário
    if (typeof bootstrap === 'undefined') {
        console.warn('Bootstrap não está disponível, adicionando suporte básico para modais');
        // Implementação mínima para modais
        window.bootstrap = {
            Modal: class Modal {
                constructor(element) {
                    this.element = element;
                }
                show() {
                    this.element.style.display = 'block';
                    this.element.classList.add('show');
                    document.body.classList.add('modal-open');
                    const backdrop = document.createElement('div');
                    backdrop.className = 'modal-backdrop show';
                    document.body.appendChild(backdrop);
                }
                hide() {
                    this.element.style.display = 'none';
                    this.element.classList.remove('show');
                    document.body.classList.remove('modal-open');
                    const backdrop = document.querySelector('.modal-backdrop');
                    if (backdrop) backdrop.remove();
                }
                static getInstance(element) {
                    return new Modal(element);
                }
            }
        };
    }
}); 