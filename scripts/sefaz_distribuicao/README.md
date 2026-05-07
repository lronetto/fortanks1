# scripts/sefaz_distribuicao

Download de XMLs fiscais (NFe / CTe / NFSe Nacional) usando o **certificado
digital A1 da empresa** (`.pfx`/`.p12` + senha), com ingestão direta no
pipeline existente `models.nota_fiscal.NotaFiscal`.

## O que ele faz

Para um CNPJ e um intervalo `data_inicial..data_final`, baixa:

- **NF-e** — emitidas pela empresa **e** emitidas contra ela
  (papéis emitente, destinatário, transportador, autorizado-`autXML`),
  via WS SOAP `NFeDistribuicaoDFe` da Receita Federal.
- **CT-e** — emitidos pela empresa **e** contra ela, via
  WS SOAP `CTeDistribuicaoDFe`.
- **NFS-e Nacional (ADN)** — quando o município é aderente ao Sistema
  Nacional NFS-e, via API REST do `adn.nfse.gov.br` (papéis
  prestador/tomador/intermediário). Para municípios não aderentes,
  esse pedaço apenas registra warning e segue.

Cada XML baixado é repassado para `NotaFiscal(xml_data=xml_b64)`, que já
detecta o tipo, extrai os dados, verifica duplicidade pela `chave_acesso`
e persiste no banco.

## Como funciona internamente

| Documento | Serviço            | Filtra por data?                     |
|-----------|--------------------|--------------------------------------|
| NF-e      | `NFeDistribuicaoDFe` (SOAP)   | ❌ pagina por **NSU**; filtra-se em memória |
| CT-e      | `CTeDistribuicaoDFe` (SOAP)   | ❌ pagina por **NSU**                 |
| NFS-e     | API REST do ADN               | ✅ `dEmiInicial`/`dEmiFinal`          |

Os WS SEFAZ não aceitam intervalo de datas — devolvem ~50 documentos a
partir de um NSU. O cliente itera até `ultNSU == maxNSU` e só então
filtra pela `dhEmi` interna.

> **Otimização:** persista o último NSU consultado e use
> `--nsu-inicial-nfe` / `--nsu-inicial-cte` na próxima execução para
> baixar apenas o delta. O servidor SEFAZ guarda histórico por **3 anos**.

## Dependências adicionais

Adiciona `cryptography` ao `pyproject.toml` (já temos `requests`).

## Uso 1 — CLI standalone

```bash
python -m scripts.sefaz_distribuicao.cli \
    --pfx /etc/certs/empresa.pfx \
    --senha 'senhaA1' \
    --cnpj 12345678000199 \
    --inicio 2026-04-01 \
    --fim    2026-04-30 \
    --uf 35
```

A CLI cria o `app.app_context()` automaticamente, então `db.session`
funciona normalmente.

## Uso 2 — Rota Flask / dentro do app

```python
from datetime import date
from scripts.sefaz_distribuicao import baixar_e_importar

resumo = baixar_e_importar(
    caminho_pfx="/etc/certs/empresa.pfx",
    senha_certificado="senhaA1",
    cnpj="12345678000199",
    data_inicial=date(2026, 4, 1),
    data_final=date(2026, 4, 30),
    uf_autor=35,
)
return jsonify({
    "importadas": resumo.total_importadas,
    "ja_existentes": len(resumo.chaves_existentes),
    "erros": resumo.erros,
}), 200
```

> Isso encaixa naturalmente em `controllers/nota_fiscal/routes/importacoes.py`
> ao lado do `importar_arquivei` / `importar_xml` que já existem.

## Limitações conhecidas

1. **NFS-e municipal não-nacional**: cidades que **não** aderiram ao
   Sistema Nacional NFS-e (ex.: muitas capitais ainda usam ABRASF 2.x,
   GINFES, ISSNet ou padrão próprio) precisam de cliente específico —
   não há padrão único. O método `nfse_nacional.baixar_periodo` falha
   silenciosamente nestes casos e segue baixando NFe/CTe.
2. O Distribuição DF-e devolve, no `docZip` de NFe completa, somente
   notas em que sua empresa figura como **destinatária**. Para as
   próprias notas emitidas, a SEFAZ devolve apenas o **resumo**
   (`resNFe`); o XML completo deve ser consultado por
   `NFeConsultaProtocolo` ou ser obtido do seu próprio emissor.
3. Cada UF tem endpoint próprio para autorização de NFe, mas a
   **distribuição DF-e é centralizada** na Receita Federal
   (`www1.nfe.fazenda.gov.br`).

## Referências

- Manual de Orientação NFeDistribuicaoDFe (Nota Técnica 2014/002 - SEFAZ).
- Manual NFS-e Nacional - APIs do ADN (gov.br/nfse).
- WS Distribuição DF-e CT-e (cte.fazenda.gov.br).
