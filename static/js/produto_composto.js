$(document).ready(function() {
    // Configuração global do AJAX para incluir o token CSRF
    $.ajaxSetup({
        beforeSend: function(xhr, settings) {
            if (!/^(GET|HEAD|OPTIONS|TRACE)$/i.test(settings.type) && !this.crossDomain) {
                xhr.setRequestHeader("X-CSRF-Token", $('meta[name="csrf-token"]').attr('content'));
            }
        }
    });

    const modalContainer = $('#modal-container');
    let imageDataUrl = null; // Variável para armazenar a imagem em base64

    // 1. Abrir modal para NOVO produto
    $('#btn-novo-produto').on('click', function() {
        abrirModalForm();
    });

    // 2. Abrir modal para EDITAR produto
    $('#tabela-produtos-compostos').on('click', '.btn-editar', function() {
        const produtoId = $(this).data('id');
        abrirModalForm(produtoId);
    });

    // 3. Handler para botão de duplicar
    $(document).on('click', '.btn-duplicar', function() {
        const produtoId = $(this).data('id');
        const produtoNome = $(this).data('nome');
        
        // Configurar o modal de duplicação
        $('#nome-produto-duplicar').text(produtoNome);
        $('#form-duplicar').attr('action', `/produto-composto/${produtoId}/duplicar`);
        $('#duplicateModal').modal('show');
    });

    // 4. Handler para botão de editar
    $('#tabela-produtos-compostos').on('click', '.btn-editar', function() {
        const produtoId = $(this).data('id');
        abrirModalForm(produtoId);
    });

    // 5. Submissão do formulário do modal
    modalContainer.on('submit', '#form-produto-composto', function(e) {
        e.preventDefault();
        salvarProduto();
    });

    // 6. Lógica para adicionar item na tabela de componentes
    modalContainer.on('click', '#btn-adicionar-item', function() {
        adicionarComponenteTabela();
    });

    // 7. Lógica para remover item da tabela de componentes
    modalContainer.on('click', '.btn-remover-item', function() {
        $(this).closest('tr').remove();
    });
    
    // 8. Configurar e abrir modal de EXCLUSÃO
    $('#tabela-produtos-compostos').on('click', '.btn-excluir', function() {
        const produtoId = $(this).data('id');
        const produtoNome = $(this).data('nome');
        
        $('#nome-produto-excluir').text(produtoNome);
        $('#form-excluir').attr('action', `/produto-composto/${produtoId}/deletar`);
        $('#deleteModal').modal('show');
    });

    // Handler para submit do formulário de exclusão
    $('#form-excluir').on('submit', function(e) {
        e.preventDefault();
        
        const action = $(this).attr('action');
        
        $.ajax({
            url: action,
            type: 'POST',
            headers: {
                'X-CSRFToken': $('meta[name="csrf-token"]').attr('content')
            },
            success: function(response) {
                // Fechar modal corretamente
                fecharModal('#deleteModal');
                
                showAlert('success', 'Produto composto excluído com sucesso!');
                recarregarTabela();
            },
            error: function(xhr, status, error) {
                console.error('Erro ao excluir:', error);
                showAlert('danger', 'Erro ao excluir produto composto. Tente novamente.');
            }
        });
    });

    // Handler para submit do formulário de duplicação
    $('#form-duplicar').on('submit', function(e) {
        e.preventDefault();
        
        const action = $(this).attr('action');
        
        $.ajax({
            url: action,
            type: 'POST',
            headers: {
                'X-CSRFToken': $('meta[name="csrf-token"]').attr('content')
            },
            success: function(response) {
                // Fechar modal corretamente
                fecharModal('#duplicateModal');
                
                showAlert('success', 'Produto composto duplicado com sucesso!');
                recarregarTabela();
            },
            error: function(xhr, status, error) {
                console.error('Erro ao duplicar:', error);
                showAlert('danger', 'Erro ao duplicar produto composto. Tente novamente.');
            }
        });
    });

    // 9. Lógica de Upload de Imagem - Versão Simplificada
    var isClicking = false;
    $(document).off('click', '#image-upload-container').on('click', '#image-upload-container', function(e) {
        if (isClicking) return; // Evitar múltiplos cliques
        
        e.preventDefault();
        e.stopPropagation();
        console.log('Área de upload clicada'); // Debug
        
        // Usar método nativo do DOM
        var fileInput = document.getElementById('image-input');
        if (fileInput) {
            console.log('Input file encontrado, clicando...');
            isClicking = true;
            fileInput.click();
            
            // Resetar após um tempo
            setTimeout(function() {
                isClicking = false;
            }, 1000);
        } else {
            console.error('Input file não encontrado');
        }
    });

    $(document).off('change', '#image-input').on('change', '#image-input', function(e) {
        console.log('Arquivo selecionado:', e.target.files[0]); // Debug
        if (e.target.files && e.target.files[0]) {
            handleFile(e.target.files[0]);
        }
    });

    // 10. Lógica de Drag and Drop
    modalContainer.on('dragover', '#image-upload-container', function(e) {
        e.preventDefault();
        e.stopPropagation();
        $(this).addClass('bg-light');
    });

    modalContainer.on('dragleave', '#image-upload-container', function(e) {
        e.preventDefault();
        e.stopPropagation();
        $(this).removeClass('bg-light');
    });

    modalContainer.on('drop', '#image-upload-container', function(e) {
        e.preventDefault();
        e.stopPropagation();
        $(this).removeClass('bg-light');
        console.log('Arquivo dropado:', e.originalEvent.dataTransfer.files[0]); // Debug
        if (e.originalEvent.dataTransfer.files && e.originalEvent.dataTransfer.files[0]) {
            handleFile(e.originalEvent.dataTransfer.files[0]);
        }
    });

    // 11. Lógica para remover imagem
    modalContainer.on('click', '#btn-remover-imagem', function() {
        $('#remover_imagem_hidden').val('1');
        $('#image-preview').attr('src', '/static/img/logo.png'); // Placeholder
        $(this).hide();
        imageDataUrl = null;
        $('#image-input').val(''); // Limpa o input file
    });

    // 12. Debug: Verificar se o modal está carregando corretamente
    modalContainer.on('shown.bs.modal', '#modal-produto-composto', function() {
        console.log('Modal aberto, verificando elementos...'); // Debug
        console.log('Área de upload:', $('#image-upload-container').length);
        console.log('Input file:', $('#image-input').length);
        
        // Teste adicional: verificar se o clique funciona
        setTimeout(function() {
            console.log('Testando clique na área de upload...');
            $('#image-upload-container').css('background-color', 'yellow'); // Visual feedback
        }, 1000);
    });

    // 13. Handlers para fechar o modal
    modalContainer.on('click', '[data-dismiss="modal"]', function() {
        console.log('Botão fechar clicado');
        fecharModal('#modal-produto-composto');
    });
    
    modalContainer.on('click', '.btn-secondary', function() {
        console.log('Botão cancelar clicado');
        fecharModal('#modal-produto-composto');
    });
    
    // 14. Handler para tecla ESC
    $(document).on('keydown', function(e) {
        if (e.key === 'Escape' && $('#modal-produto-composto').hasClass('show')) {
            console.log('ESC pressionado');
            fecharModal('#modal-produto-composto');
        }
    });
    
    // 15. Handler para clique fora do modal
    modalContainer.on('click', '.modal', function(e) {
        if (e.target === this) {
            console.log('Clique fora do modal');
            fecharModal('#modal-produto-composto');
        }
    });

    // 16. Verificação do Bootstrap e handler alternativo
    $(document).ready(function() {
        // Verificar se o Bootstrap está disponível
        if (typeof $.fn.modal === 'undefined') {
            console.error('Bootstrap modal não está disponível!');
        } else {
            console.log('Bootstrap modal está disponível');
        }
        
        // Handler alternativo para fechar modal
        $(document).on('click', '[data-dismiss="modal"]', function() {
            console.log('Handler alternativo - Botão fechar clicado');
            fecharModal($(this).closest('.modal'));
        });
        
        $(document).on('click', '.btn-secondary', function() {
            console.log('Handler alternativo - Botão cancelar clicado');
            fecharModal($(this).closest('.modal'));
        });
        
        // Inicializar handlers da tabela
        aplicarHandlersTabela();
    });

    


    // --- FUNÇÕES AUXILIARES ---

    function abrirModalForm(produtoId) {
        const url = produtoId ? `/produto-composto/${produtoId}/form` : '/produto-composto/form';
        
        // Carrega o conteúdo do modal
        modalContainer.load(url, function() {
            const modal = $('#modal-produto-composto')
            modal.modal('show');
            
            // Reseta a variável de imagem e o campo hidden
            imageDataUrl = null;
            $('#remover_imagem_hidden').val('0');

            // Inicializa o Select2 após o modal ser carregado
            inicializarSelect2();

            // Adiciona o listener de paste no documento quando o modal abre
            $(document).on('paste.produtoComposto', handlePaste);

            // Garante a remoção do listener quando o modal é fechado
            modal.on('hidden.bs.modal', function () {
                $(document).off('paste.produtoComposto');
            });
        });
    }

    function inicializarSelect2() {
        $('#select-item-estoque').select2({
            placeholder: "Selecione um item",
            width: '100%',
            dropdownParent: $('#modal-produto-composto'),
            ajax: {
                url: "/estoque/api/listar",
                dataType: 'json',
                delay: 250,
                data: function(params) {
                    return {
                        q: params.term // search term
                    };
                },
                processResults: function(data) {
                    return {
                        results: data.results
                    };
                },
                cache: true
            }
        });
    }
    
    function handlePaste(e) {
        // Acessa os itens da área de transferência
        const items = (e.clipboardData || e.originalEvent.clipboardData)?.items;
        if (!items) return;

        for (const item of items) {
            // Verifica se o item é um arquivo de imagem
            if (item.kind === 'file' && item.type.startsWith('image/')) {
                // Impede a ação padrão do navegador (colar texto/imagem)
                e.preventDefault();
                const file = item.getAsFile();
                if (file) {
                    // Usa a nossa função existente para lidar com o arquivo
                    handleFile(file);
                }
                // Para após encontrar a primeira imagem
            return;
        }
        }
    }
  
    function handleFile(file) {
        if (!file.type.startsWith('image/')) {
            alert('Por favor, selecione um arquivo de imagem (ex: PNG, JPG).');
            return;
        }
        
        if (file.size > 2 * 1024 * 1024) { // 2MB
            alert('A imagem é muito grande. O tamanho máximo permitido é 2MB.');
            return;
        }

        const reader = new FileReader();
        reader.onload = function(e) {
            $('#image-preview').attr('src', e.target.result);
            $('#btn-remover-imagem').show();
            $('#remover_imagem_hidden').val('0'); // Se o usuário remover e dps add outra
            imageDataUrl = e.target.result;
        }
        reader.readAsDataURL(file);
    }

    function adicionarComponenteTabela() {
        const select = $('#select-item-estoque');
        const selectedOption = select.select2('data')[0];
        const quantidade = $('#quantidade-item').val();

        if (!selectedOption || !quantidade || parseFloat(quantidade) <= 0) {
            alert('Por favor, selecione um item e insira uma quantidade válida.');
            return;
        }
        
        const estoqueId = selectedOption.id;
        const nomeItem = selectedOption.text;

        // Verifica se o item já foi adicionado
        if ($(`#tabela-componentes tbody tr[data-estoque-id="${estoqueId}"]`).length > 0) {
            alert('Este item já foi adicionado.');
            return;
        }
        
        const newRow = `
            <tr data-estoque-id="${estoqueId}">
                <td>${nomeItem}</td>
                <td><input type="text" class="form-control form-control-sm quantidade-componente" value="${quantidade}"></td>
                <td class="text-center">
                    <button type="button" class="btn btn-danger btn-sm btn-remover-item"><i class="fas fa-trash"></i></button>
                </td>
            </tr>
        `;

        $('#tabela-componentes tbody').append(newRow);

        // Limpa os campos
        select.val(null).trigger('change');
        $('#quantidade-item').val('');
    }

    function fecharModal(modalId) {
        $(modalId).modal('hide');
        $('.modal-backdrop').remove();
        $('body').removeClass('modal-open');
    }

    function salvarProduto() {
        const produtoId = $('#produto_id').val();
        
        // Coleta de dados dos componentes
        const componentes = [];
        $('#tabela-componentes tbody tr').each(function() {
            const row = $(this);
            const quantidadeValor = row.find('.quantidade-componente').val();
            
            // Garantir que a quantidade seja tratada como número decimal
            const quantidade = parseFloat(quantidadeValor) || 0;
            
            console.log(`Componente - Estoque ID: ${row.data('estoque-id')}, Valor original: "${quantidadeValor}", Valor convertido: ${quantidade}`);
            
            componentes.push({
                estoque_id: parseInt(row.data('estoque-id')),
                quantidade: quantidade
            });
        });

        const dadosProduto = {
            id: produtoId || null,
            nome: $('#nome').val(),
            descricao: $('#descricao').val(),
            tempo_producao: $('#tempo_producao').val() || null,
            status: $('#status').val(),
            componentes: componentes,
            imagem: imageDataUrl || null, // Envia a imagem em base64 ou null se não houver
            remover_imagem: $('#remover_imagem_hidden').val() === '1'
        };

        console.log('Dados a serem enviados:', dadosProduto);
        console.log('ImageDataUrl:', imageDataUrl);

        $.ajax({
            url: '/produto-composto/salvar',
            type: 'POST',
            contentType: 'application/json',
            data: JSON.stringify(dadosProduto),
            success: function(response) {
                if (response.success) {
                    // Fechar modal corretamente
                    fecharModal('#modal-produto-composto');
                    
                    // Mostrar mensagem de sucesso
                    showAlert('success', response.message);
                    
                    // Recarregar a tabela via AJAX
                    recarregarTabela();
                } else {
                    showAlert('danger', 'Erro: ' + response.message);
                }
            },
            error: function(xhr, status, error) {
                console.error('Erro ao salvar:', error);
                showAlert('danger', 'Erro ao salvar produto composto. Tente novamente.');
            }
        });
    }

    function recarregarTabela() {
        $.ajax({
            url: '/produto-composto/',
            type: 'GET',
            success: function(data) {
                // Extrair apenas o conteúdo da tabela do HTML retornado
                const $tempDiv = $('<div>').html(data);
                const novaTabela = $tempDiv.find('#tabela-produtos-compostos tbody').html();
                
                // Atualizar o conteúdo da tabela
                $('#tabela-produtos-compostos tbody').html(novaTabela);
                
                // Reaplicar os handlers dos botões
                aplicarHandlersTabela();
                
                // Mostrar mensagem de sucesso
                showAlert('success', 'Tabela atualizada com sucesso!');
            },
            error: function(xhr, status, error) {
                console.error('Erro ao recarregar tabela:', error);
                showAlert('warning', 'Tabela salva, mas houve erro ao atualizar a visualização.');
            }
        });
    }

    function aplicarHandlersTabela() {
        // Reaplicar handlers para os botões da tabela
        $('#tabela-produtos-compostos .btn-editar').off('click').on('click', function() {
            const produtoId = $(this).data('id');
            abrirModalForm(produtoId);
        });
        
        $('#tabela-produtos-compostos .btn-duplicar').off('click').on('click', function() {
            const produtoId = $(this).data('id');
            const produtoNome = $(this).data('nome');
            
            // Configurar o modal de duplicação
            $('#nome-produto-duplicar').text(produtoNome);
            $('#form-duplicar').attr('action', `/produto-composto/${produtoId}/duplicar`);
            $('#duplicateModal').modal('show');
        });
        
        $('#tabela-produtos-compostos .btn-excluir').off('click').on('click', function() {
            const produtoId = $(this).data('id');
            const produtoNome = $(this).data('nome');
            
            $('#nome-produto-excluir').text(produtoNome);
            $('#form-excluir').attr('action', `/produto-composto/${produtoId}/deletar`);
            $('#deleteModal').modal('show');
        });
    }

    function showAlert(type, message) {
        // Remover alertas anteriores
        $('.alert').remove();
        
        // Criar novo alerta
        const alertHtml = `
            <div class="alert alert-${type} alert-dismissible fade show" role="alert">
                ${message}
                <button type="button" class="close" data-dismiss="alert" aria-label="Close">
                    <span aria-hidden="true">&times;</span>
                </button>
            </div>
        `;
        
        // Inserir no topo da página
        $('.container-fluid').prepend(alertHtml);
        
        // Auto-remover após 5 segundos
        setTimeout(function() {
            $('.alert').fadeOut();
        }, 5000);
    }
}); 