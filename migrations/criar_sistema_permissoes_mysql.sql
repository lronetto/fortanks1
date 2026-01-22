-- =====================================================
-- Sistema de Gerenciamento de Permissões de Módulos
-- Banco de Dados: MySQL
-- =====================================================

-- Tabela de Módulos
-- Armazena os módulos do sistema que podem ter permissões
CREATE TABLE IF NOT EXISTS modulos (
    id INT AUTO_INCREMENT PRIMARY KEY,
    nome VARCHAR(100) NOT NULL UNIQUE COMMENT 'Nome único do módulo (ex: DASHBOARD, CLIENTES)',
    descricao TEXT COMMENT 'Descrição do módulo',
    icone VARCHAR(50) COMMENT 'Ícone do módulo (ex: fas fa-dashboard)',
    url VARCHAR(200) COMMENT 'URL base do módulo',
    ordem INT DEFAULT 0 COMMENT 'Ordem de exibição no menu',
    status ENUM('Ativo', 'Inativo') DEFAULT 'Ativo' COMMENT 'Status do módulo',
    criado_em DATETIME DEFAULT CURRENT_TIMESTAMP COMMENT 'Data de criação',
    atualizado_em DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT 'Data de atualização',
    INDEX idx_modulos_status (status),
    INDEX idx_modulos_ordem (ordem)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='Tabela de módulos do sistema';

-- Tabela de Permissões
-- Armazena as permissões de acesso aos módulos por usuário, departamento ou cargo
CREATE TABLE IF NOT EXISTS permissoes (
    id INT AUTO_INCREMENT PRIMARY KEY,
    modulo_id INT NOT NULL COMMENT 'Referência ao módulo',
    usuario_id INT NULL COMMENT 'Referência ao usuário (se tipo_permissao = usuario)',
    departamento_id INT NULL COMMENT 'Referência ao departamento (se tipo_permissao = departamento)',
    cargo_id INT NULL COMMENT 'Referência ao cargo (se tipo_permissao = cargo)',
    tipo_permissao ENUM('usuario', 'departamento', 'cargo') NOT NULL COMMENT 'Tipo de permissão',
    pode_visualizar BOOLEAN DEFAULT TRUE COMMENT 'Permissão para visualizar o módulo',
    pode_criar BOOLEAN DEFAULT FALSE COMMENT 'Permissão para criar registros',
    pode_editar BOOLEAN DEFAULT FALSE COMMENT 'Permissão para editar registros',
    pode_excluir BOOLEAN DEFAULT FALSE COMMENT 'Permissão para excluir registros',
    pode_exportar BOOLEAN DEFAULT FALSE COMMENT 'Permissão para exportar dados',
    status ENUM('Ativo', 'Inativo') DEFAULT 'Ativo' COMMENT 'Status da permissão',
    criado_em DATETIME DEFAULT CURRENT_TIMESTAMP COMMENT 'Data de criação',
    atualizado_em DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT 'Data de atualização',
    FOREIGN KEY (modulo_id) REFERENCES modulos(id) ON DELETE CASCADE,
    FOREIGN KEY (usuario_id) REFERENCES usuarios(id) ON DELETE CASCADE,
    FOREIGN KEY (departamento_id) REFERENCES departamentos(id) ON DELETE CASCADE,
    FOREIGN KEY (cargo_id) REFERENCES cargos(id) ON DELETE CASCADE,
    INDEX idx_permissoes_modulo (modulo_id),
    INDEX idx_permissoes_usuario (usuario_id),
    INDEX idx_permissoes_departamento (departamento_id),
    INDEX idx_permissoes_cargo (cargo_id),
    INDEX idx_permissoes_tipo (tipo_permissao),
    INDEX idx_permissoes_status (status),
    -- Garantir que apenas um tipo de permissão seja definido por registro
    CONSTRAINT chk_permissoes_tipo CHECK (
        (tipo_permissao = 'usuario' AND usuario_id IS NOT NULL AND departamento_id IS NULL AND cargo_id IS NULL) OR
        (tipo_permissao = 'departamento' AND departamento_id IS NOT NULL AND usuario_id IS NULL AND cargo_id IS NULL) OR
        (tipo_permissao = 'cargo' AND cargo_id IS NOT NULL AND usuario_id IS NULL AND departamento_id IS NULL)
    )
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='Tabela de permissões de acesso aos módulos';

-- =====================================================
-- Inserção de Módulos Iniciais
-- =====================================================

INSERT INTO modulos (nome, descricao, icone, url, ordem, status) VALUES
('DASHBOARD', 'Painel de controle principal', 'fas fa-tachometer-alt', '/dashboard', 1, 'Ativo'),
('USUARIOS', 'Gerenciamento de usuários do sistema', 'fas fa-users', '/usuarios', 2, 'Ativo'),
('COLABORADORES', 'Gerenciamento de colaboradores', 'fas fa-user-tie', '/colaboradores', 3, 'Ativo'),
('DEPARTAMENTOS', 'Gerenciamento de departamentos', 'fas fa-building', '/departamentos', 4, 'Ativo'),
('CARGOS', 'Gerenciamento de cargos', 'fas fa-briefcase', '/cargos', 5, 'Ativo'),
('CLIENTES', 'Gerenciamento de clientes', 'fas fa-handshake', '/clientes', 6, 'Ativo'),
('CONTRATOS', 'Gerenciamento de contratos', 'fas fa-file-contract', '/contratos', 7, 'Ativo'),
('TANQUES', 'Gerenciamento de tanques', 'fas fa-cube', '/tanques', 8, 'Ativo'),
('PECAS', 'Gerenciamento de peças', 'fas fa-puzzle-piece', '/pecas', 9, 'Ativo'),
('CONCRETAGENS', 'Gerenciamento de concretagens', 'fas fa-hard-hat', '/concretagens', 10, 'Ativo'),
('EQUIPAMENTOS', 'Gerenciamento de equipamentos', 'fas fa-tools', '/equipamentos', 11, 'Ativo'),
('MATERIAIS', 'Gerenciamento de materiais', 'fas fa-boxes', '/materiais', 12, 'Ativo'),
('ESTOQUE', 'Gerenciamento de estoque', 'fas fa-warehouse', '/estoque', 13, 'Ativo'),
('NOTAS_FISCAIS', 'Gerenciamento de notas fiscais', 'fas fa-file-invoice', '/notas-fiscais', 14, 'Ativo'),
('RELATORIOS', 'Relatórios do sistema', 'fas fa-chart-bar', '/relatorios', 15, 'Ativo'),
('PERMISSOES', 'Gerenciamento de permissões', 'fas fa-key', '/admin/permissoes', 16, 'Ativo'),
('REEMBOLSOS', 'Gerenciamento de reembolsos', 'fas fa-money-bill-wave', '/reembolsos', 17, 'Ativo'),
('CERTIFICADOS', 'Gerenciamento de certificados', 'fas fa-certificate', '/certificados', 18, 'Ativo'),
('DADOS_ANALITICOS', 'Dados analíticos e dashboards', 'fas fa-chart-line', '/dados-analiticos', 19, 'Ativo'),
('PRODUTO_COMPOSTO', 'Gerenciamento de produtos compostos', 'fas fa-box', '/produto-composto', 20, 'Ativo'),
('SOLICITACOES', 'Gerenciamento de solicitações', 'fas fa-clipboard-list', '/solicitacoes', 21, 'Ativo'),
('SEGURANCA', 'Módulo de segurança e EPIs', 'fas fa-shield-alt', '/seguranca', 22, 'Ativo')
ON DUPLICATE KEY UPDATE 
    descricao = VALUES(descricao),
    icone = VALUES(icone),
    url = VALUES(url),
    ordem = VALUES(ordem);

-- =====================================================
-- Exemplo de Permissões Iniciais (Opcional)
-- Descomente e ajuste conforme necessário
-- =====================================================

-- Exemplo: Dar acesso total a cargos administrativos
-- Substitua os IDs pelos IDs reais dos cargos no seu banco
/*
INSERT INTO permissoes (modulo_id, cargo_id, tipo_permissao, pode_visualizar, pode_criar, pode_editar, pode_excluir, pode_exportar, status)
SELECT 
    m.id,
    c.id,
    'cargo',
    TRUE,
    TRUE,
    TRUE,
    TRUE,
    TRUE,
    'Ativo'
FROM modulos m
CROSS JOIN cargos c
WHERE c.nome IN ('ADMINISTRADOR', 'GERENTE', 'DIRETOR')
AND m.status = 'Ativo'
ON DUPLICATE KEY UPDATE status = 'Ativo';
*/

-- =====================================================
-- Views Úteis (Opcional)
-- =====================================================

-- View para listar permissões com informações completas
CREATE OR REPLACE VIEW vw_permissoes_completas AS
SELECT 
    p.id,
    p.tipo_permissao,
    m.nome AS modulo_nome,
    m.descricao AS modulo_descricao,
    CASE 
        WHEN p.tipo_permissao = 'usuario' THEN u.nome
        WHEN p.tipo_permissao = 'departamento' THEN d.nome
        WHEN p.tipo_permissao = 'cargo' THEN c.nome
    END AS entidade_nome,
    p.pode_visualizar,
    p.pode_criar,
    p.pode_editar,
    p.pode_excluir,
    p.pode_exportar,
    p.status,
    p.criado_em,
    p.atualizado_em
FROM permissoes p
INNER JOIN modulos m ON p.modulo_id = m.id
LEFT JOIN usuarios u ON p.usuario_id = u.id AND p.tipo_permissao = 'usuario'
LEFT JOIN departamentos d ON p.departamento_id = d.id AND p.tipo_permissao = 'departamento'
LEFT JOIN cargos c ON p.cargo_id = c.id AND p.tipo_permissao = 'cargo'
WHERE p.status = 'Ativo' AND m.status = 'Ativo';

-- =====================================================
-- Fim do Script
-- =====================================================
