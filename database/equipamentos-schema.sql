-- Tabela de cadastro de equipamentos
CREATE TABLE IF NOT EXISTS checklist_equipamentos (
    id INT AUTO_INCREMENT PRIMARY KEY,
    codigo VARCHAR(50) NOT NULL,
    nome VARCHAR(100) NOT NULL,
    tipo VARCHAR(50) NOT NULL,
    modelo VARCHAR(100),
    fabricante VARCHAR(100),
    numero_serie VARCHAR(100),
    data_aquisicao DATE,
    data_ultima_manutencao DATE,
    local VARCHAR(100),
    status ENUM('ativo', 'inativo', 'em_manutencao') NOT NULL DEFAULT 'ativo',
    observacoes TEXT,
    foto VARCHAR(255),
    criado_por INT NOT NULL,
    criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    atualizado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    FOREIGN KEY (criado_por) REFERENCES usuarios(id),
    INDEX idx_codigo (codigo),
    INDEX idx_tipo (tipo),
    INDEX idx_status (status)
);

-- Tabela de histórico de manutenções
CREATE TABLE IF NOT EXISTS checklist_manutencoes (
    id INT AUTO_INCREMENT PRIMARY KEY,
    equipamento_id INT NOT NULL,
    tipo_manutencao ENUM('preventiva', 'corretiva') NOT NULL,
    data_manutencao DATE NOT NULL,
    responsavel_id INT NOT NULL,
    descricao TEXT NOT NULL,
    custo DECIMAL(10,2),
    observacoes TEXT,
    criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (equipamento_id) REFERENCES checklist_equipamentos(id) ON DELETE CASCADE,
    FOREIGN KEY (responsavel_id) REFERENCES usuarios(id)
);

-- Modificar a tabela de checklists preenchidos para referir equipamentos cadastrados
ALTER TABLE checklist_preenchidos
ADD COLUMN equipamento_cadastrado_id INT NULL AFTER modelo_id,
ADD CONSTRAINT fk_checklist_equipamento FOREIGN KEY (equipamento_cadastrado_id) 
REFERENCES checklist_equipamentos(id);
