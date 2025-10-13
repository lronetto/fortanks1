# Sistema de Permissões de Módulos

## Visão Geral

O sistema de permissões permite controlar o acesso aos módulos do sistema baseado em:
- **Usuário específico**: Permissões individuais para um usuário
- **Departamento**: Permissões para todos os usuários de um departamento
- **Cargo**: Permissões para todos os usuários com um cargo específico

## Estrutura do Sistema

### Modelos

#### Modulo
Representa os módulos do sistema com:
- Nome, descrição, ícone, URL
- Ordem de exibição
- Status (Ativo/Inativo)

#### Permissao
Define as permissões de acesso com:
- Referência ao módulo
- Tipo de permissão (usuario/departamento/cargo)
- Permissões específicas (visualizar, criar, editar, excluir, exportar)

### Hierarquia de Permissões

1. **Usuário específico** (maior prioridade)
2. **Departamento do usuário**
3. **Cargo do usuário** (menor prioridade)

## Como Usar

### 1. Em Controllers

```python
from utils.permissoes import verificar_permissao

@permissoes_bp.route('/exemplo')
@login_required
@verificar_permissao('MODULO_NOME', 'visualizar')
def exemplo():
    # Código da função
    pass
```

### 2. Em Templates

```html
{% if verificar_permissao_menu('MODULO_NOME') %}
    <li class="nav-item">
        <a class="nav-link" href="/modulo">
            <i class="fas fa-icon"></i> Módulo
        </a>
    </li>
{% endif %}

{% if verificar_permissao('MODULO_NOME', 'criar') %}
    <button class="btn btn-primary">Novo Item</button>
{% endif %}
```

### 3. Verificação Programática

```python
from models.permissoes import Permissao

# Verificar permissão específica
tem_permissao = Permissao.verificar_permissao_completa(usuario, 'MODULO_NOME', 'editar')

# Obter módulos permitidos para um usuário
from utils.permissoes import obter_modulos_permitidos
modulos = obter_modulos_permitidos()
```

## Ações Disponíveis

- **visualizar**: Acesso de leitura ao módulo
- **criar**: Criar novos registros
- **editar**: Modificar registros existentes
- **excluir**: Remover registros
- **exportar**: Exportar dados

## Interface de Administração

Acesse `/permissoes` para:
- Gerenciar módulos do sistema
- Criar e editar permissões
- Visualizar permissões por usuário/departamento/cargo

## Módulos Pré-configurados

O sistema já inclui os seguintes módulos:
- DASHBOARD
- USUARIOS
- COLABORADORES
- DEPARTAMENTOS
- CARGOS
- CLIENTES
- CONTRATOS
- TANQUES
- PECAS
- CONCRETAGENS
- EQUIPAMENTOS
- MATERIAIS
- ESTOQUE
- NOTAS_FISCAIS
- RELATORIOS
- PERMISSOES

## Permissões Iniciais

### Cargos com Acesso Total
- ADMINISTRADOR
- GERENTE
- DIRETOR

### Cargos com Permissões Específicas
- **TÉCNICO DE EDIFICAÇÕES**: Dashboard, Concretagens, Equipamentos, Estoque, Materiais, Peças, Relatórios
- **GESTOR DE DESENVOLVIMENTO**: Acesso amplo a módulos operacionais
- **GESTOR DE FABRICA**: Acesso amplo a módulos operacionais
- **ENGENHEIRO CIVIL**: Acesso amplo a módulos operacionais
- **OPERADOR CENTRAL DE CONCRETO**: Dashboard, Concretagens, Equipamentos, Relatórios
- **ASSISTENTE ADMINISTRATIVO**: Dashboard, Colaboradores, Clientes, Notas Fiscais, Relatórios

## Migração do Sistema Antigo

O sistema mantém compatibilidade com o sistema antigo de permissões através do método `_verificar_permissao_antiga()` no modelo Usuario, garantindo que não haja quebra de funcionalidade durante a transição.

## Exemplo de Implementação

```python
# Controller com verificação de permissões
from utils.permissoes import verificar_permissao

@blueprint.route('/clientes')
@login_required
@verificar_permissao('CLIENTES', 'visualizar')
def listar_clientes():
    # Lista clientes
    pass

@blueprint.route('/clientes/novo', methods=['GET', 'POST'])
@login_required
@verificar_permissao('CLIENTES', 'criar')
def novo_cliente():
    # Cria novo cliente
    pass

@blueprint.route('/clientes/<int:id>/editar', methods=['GET', 'POST'])
@login_required
@verificar_permissao('CLIENTES', 'editar')
def editar_cliente(id):
    # Edita cliente
    pass
```

## API de Permissões

### Verificar Permissão
```
GET /permissoes/api/verificar-permissao?modulo=MODULO_NOME&acao=visualizar
```

### Módulos do Usuário
```
GET /permissoes/api/modulos-usuario
```

## Logs e Auditoria

O sistema registra tentativas de acesso negado nos logs da aplicação, facilitando a auditoria de segurança.

