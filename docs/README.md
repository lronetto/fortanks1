# Sistema de Gestão Fortanks

## Visão Geral
Sistema de gestão empresarial desenvolvido para a Fortanks, focado no controle de produção de tanques, gestão de materiais, processos de concretagem e gestão administrativa.

## Módulos do Sistema

### 1. Gestão de Produção
#### 1.1 Tanques
- Cadastro e acompanhamento de tanques
- Controle de produção
- Especificações técnicas
- Status de fabricação

#### 1.2 Concretagem
- Controle de processos de concretagem
- Usinagem de concreto
- Traços e composições
- Registro de operações

#### 1.3 Peças
- Cadastro de peças
- Controle de estoque
- Especificações técnicas

### 2. Gestão de Materiais
- Cadastro completo de materiais
- Controle de estoque
- Importação em massa
- Conversão de unidades
- Vinculação com plano de contas
- Solicitações de materiais

### 3. Gestão de Equipamentos
- Cadastro de equipamentos
- Controle de manutenção
- Histórico de uso
- Documentação técnica

### 4. Segurança e EPI
- Controle de EPIs
- Distribuição para colaboradores
- Histórico de entregas
- Controle de validade

### 5. Gestão Administrativa
#### 5.1 Clientes
- Cadastro de clientes
- Endereços
- Contratos
- Histórico de relacionamento

#### 5.2 Colaboradores
- Cadastro de funcionários
- Controle de acesso
- Atribuições e responsabilidades

#### 5.3 Financeiro
- Plano de contas
- Centros de custo
- Notas fiscais
- Controle orçamentário

## Arquitetura do Sistema

### Tecnologias Utilizadas
#### Backend
- Python 3.x
- Flask 2.3.3 (Framework Web)
- SQLAlchemy 2.0.21 (ORM)
- Flask-Migrate 4.0.5 (Migrações)
- Flask-Login 0.6.2 (Autenticação)
- Flask-WTF 1.2.1 (Formulários)
- Pandas 2.1.1 (Manipulação de dados)

#### Frontend
- HTML5/CSS3
- Bootstrap 5
- JavaScript/jQuery
- Select2 (Campos de seleção avançados)
- Font Awesome (Ícones)

#### Banco de Dados
- MySQL/PostgreSQL
- Migrations para versionamento

### Estrutura de Diretórios
```
fortanks/
├── models/                     # Modelos de dados
│   ├── __init__.py            # Inicialização dos modelos
│   ├── database.py            # Configuração do banco de dados
│   ├── material.py            # Modelo de materiais
│   ├── solicitacao.py         # Modelo de solicitações
│   ├── usuario.py             # Modelo de usuários
│   ├── cliente.py             # Modelo de clientes
│   ├── colaborador.py         # Modelo de colaboradores
│   ├── concretagem.py         # Modelo de concretagem
│   ├── contrato.py            # Modelo de contratos
│   ├── conversao_unidade.py   # Modelo de conversão de unidades
│   ├── endereco.py            # Modelo de endereços
│   ├── epi.py                 # Modelo de EPIs
│   ├── equipamento.py         # Modelo de equipamentos
│   ├── nota_fiscal.py         # Modelo de notas fiscais
│   ├── peca.py                # Modelo de peças
│   ├── plano_conta.py         # Modelo de plano de contas
│   ├── tanque.py              # Modelo de tanques
│   └── usinagem_concreto.py   # Modelo de usinagem de concreto
│
├── controllers/                # Controladores da aplicação
│   ├── admin_controller.py     # Controle administrativo
│   ├── api_controller.py       # APIs do sistema
│   ├── auth_controller.py      # Autenticação
│   ├── centro_custo_controller.py  # Centro de custos
│   ├── cliente_controller.py   # Gestão de clientes
│   ├── colaborador_controller.py    # Gestão de colaboradores
│   ├── concretagem_controller.py    # Controle de concretagem
│   ├── contrato_controller.py  # Gestão de contratos
│   ├── conversao_unidade_controller.py  # Conversão de unidades
│   ├── dashboard_controller.py # Dashboard
│   ├── epi_controller.py       # Controle de EPIs
│   ├── equipamento_controller.py    # Gestão de equipamentos
│   ├── material_controller.py  # Gestão de materiais
│   ├── peca_controller.py      # Gestão de peças
│   ├── plano_conta_controller.py    # Plano de contas
│   ├── seguranca_controller.py # Controle de segurança
│   ├── solicitacao_controller.py    # Solicitações de materiais
│   ├── tanque_controller.py    # Gestão de tanques
│   ├── usuario_controller.py   # Gestão de usuários
│   └── usinagem_concreto_controller.py  # Usinagem de concreto
│
├── templates/                  # Templates HTML
│   ├── auth/                  # Autenticação
│   ├── centro_custo/          # Centro de custos
│   ├── clientes/              # Clientes
│   ├── colaboradores/         # Colaboradores
│   ├── common/                # Templates base
│   ├── concretagens/          # Concretagem
│   ├── contratos/             # Contratos
│   ├── conversao_unidades/    # Conversão de unidades
│   ├── dashboard/             # Dashboard
│   ├── equipamentos/          # Equipamentos
│   ├── materiais/             # Materiais
│   ├── pecas/                 # Peças
│   ├── planos_conta/          # Plano de contas
│   ├── seguranca/             # Segurança
│   ├── solicitacoes/          # Solicitações
│   ├── tanques/               # Tanques
│   ├── usuarios/              # Usuários
│   └── usinagem_concreto/     # Usinagem de concreto
│
├── static/                    # Arquivos estáticos
│   ├── css/                   # Estilos
│   ├── js/                    # JavaScript
│   └── img/                   # Imagens
│
├── migrations/                # Migrações do banco de dados
│   └── versions/              # Versões das migrações
│
├── utils/                    # Utilitários
├── config/                   # Configurações
├── instance/                 # Instância específica
├── temp_uploads/             # Uploads temporários
├── app.py                    # Aplicação principal
├── requirements.txt          # Dependências
└── run_migrations.py         # Script de migrações
```

