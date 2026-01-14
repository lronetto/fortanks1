/**
 * JavaScript para gerenciar certificados
 */

// Função para editar certificado
function editarCertificado(id) {
    // Buscar dados do certificado
    fetch(`/certificados/editar/${id}`)
        .then(response => response.json())
        .then(data => {
            const certificado = data.certificado;
            const documentos = data.documentos || [];
            
            // Preencher formulário
            document.getElementById('certificado_id_editar').value = certificado.id;
            document.getElementById('nome_editar').value = certificado.nome || '';
            // Definir o valor do select de tipo
            const tipoSelect = document.getElementById('tipo_editar');
            if (certificado.tipo) {
                tipoSelect.value = certificado.tipo;
                // Mostrar/ocultar campos de cordoalha usando função do template
                if (window.toggleCamposCordoalhaEditar) {
                    window.toggleCamposCordoalhaEditar(certificado.tipo);
                }
                
                // Carregar dados de cordoalha se existirem
                if (certificado.dados_adicionais && (certificado.tipo === 'cordoalha nua' || certificado.tipo === 'materiais - cordoalha nua')) {
                    // Aguardar um pouco para garantir que os campos foram renderizados
                    setTimeout(() => {
                        if (window.carregarDadosCordoalhaEditar) {
                            window.carregarDadosCordoalhaEditar(certificado.dados_adicionais);
                        }
                    }, 100);
                }
            } else {
                tipoSelect.value = '';
            }
            document.getElementById('data_editar').value = certificado.data || '';
            document.getElementById('data_vencimento_editar').value = certificado.data_vencimento || '';
            
            // Preencher dados adicionais
            const dadosAdicionaisInput = document.getElementById('dados_adicionais_editar');
            if (dadosAdicionaisInput) {
                if (certificado.dados_adicionais && Object.keys(certificado.dados_adicionais).length > 0) {
                    dadosAdicionaisInput.value = JSON.stringify(certificado.dados_adicionais, null, 2);
                } else {
                    dadosAdicionaisInput.value = '';
                }
            }
            
            // Atualizar action do formulário
            document.getElementById('form-editar-certificado').action = `/certificados/editar/${id}`;
            
            // Carregar documentos existentes
            const documentosContainer = document.getElementById('documentos_existentes');
            documentosContainer.innerHTML = '';
            
            if (documentos.length > 0) {
                documentos.forEach(doc => {
                    const docItem = document.createElement('div');
                    docItem.className = 'list-group-item d-flex justify-content-between align-items-center';
                    docItem.innerHTML = `
                        <div>
                            <i class="fas fa-file"></i> ${doc.filename}
                            <small class="text-muted ms-2">${new Date(doc.uploaded_at).toLocaleDateString('pt-BR')}</small>
                        </div>
                        <div>
                            <a href="/certificados/documento/${doc.id}/download" class="btn btn-sm btn-primary me-1" target="_blank">
                                <i class="fas fa-download"></i>
                            </a>
                            <button type="button" class="btn btn-sm btn-danger" onclick="excluirDocumento(${doc.id}, ${id})">
                                <i class="fas fa-trash"></i>
                            </button>
                        </div>
                    `;
                    documentosContainer.appendChild(docItem);
                });
            } else {
                documentosContainer.innerHTML = '<p class="text-muted">Nenhum documento anexado</p>';
            }
            
            // Abrir modal
            const modal = new bootstrap.Modal(document.getElementById('modalEditarCertificado'));
            modal.show();
        })
        .catch(error => {
            console.error('Erro ao carregar certificado:', error);
            alert('Erro ao carregar dados do certificado.');
        });
}

