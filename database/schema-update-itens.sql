-- Modificando o esquema para permitir múltiplos itens por solicitação

-- Primeiro, vamos modificar a tabela solicitacoes (remover o campo material_id e quantidade)
ALTER TABLE solicitacoes DROP FOREIGN KEY solicitacoes_ibfk_1;
ALTER TABLE solicitacoes DROP COLUMN material_id;
ALTER TABLE solicitacoes DROP COLUMN quantidade;

-- Agora, criamos a nova tabela de itens de solicitação
CREATE TABLE IF NOT EXISTS itens_solicitacao (
    id INT AUTO_INCREMENT PRIMARY KEY,
    solicitacao_id INT NOT NULL,
    material_id INT NOT NULL,
    quantidade INT NOT NULL,
    observacao TEXT,
    criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (solicitacao_id) REFERENCES solicitacoes(id) ON DELETE CASCADE,
    FOREIGN KEY (material_id) REFERENCES materiais(id)
);

-- Adicionamos um índice para melhorar a busca
CREATE INDEX idx_solicitacao_material ON itens_solicitacao(solicitacao_id, material_id);