## Funcionalidades Principais

### 1. Solicitações de Materiais
- Criação de solicitações com múltiplos itens
- Fluxo de aprovação
- Integração com estoque
- Vinculação com centro de custos
- Histórico de solicitações

### 2. Usinagem de Concreto
- Cadastro de traços
- Controle de materiais
- Registro de operações
- Histórico de produção

### 3. Gestão de EPIs
- Controle de estoque
- Distribuição
- Controle de validade
- Histórico por colaborador

### 4. Controle de Tanques
- Acompanhamento de produção
- Especificações técnicas
- Status de fabricação
- Documentação

## Controle de Acesso

### Perfis de Usuário
1. Administrador
   - Acesso total ao sistema
   - Gestão de usuários
   - Configurações gerais

2. Gerente
   - Aprovação de solicitações
   - Relatórios gerenciais
   - Gestão de equipe

3. Operacional
   - Registro de operações
   - Solicitações de materiais
   - Consultas

## Instalação e Configuração

### Requisitos
- Python 3.8+
- MySQL/PostgreSQL
- Ambiente virtual Python

### Passos para Instalação

1. Clone o repositório
```bash
git clone [url-do-repositorio]
cd fortanks
```

2. Crie e ative o ambiente virtual
```bash
python -m venv venv
source venv/bin/activate  # Linux/Mac
venv\Scripts\activate     # Windows
```

3. Instale as dependências
```bash
pip install -r requirements.txt
```

4. Configure o banco de dados
```bash
# Edite as configurações no arquivo config.py
flask db upgrade
```

5. Execute o servidor
```bash
flask run
```

## Desenvolvimento

### Padrões de Código
- PEP 8 para Python
- Black para formatação
- Flake8 para linting

### Testes
- Pytest para testes unitários
- Pytest-flask para testes de integração

### Versionamento
- Git para controle de versão
- Branches por feature
- Pull requests para revisão

## Manutenção

### Backups
- Backup diário do banco de dados
- Backup semanal dos arquivos
- Retenção de 30 dias

### Logs
- Logs de acesso
- Logs de operações
- Logs de erros

### Monitoramento
- Status do servidor
- Uso de recursos
- Tempo de resposta

## Suporte

### Contatos
- Suporte Técnico: suporte@fortanks.com.br
- Administração: admin@fortanks.com.br

### Documentação Adicional
- Manual do Usuário
- Guia de Administração
- FAQ

## Licença
Este software é proprietário e confidencial.
Todos os direitos reservados à Fortanks. 