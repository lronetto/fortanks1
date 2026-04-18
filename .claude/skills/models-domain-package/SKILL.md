---
name: models-domain-package
description: >-
  Organiza domínios SQLAlchemy em pacotes sob models/<domínio>/ com entities,
  services, utils e constants; reexporta no __init__.py para compatibilidade.
  Use ao refatorar um modelo monolítico em pacote, ao criar um novo domínio de
  modelos, ou quando o usuário pedir estrutura tipo nota_fiscal/concreto em models/.
metadata:
  author: fortanks
  version: '1.0.0'
---

# Pacote de domínio em `models/<nome>/`

Padrão usado em **`models/nota_fiscal/`** e **`models/concreto/`**: separar ORM, constantes, utilitários puros e lógica de serviço, mantendo **`from models.<domínio> import ...`** estável.

## Estrutura alvo

```
models/<domínio>/
├── __init__.py          # Reexporta API pública (__all__)
├── constants.py         # CFOPs, nomes de tabelas, chaves compartilhadas (sem I/O)
├── entities/            # OU um único entities.py se o domínio for pequeno
│   ├── __init__.py      # Reexporta classes ORM
│   ├── <entidade>.py
│   └── ...
├── services/            # Regras de negócio que orquestram ORM + outros modelos
│   ├── __init__.py
│   └── <servico>.py
├── utils/               # Funções puras / helpers sem efeitos colaterais pesados
│   ├── __init__.py
│   └── <topico>.py
└── parsing/             # Opcional (ex.: nota_fiscal — XML, extração)
    └── ...
```

**Quando usar `entities/` em pasta** em vez de um só `entities.py`: várias tabelas/classes OU arquivos grandes; facilita navegação e imports relativos entre entidades do mesmo domínio.

**Referências no repositório**: `models/nota_fiscal/` (inclui `movimentacao_estoque.py`, `xml_utils.py` na raiz do pacote), `models/concreto/` (`entities/` + `utils/qualidade.py` + `services/producao_pecas.py`).

## Responsabilidades por camada

| Camada | Conteúdo | Evitar |
|--------|----------|--------|
| **constants** | Literais compartilhados, nomes de tabela alinhados a `__tablename__` | Lógica de negócio |
| **entities** | `db.Model`, relacionamentos, métodos de instância leves | Import circular pesado de `services` no topo do arquivo — preferir import lazy dentro de método |
| **services** | Fluxos (produção, importação, agregações), uso de vários modelos | Colocar ORM genérico aqui se for só CRUD da entidade |
| **utils** | JSON, datas, normalização, validações puras | Dependência de Flask `request` quando der para isolar |
| **parsing** | Leitura de XML/API, extração estruturada | Misturar com rotas Flask |

## `__init__.py` raiz do domínio

- Importar e reexportar o que o restante do monólito já usa: **`from models.<domínio> import Classe, funcao`**.
- Manter **`__all__`** explícito.
- Texto em **português** (docstring do pacote), alinhado ao projeto.

## Compatibilidade ao refatorar

1. Mapear todos os imports: `grep -r "models.<domínio>"` e `from models import` que tocam nas classes movidas.
2. Criar a nova árvore; mover código sem alterar comportamento na primeira passada (só paths de import).
3. Atualizar **`models/__init__.py`** se registrar modelos para `configure_mappers()` — continuar importando do pacote agregador (`from .<domínio> import ...`).
4. Remover arquivos antigos na raiz de `models/<domínio>/` só depois de nenhum import apontar para eles.
5. Rodar `python -m py_compile` nos módulos tocados; import completo do app pode exigir venv com dependências.

## Imports e ciclos

- **Entidade → serviço**: se inevitável no carregamento do módulo, usar **import dentro da função/método** (ex.: `produzir()` chama serviço).
- **Serviço → entidade**: imports absolutos `from models.<domínio>.entities.<mod> import ...` ou relativos `from ..entities...` desde que não crie ciclo com `__init__.py` do pacote.
- Ordem em **`entities/__init__.py`**: carregar módulos sem dependência cruzada primeiro (ex.: traços e usinagens antes de concretagens se esta importar serviços que referenciam usinagens em runtime).

## Novo domínio do zero

1. Criar `models/<domínio>/` com `constants.py` (mesmo que mínimo), `entities/`, `services/`, `utils/` conforme necessidade real — **não** criar pastas vazias só por simetria.
2. Definir modelos em `entities/`; registrar tabela com `__tablename__` (pode igualar constante em `constants.py`).
3. Colocar regras multi-modelo em `services/`.
4. Expor tudo necessário em `__init__.py`.
5. Adicionar imports em **`models/__init__.py`** para SQLAlchemy mapear as classes antes de `configure_mappers()`.

## Checklist rápido

**Refatoração**

- [ ] Estrutura de pastas criada; código movido com imports corrigidos
- [ ] `__init__.py` raiz reexporta a API antiga
- [ ] `models/__init__.py` atualizado se aplicável
- [ ] Arquivos legados removidos; grep sem referências quebradas
- [ ] `py_compile` ou subida do app ok

**Novo domínio**

- [ ] Entidades + migrations Alembic/Flask-Migrate se novas tabelas
- [ ] Serviços e utils só onde há lógica real
- [ ] Documentação de alto nível em **`CLAUDE.md`** (seção Architecture / models) se o domínio for relevante para outros devs

## Quando não aplicar

- Modelo único, menos de ~100 linhas, sem serviços — um arquivo `models/foo.py` continua aceitável.
- Lógica que é específica de **controller** ou **view** — não pertence em `models/`.