// Função para visualizar certificado
function visualizarCertificado(id) {
    // Buscar dados do certificado
    fetch(`/certificados/visualizar/${id}`)
        .then(response => response.json())
        .then(data => {
            const certificado = data.certificado;
            const documentos = data.documentos || [];
            
            // Preencher detalhes
            const detalhesContainer = document.getElementById('detalhes_certificado');
            detalhesContainer.innerHTML = `
                <dt class="col-sm-4">ID:</dt>
                <dd class="col-sm-8">${certificado.id}</dd>
                
                <dt class="col-sm-4">Nome:</dt>
                <dd class="col-sm-8">${certificado.nome || 'N/A'}</dd>
                
                <dt class="col-sm-4">Tipo:</dt>
                <dd class="col-sm-8">${certificado.tipo || 'N/A'}</dd>
                
                <dt class="col-sm-4">Data:</dt>
                <dd class="col-sm-8">${certificado.data ? new Date(certificado.data).toLocaleDateString('pt-BR') : 'N/A'}</dd>
                
                <dt class="col-sm-4">Data de Vencimento:</dt>
                <dd class="col-sm-8">${certificado.data_vencimento ? new Date(certificado.data_vencimento).toLocaleDateString('pt-BR') : 'N/A'}</dd>
                
                <dt class="col-sm-4">Status:</dt>
                <dd class="col-sm-8">
                    ${certificado.ativo ? '<span class="badge bg-success">Ativo</span>' : '<span class="badge bg-danger">Inativo</span>'}
                </dd>
                
                <dt class="col-sm-4">Criado em:</dt>
                <dd class="col-sm-8">${certificado.criado_em ? new Date(certificado.criado_em).toLocaleString('pt-BR') : 'N/A'}</dd>
                
                <dt class="col-sm-4">Atualizado em:</dt>
                <dd class="col-sm-8">${certificado.atualizado_em ? new Date(certificado.atualizado_em).toLocaleString('pt-BR') : 'N/A'}</dd>
            `;
            
            // Adicionar dados adicionais se existirem
            if (certificado.dados_adicionais && Object.keys(certificado.dados_adicionais).length > 0) {
                detalhesContainer.innerHTML += `
                    <dt class="col-sm-4">Dados Adicionais:</dt>
                    <dd class="col-sm-8">
                        <pre class="bg-light p-2 rounded">${JSON.stringify(certificado.dados_adicionais, null, 2)}</pre>
                    </dd>
                `;
            }
            
            // Carregar documentos
            const documentosContainer = document.getElementById('documentos_visualizacao');
            documentosContainer.innerHTML = '';
            
            if (documentos.length > 0) {
                documentos.forEach(doc => {
                    const docItem = document.createElement('a');
                    docItem.href = `/certificados/documento/${doc.id}/download`;
                    docItem.target = '_blank';
                    docItem.className = 'list-group-item list-group-item-action d-flex justify-content-between align-items-center';
                    docItem.innerHTML = `
                        <div>
                            <i class="fas fa-file"></i> ${doc.filename}
                            <small class="text-muted ms-2">${new Date(doc.uploaded_at).toLocaleDateString('pt-BR')}</small>
                        </div>
                        <i class="fas fa-download"></i>
                    `;
                    documentosContainer.appendChild(docItem);
                });
            } else {
                documentosContainer.innerHTML = '<p class="text-muted">Nenhum documento anexado</p>';
            }
            
            // Abrir modal
            const modal = new bootstrap.Modal(document.getElementById('modalVisualizarCertificado'));
            modal.show();
        })
        .catch(error => {
            console.error('Erro ao carregar certificado:', error);
            alert('Erro ao carregar dados do certificado.');
        });
}

// Função para excluir documento
function excluirDocumento(docId, certificadoId) {
    if (!confirm('Tem certeza que deseja excluir este documento?')) {
        return;
    }
    
    // Obter CSRF token
    const csrfToken = document.querySelector('meta[name="csrf-token"]').getAttribute('content');
    
    fetch(`/certificados/documento/${docId}/excluir`, {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
            'X-CSRFToken': csrfToken,
            'X-CSRF-Token': csrfToken
        },
        body: JSON.stringify({})
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            // Recarregar dados do certificado para atualizar lista de documentos
            editarCertificado(certificadoId);
            alert('Documento excluído com sucesso!');
        } else {
            alert('Erro ao excluir documento: ' + data.message);
        }
    })
    .catch(error => {
        console.error('Erro ao excluir documento:', error);
        alert('Erro ao excluir documento.');
    });
}

// Validar JSON nos campos de dados adicionais
document.addEventListener('DOMContentLoaded', function() {
    const dadosAdicionaisInputs = document.querySelectorAll('[name="dados_adicionais"]');
    
    dadosAdicionaisInputs.forEach(input => {
        input.addEventListener('blur', function() {
            const value = this.value.trim();
            if (value) {
                try {
                    JSON.parse(value);
                    this.classList.remove('is-invalid');
                    this.classList.add('is-valid');
                } catch (e) {
                    this.classList.remove('is-valid');
                    this.classList.add('is-invalid');
                    alert('JSON inválido. Por favor, verifique a sintaxe.');
                }
            }
        });
    });
    
    // Permitir múltiplos arquivos no input de documentos
    const documentoInputs = document.querySelectorAll('input[type="file"][name^="documento_"]');
    documentoInputs.forEach(input => {
        input.addEventListener('change', function() {
            if (this.files.length > 0) {
                // Criar inputs adicionais se necessário
                let index = 0;
                const existingInputs = document.querySelectorAll('input[type="file"][name^="documento_"]');
                existingInputs.forEach(existingInput => {
                    const nameMatch = existingInput.name.match(/documento_(\d+)/);
                    if (nameMatch) {
                        const inputIndex = parseInt(nameMatch[1]);
                        if (inputIndex >= index) {
                            index = inputIndex + 1;
                        }
                    }
                });
                
                // Se houver múltiplos arquivos selecionados, criar inputs separados
                if (this.files.length > 1) {
                    for (let i = 1; i < this.files.length; i++) {
                        const newInput = document.createElement('input');
                        newInput.type = 'file';
                        newInput.name = `documento_${index + i}`;
                        newInput.className = 'form-control mt-2';
                        newInput.accept = '.pdf,.doc,.docx,.jpg,.jpeg,.png';
                        newInput.style.display = 'none';
                        this.parentElement.appendChild(newInput);
                        // Criar um FileList simulado não é possível, então vamos usar uma abordagem diferente
                    }
                }
            }
        });
    });
    
});
