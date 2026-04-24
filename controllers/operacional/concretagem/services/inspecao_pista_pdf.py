"""Processamento do template ODS INSPECAO_PISTA para exportação PDF."""

import logging

from models.tanque import TanquesPecas

try:
    from odf.opendocument import load
    from odf.table import Table, TableRow, TableCell
    from odf.text import P
    from odf.style import PageLayout
    from odf.namespaces import STYLENS
    ODFPY_AVAILABLE = True
except ImportError:
    ODFPY_AVAILABLE = False
    load = Table = TableRow = TableCell = P = PageLayout = STYLENS = None


def aplicar_layout_pagina_horizontal_ods(doc):
    """Ajusta layouts ODS para paisagem e escala para caber em uma página."""
    if not ODFPY_AVAILABLE:
        return
    try:
        layouts = doc.getElementsByType(PageLayout)
        for layout in layouts:
            for child in (layout.childNodes or []):
                if getattr(child, 'qname', None) == (STYLENS, 'page-layout-properties'):
                    child.setAttribute('printorientation', 'landscape')
                    child.setAttribute('scaletopages', '1')
                    break
    except Exception as e:
        logging.warning(f"Não foi possível aplicar layout horizontal ao ODS: {e}")


def processar_ods_template_inspecao_pista(ods_path, concretagem_id, concretagem):
    """Substitui placeholders no template INSPECAO_PISTA.ods pelos dados das peças."""
    if not ODFPY_AVAILABLE:
        raise ImportError('odfpy não está disponível. Instale com: pip install odfpy')

    doc = load(ods_path)
    tables = doc.getElementsByType(Table)

    pecas_data = concretagem.get_pecas() if concretagem else []
    pecas_concretadas = []

    for peca_item in pecas_data:
        peca_nome = peca_item.get('nome') or peca_item.get('placa')
        tanque_id = peca_item.get('tanque_id') or peca_item.get('tanque')
        forma = peca_item.get('forma', 0)

        if peca_nome and tanque_id:
            try:
                tanque_id_int = int(tanque_id) if isinstance(tanque_id, str) else tanque_id
                peca_obj = TanquesPecas.query.filter_by(
                    nome=peca_nome,
                    tanque_id=tanque_id_int
                ).first()

                if peca_obj:
                    pecas_concretadas.append({
                        'nome': peca_nome,
                        'tipo': peca_obj.tipo,
                        'forma': forma,
                        'tanque_id': tanque_id_int,
                        'tanque_nome': peca_obj.tanque.nome if peca_obj.tanque else ''
                    })
            except (ValueError, TypeError) as e:
                logging.warning(f"Erro ao processar peça {peca_nome}: {str(e)}")
                continue

    for table in tables:
        rows = table.getElementsByType(TableRow)
        for row_idx, row in enumerate(rows):
            cells = row.getElementsByType(TableCell)
            for cell_idx, cell in enumerate(cells):
                original_text = ''
                paragraphs = cell.getElementsByType(P)

                if paragraphs:
                    for para in paragraphs:
                        para_text = ''
                        for node in para.childNodes:
                            if hasattr(node, 'data'):
                                para_text += str(node.data)
                            elif hasattr(node, 'nodeValue'):
                                para_text += str(node.nodeValue)
                        if para_text:
                            original_text += para_text

                if not original_text:
                    for node in cell.childNodes:
                        if hasattr(node, 'data'):
                            original_text += str(node.data)
                        elif hasattr(node, 'nodeValue'):
                            original_text += str(node.nodeValue)

                if original_text and len(original_text.strip()) > 0 and 1 < len(original_text) <= 5:
                    new_value = original_text

                    new_value = new_value.replace('{1}', str(concretagem_id))
                    new_value = new_value.replace('{4}', concretagem.data_concretagem.strftime('%d/%m/%Y') if concretagem.data_concretagem else '')
                    new_value = new_value.replace('{7}', concretagem.pista if concretagem.pista else '')

                    formas = list(range(13))
                    for forma in formas:
                        count = 0
                        for peca in pecas_concretadas:
                            if peca.get('forma') == forma:
                                new_value = new_value.replace(f'{{{7+forma}}}', str(forma))
                                new_value = new_value.replace(f'{{{19+forma}}}', str(peca['nome']))
                                new_value = new_value.replace(f'{{{31+forma}}}', str(peca['tipo']))

                                tipo_painel = 'FECHO' if peca['tipo'] == 'PF' else ('NORMAL' if peca['tipo'] in ['PN', 'P'] else 'ESPECIAL')
                                new_value = new_value.replace(f'{{{43+forma}}}', str(tipo_painel))
                                count += 1

                        if count == 0:
                            new_value = new_value.replace(f'{{{7+forma}}}', '')
                            new_value = new_value.replace(f'{{{19+forma}}}', '')
                            new_value = new_value.replace(f'{{{31+forma}}}', '')
                            new_value = new_value.replace(f'{{{43+forma}}}', '')

                    if new_value != original_text:
                        paragraphs_to_remove = cell.getElementsByType(P)
                        for para in paragraphs_to_remove:
                            cell.removeChild(para)

                        new_para = P()
                        new_para.addText(new_value)
                        cell.addElement(new_para)

    aplicar_layout_pagina_horizontal_ods(doc)
    doc.save(ods_path)
