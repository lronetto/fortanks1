# Download de XMLs Fiscais (NFe / CTe / NFSe) com certificado A1

Este módulo baixa, em um intervalo de datas, todos os XMLs de:

- **NF-e** (mercadorias) — emitidas pela empresa **e** emitidas contra
  ela (papéis emitente, destinatário, transportador, autorizado-`autXML`).
- **CT-e** (transporte) — emitidos pela empresa **e** contra ela
  (emitente, tomador, remetente, destinatário, expedidor, recebedor).
- **NFS-e Nacional (ADN)** — quando o município é aderente ao Sistema
  Nacional NFS-e (papéis prestador / tomador / intermediário).

A autenticação é feita 100% por **mTLS com certificado digital A1**
(arquivo `.pfx` / `.p12` + senha) — não há login/senha de portal.

---

## Como funciona

| Documento | Serviço            | Filtra por data? |
|-----------|--------------------|------------------|
| NF-e      | `NFeDistribuicaoDFe` (SOAP, Receita Federal) | ❌ paginação por NSU; filtra-se em memória |
| CT-e      | `CTeDistribuicaoDFe` (SOAP, Receita Federal) | ❌ paginação por NSU; filtra-se em memória |
| NFS-e     | API REST do ADN (`adn.nfse.gov.br`)          | ✅ `dEmiInicial`/`dEmiFinal` |

Os WS de NFe/CTe **não aceitam intervalo de datas**: eles devolvem,
a partir de um NSU (Número Sequencial Único), os próximos ~50
documentos. O cliente itera até `ultNSU == maxNSU` e só então aplica
o filtro `data_inicial..data_final` sobre a `dhEmi` interna do XML.

> **Dica de produção:** persista o último NSU consultado (em banco)
> e passe em `nsu_inicial` na próxima execução para baixar apenas
> o delta — o servidor mantém o histórico por **3 anos**.

---

## Instalação

```bash
pip install requests cryptography
```

(Já temos `requests`/`cryptography` no `requirements.txt`.)

---

## Uso programático

```python
from datetime import date
from modulos.download_xml import baixar_xmls_periodo

pacote = baixar_xmls_periodo(
    caminho_pfx="/etc/certs/empresa.pfx",
    senha_certificado="senhaA1",
    cnpj="12345678000199",
    data_inicial=date(2026, 4, 1),
    data_final=date(2026, 4, 30),
    uf_autor=35,            # SP
    ambiente=1,             # 1=produção, 2=homologação
    diretorio_saida="./saida_xmls",
)
print(len(pacote.nfe_emitidas), len(pacote.nfe_recebidas))
```

## Uso pela linha de comando

```bash
python -m modulos.download_xml.exemplos.baixar_periodo \
    --pfx /etc/certs/empresa.pfx \
    --senha 'senhaA1' \
    --cnpj 12345678000199 \
    --inicio 2026-04-01 \
    --fim    2026-04-30 \
    --uf 35
```

Saída em disco:

```
saida_xmls/
├── nfe/
│   ├── emitidas/<chave>.xml
│   └── recebidas/<chave>.xml
├── cte/
│   ├── emitidos/<chave>.xml
│   └── recebidos/<chave>.xml
└── nfse/
    ├── prestador/<chave>.xml
    ├── tomador/<chave>.xml
    └── intermediario/<chave>.xml
```

---

## Limitações conhecidas

1. **NFS-e municipal não-nacional**: cidades que **não** aderiram ao
   Sistema Nacional NFS-e (ex.: muitas capitais ainda usam ABRASF 2.x,
   GINFES, ISSNet ou padrão próprio) precisam de cliente específico —
   não há padrão único. O método `nfse_nacional.baixar_periodo` falha
   silenciosamente nestes casos e segue baixando NFe/CTe.
2. O Distribuição DF-e devolve, no `docZip` de NFe completa, somente
   notas em que sua empresa figura como **destinatária**. Para as
   próprias notas emitidas, a SEFAZ devolve apenas o **resumo**
   (`resNFe`); o XML completo deve ser consultado pelo serviço
   `NFeConsultaProtocolo` ou ser obtido do seu próprio emissor.
3. Cada UF possui um endpoint próprio para autorização de NFe, mas a
   **distribuição DF-e é centralizada na Receita Federal** (Ambiente
   Nacional) — por isso usamos `www1.nfe.fazenda.gov.br`.

---

## Referências

- Manual de Orientação NFeDistribuicaoDFe (Nota Técnica 2014/002 - SEFAZ).
- Manual NFS-e Nacional - APIs do ADN (gov.br/nfse - v1.2 out/2025).
- Portal NF-e — endpoints de webservice por UF.
