// Script para gerenciar o formulário de produto composto
document.addEventListener('DOMContentLoaded', function() {
    console.log('Script de produto composto carregado');
    
    // Referência ao modal (verificar se existe para evitar erros)
    const addMaterialModal = document.getElementById('addMaterialModal');
    if (!addMaterialModal) {
        console.log('Modal de adicionar material não encontrado na página');
        return;
    }
    
    // Configurar eventos para o carregamento de unidades quando o modal é exibido
    addMaterialModal.addEventListener('shown.bs.modal', function() {
        console.log('Modal de adicionar material aberto');
        configurarEventosMaterial();
    });
    
    // Se o evento do Bootstrap não funcionar, tentar com jQuery como fallback
    if (typeof $ !== 'undefined') {
        $(addMaterialModal).on('shown.bs.modal', function() {
            console.log('Modal aberto via jQuery');
            configurarEventosMaterial();
        });
    }
    
    // Configuração inicial ao carregar a página
    configurarEventosMaterial();
    
    // Configurar o botão de teste
    const btnTestarUnidades = document.getElementById('btnTestarUnidades');
    if (btnTestarUnidades) {
        btnTestarUnidades.addEventListener('click', function() {
            const materialSelect = document.getElementById('material_id');
            if (materialSelect && materialSelect.value) {
                console.log('Teste manual: Carregando unidades para o material ID:', materialSelect.value);
                carregarUnidades(materialSelect.value);
            } else {
                alert('Selecione um material primeiro!');
            }
        });
    }
    
    // Função para configurar o evento de mudança no material
    function configurarEventosMaterial() {
        const materialSelect = document.getElementById('material_id');
        if (!materialSelect) {
            console.log('Select de material não encontrado');
            return;
        }
        
        console.log('Configurando evento de mudança para o select de material');
        
        // Remover eventos antigos para evitar duplicatas
        materialSelect.removeEventListener('change', handleMaterialChange);
        materialSelect.addEventListener('change', handleMaterialChange);
        
        // Executar uma vez para configurar o estado inicial
        if (materialSelect.value) {
            console.log('Material já selecionado, carregando unidades');
            carregarUnidades(materialSelect.value);
        }
    }
    
    // Handler para a mudança de material
    function handleMaterialChange(event) {
        const materialId = event.target.value;
        console.log('Material alterado para:', materialId);
        
        if (!materialId) {
            // Limpar o select de unidades se nenhum material for selecionado
            const unidadeSelect = document.getElementById('unidade');
            if (unidadeSelect) {
                unidadeSelect.innerHTML = '<option value="">Selecione um material primeiro</option>';
                
                const unidadeFator = document.getElementById('unidadeFator');
                if (unidadeFator) {
                    unidadeFator.textContent = '';
                }
            }
            return;
        }
        
        // Carregar unidades para o material selecionado
        carregarUnidades(materialId);
    }
    
    // Função para carregar unidades via XMLHttpRequest (mais compatível que Fetch)
    function carregarUnidades(materialId) {
        console.log('Carregando unidades para o material ID:', materialId);
        
        // Mostrar estado de carregamento
        const unidadeSelect = document.getElementById('unidade');
        if (unidadeSelect) {
            unidadeSelect.innerHTML = '<option value="">Carregando...</option>';
            unidadeSelect.disabled = true;
        }
        
        // Criar e configurar a requisição
        const xhr = new XMLHttpRequest();
        xhr.open('GET', '/produto-composto/api/produto-composto/material/' + materialId + '/unidades', true);
        
        xhr.onload = function() {
            console.log('Resposta recebida:', xhr.status);
            console.log('Resposta texto:', xhr.responseText);
            
            if (xhr.status >= 200 && xhr.status < 300) {
                console.log('Unidades carregadas com sucesso');
                try {
                    const data = JSON.parse(xhr.responseText);
                    console.log('Dados recebidos:', data);
                    preencherUnidades(data);
                } catch (e) {
                    console.error('Erro ao processar resposta JSON:', e);
                    mostrarErroUnidades('Erro ao processar resposta');
                }
            } else {
                console.error('Erro ao carregar unidades:', xhr.status, xhr.statusText);
                mostrarErroUnidades('Erro: ' + xhr.status);
            }
        };
        
        xhr.onerror = function() {
            console.error('Erro de rede ao carregar unidades');
            mostrarErroUnidades('Erro de conexão');
        };
        
        xhr.send();
    }
    
    // Função para preencher o select de unidades com os dados recebidos
    function preencherUnidades(data) {
        const unidadeSelect = document.getElementById('unidade');
        if (!unidadeSelect) {
            console.log('Select de unidade não encontrado');
            return;
        }
        
        // Limpar select e habilitar
        unidadeSelect.innerHTML = '';
        unidadeSelect.disabled = false;
        
        // Verificar se há unidades disponíveis
        if (!data.unidades || data.unidades.length === 0) {
            unidadeSelect.innerHTML = '<option value="">Nenhuma unidade disponível</option>';
            return;
        }
        
        // Adicionar cada unidade como uma opção
        data.unidades.forEach(function(unidade) {
            const option = document.createElement('option');
            option.value = unidade.nome;
            option.textContent = unidade.nome + (unidade.descricao ? ' - ' + unidade.descricao : '');
            
            // Marcar unidade padrão como selecionada
            if (unidade.padrao) {
                option.selected = true;
            }
            
            // Adicionar informação de fator de conversão como atributo data
            if (unidade.fator_conversao) {
                option.dataset.fator = unidade.fator_conversao;
            }
            
            unidadeSelect.appendChild(option);
        });
        
        // Atualizar informação de fator de conversão
        atualizarInfoConversao();
        
        // Adicionar evento de mudança para a unidade
        unidadeSelect.removeEventListener('change', atualizarInfoConversao);
        unidadeSelect.addEventListener('change', atualizarInfoConversao);
    }
    
    // Função para mostrar erro no select de unidades
    function mostrarErroUnidades(mensagem) {
        const unidadeSelect = document.getElementById('unidade');
        if (unidadeSelect) {
            unidadeSelect.innerHTML = `<option value="">Erro: ${mensagem}</option>`;
            unidadeSelect.disabled = false;
        }
        
        const unidadeFator = document.getElementById('unidadeFator');
        if (unidadeFator) {
            unidadeFator.textContent = '';
        }
    }
    
    // Função para atualizar informações de conversão
    function atualizarInfoConversao() {
        const unidadeSelect = document.getElementById('unidade');
        const unidadeFator = document.getElementById('unidadeFator');
        
        if (!unidadeSelect || !unidadeFator) return;
        
        const selectedOption = unidadeSelect.options[unidadeSelect.selectedIndex];
        if (!selectedOption) return;
        
        const fator = selectedOption.dataset.fator;
        
        if (fator) {
            unidadeFator.textContent = 'Fator de conversão: ' + parseFloat(fator).toFixed(4);
        } else {
            unidadeFator.textContent = '';
        }
    }
}); 