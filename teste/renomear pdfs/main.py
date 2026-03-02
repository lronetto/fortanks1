"""
Script para renomear PDFs pela chave de acesso da nota (código de barras/QR) e copiar para output.
- Antes de copiar: remove páginas em branco.
- Com chave: busca NotaFiscal; se tiver fatura/vencimento em dados_adicionais, renomeia para
  dd-mm-aa TIPO numero_nf nome_emitente (TIPO = CTE, NF ou NFS); senão usa chave.pdf.
- Sem chave: copia com o nome original.
"""
import io
import json
import os
import re
import sys
from datetime import datetime, timedelta
from pathlib import Path

# Path do projeto (raiz fortanks_novo) para imports
PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from dotenv import load_dotenv
load_dotenv(PROJECT_ROOT / ".env")

from PyPDF2 import PdfReader, PdfWriter
from pdf2image import convert_from_bytes

from utils.utils import validar_chave_acesso, extrair_chave_do_pdf
from models.nota_fiscal import NotaFiscal


def _pagina_em_branco(imagem, limiar_media=250):
    """Retorna True se a imagem (PIL) for considerada página em branco (quase só pixels claros)."""
    try:
        img = imagem.resize((80, 80)).convert("L")
        dados = list(img.getdata())
        if not dados:
            return True
        media = sum(dados) / len(dados)
        return media >= limiar_media
    except Exception:
        return False


def _remover_paginas_em_branco(payload):
    """
    Detecta páginas em branco, remove e retorna (novo_payload, qtd_removidas).
    Se não houver páginas em branco, retorna (payload_original, 0).
    """
    if not payload or len(payload) < 100:
        return payload, 0
    try:
        reader = PdfReader(io.BytesIO(payload))
        num_paginas = len(reader.pages)
        if num_paginas <= 0:
            return payload, 0

        poppler_path = "/usr/bin" if sys.platform == "linux" else None
        imagens = convert_from_bytes(payload, 150, poppler_path=poppler_path)
        if len(imagens) != num_paginas:
            return payload, 0

        indices_nao_em_branco = [i for i, img in enumerate(imagens) if not _pagina_em_branco(img)]
        removidas = num_paginas - len(indices_nao_em_branco)
        if removidas == 0:
            return payload, 0

        writer = PdfWriter()
        for i in indices_nao_em_branco:
            writer.add_page(reader.pages[i])
        buf = io.BytesIO()
        writer.write(buf)
        return buf.getvalue(), removidas
    except Exception:
        return payload, 0


def _tipo_label(tipo):
    """Retorna CTE, NF ou NFS conforme tipo da nota."""
    if tipo in (0, 1):
        return "NF"
    if tipo == 2:
        return "CTE"
    if tipo == 3:
        return "NFS"
    return "NF"


def _nome_arquivo_seguro(nome):
    """Remove caracteres inválidos para nome de arquivo e limita tamanho."""
    if not nome:
        return "emitente"
    s = re.sub(r'[<>:"/\\|?*]', "_", str(nome).strip())
    s = re.sub(r"\s+", " ", s).strip()
    return s[:80] if len(s) > 80 else s or "emitente"


def listar_nomes_sem_extensao(pasta_ler=None):
    """
    Cria uma lista com os nomes dos arquivos da pasta 'ler', sem extensão.
    Se pasta_ler não for informada, usa a pasta 'ler' ao lado do script.
    Retorna lista de strings (nomes sem extensão).
    """
    if pasta_ler is None:
        base = Path(__file__).resolve().parent
        pasta_ler = base / "ler"
    pasta = Path(pasta_ler)
    if not pasta.is_dir():
        return []
    return [p.stem for p in pasta.iterdir() if p.is_file()]


def _nome_nota_fiscal(nota):
    """Monta o nome: TIPO numero_nf nome_emitente."""
    tipo_str = _tipo_label(nota.tipo)
    nome_safe = _nome_arquivo_seguro(nota.nome_emitente)
    return f"{tipo_str} {nota.numero_nf} {nome_safe}.pdf"

def _nome_por_nota_e_vencimento(nota, vencimento):
    """Monta o nome: dd-mm-aa TIPO numero_nf nome_emitente."""
    dd_mm_aa = vencimento.strftime("%d-%m-%y")
    
    return f"{dd_mm_aa} {_nome_nota_fiscal(nota)}"


def _obter_vencimento_dados_adicionais(nota):
    """Obtém vencimento de dados_adicionais (fatura ou faturamento)."""
    if not nota.dados_adicionais:
        return None
    try:
        dados = json.loads(nota.dados_adicionais) if isinstance(nota.dados_adicionais, str) else nota.dados_adicionais
        if not isinstance(dados, dict):
            return None
        for key in ("fatura", "faturamento"):
            fat = dados.get(key)
            if isinstance(fat, dict):
                venc = fat.get("vencimento")
                if venc:
                    return datetime.strptime(venc, "%Y-%m-%d")
    except (ValueError, TypeError, KeyError):
        pass
    return None


def main():
    from app import app

    base = Path(__file__).resolve().parent
    input_dir = base / "input"
    output_dir = base / "output"
   
    if not input_dir.is_dir():
        input_dir = base
    output_dir.mkdir(parents=True, exist_ok=True)

    pdfs = list(input_dir.glob("*.pdf"))
    if not pdfs:
        print(f"Nenhum PDF encontrado em {input_dir}")
        return

    print(f"Processando {len(pdfs)} arquivo(s) de {input_dir} -> {output_dir}")
    if False:
        with app.app_context():
            for path in pdfs:
                try:
                    payload = path.read_bytes()
                    payload, qtd_removidas = _remover_paginas_em_branco(payload)
                    if qtd_removidas > 0:
                        print(f"  [páginas em branco] {path.name}: {qtd_removidas} página(s) removida(s)")
                    chave = extrair_chave_do_pdf(payload)
                    if chave:
                        nota = NotaFiscal.query.filter_by(chave_acesso=chave).first()
                        vencimento = None
                        if nota:
                            vencimento = _obter_vencimento_dados_adicionais(nota) or nota.get_vencimento()
                            if not vencimento:
                                vencimento = (nota.data_emissao+timedelta(days=30)).strftime("%d-%m-%y")
                                dest_name = f'{vencimento} {_nome_nota_fiscal(nota)}'
                                print(f"  [sem vencimento] {path.name} -> {dest_name}")
                            else:
                                dest_name = _nome_por_nota_e_vencimento(nota, vencimento)
                                print(f"  [chave+vencimento] {path.name} -> {dest_name}")
                        else:

                            dest_name = f"{chave}.pdf"
                            print(f"  [chave] {path.name} -> {dest_name}")
                    else:
                        dest_name = path.name
                        print(f"  [sem chave] {path.name} -> {dest_name}")

                    dest = output_dir / dest_name
                    if dest.resolve() == path.resolve():
                        continue
                    if dest.exists() and dest.stat().st_size != path.stat().st_size:
                        dest = output_dir / f"{dest.stem}_{path.stem}{dest.suffix}"
                        print(f"  -> renomeado para {dest.name} (evitar sobrescrever)")
                    dest.write_bytes(payload)

                except Exception as e:
                    print(f"  ERRO {path.name}: {e}")

    nomes_sem_extensao = listar_nomes_sem_extensao()
    for nome in nomes_sem_extensao:
        print(f"{nome}")
if __name__ == "__main__":
    main()
