function carregarCentrosCusto(centroCustoId) {
    console.log('Carregando centros de custo');
    url='/notas-fiscais/api/centros-custo'
    // Tentar cada URL até uma funcionar
    
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
            console.log('Centros de custo recebidos:', data);
            if (data.success) {
                let options = '<option value="">Selecione um centro de custo</option>';
                
                data.centros_custo.forEach(function(centro) {
                    options += `<option value="${centro.id}">${centro.codigo} - ${centro.nome}</option>`;
                });
                
                document.getElementById(centroCustoId).innerHTML = options;
                
                // Registrar URL bem-sucedida para uso futuro
                console.log(`URL bem-sucedida: ${url}`);
            } else {
                console.error('Erro ao carregar centros de custo:', data.message);
            }
        })
        .catch(error => {
            console.warn(`Falha ao usar ${url}:`, error);
        });
}
function fecharModal(modalId) {
    $(modalId).modal('hide');
    $('.modal-backdrop').remove();
    $('body').removeClass('modal-open');
}
async function compararUnidades(unidadeNota, unidadeMaterial) {
    console.log('compararUnidades', unidadeNota, unidadeMaterial);
    try {
        const response = await fetch('/notas-fiscais/api/comparar-unidades', {
            method: 'POST',
            headers: {
                'X-CSRFToken': $('input[name="csrf_token"]').val(),
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({unidadeNota, unidadeMaterial})
        });
        const data = await response.json();
        return data;
    } catch (error) {
        console.error('Erro ao comparar unidades:', error);
        return false;
    }
}
