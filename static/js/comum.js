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

