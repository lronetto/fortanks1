"""Exportação PDF (inspeção de pista) para concretagens."""

import io
import logging
import os
import shutil
from datetime import datetime

from flask import jsonify, send_file
from flask_login import login_required

from controllers.relatorios.commun import (
    _converter_excel_para_pdf_libreoffice,
    _criar_arquivo_temp_projeto,
    _limpar_arquivo_temp,
)

from models.concreto import ConcretoConcretagens

from .. import concretagem
from ..services.inspecao_pista_pdf import ODFPY_AVAILABLE, processar_ods_template_inspecao_pista


@concretagem.route('/api/<int:id>/pecas/exportar-pdf', methods=['GET'])
@login_required
def api_exportar_pecas_pdf(id):
    """Exporta peças de uma concretagem para PDF usando o template INSPECAO_PISTA.ods."""
    excel_path = None
    generated_pdf_path = None

    try:
        obj = ConcretoConcretagens.query.get_or_404(id)

        controllers_pkg = os.path.dirname(
            os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        )
        templates_dir = os.path.join(controllers_pkg, 'controllers', 'templates_excel')
        template_ods = os.path.join(templates_dir, 'INSPECAO_PISTA.ods')
        logging.debug('Template ODS inspeção pista: %s', template_ods)
        if not os.path.exists(template_ods):
            return jsonify({'error': 'Template INSPECAO_PISTA.ods não encontrado'}), 404

        if not ODFPY_AVAILABLE:
            return jsonify({'error': 'odfpy não está instalado. Instale com: pip install odfpy'}), 500

        excel_path = _criar_arquivo_temp_projeto(suffix='.ods', prefix='inspecao_pista_')
        shutil.copy2(template_ods, excel_path)

        processar_ods_template_inspecao_pista(excel_path, id, obj)

        generated_pdf_path = _converter_excel_para_pdf_libreoffice(excel_path)

        if not generated_pdf_path or not os.path.exists(generated_pdf_path):
            return jsonify({
                'error': 'Erro ao converter ODS para PDF. Verifique se o LibreOffice está instalado e configurado corretamente.'
            }), 500

        pdf_size = os.path.getsize(generated_pdf_path)
        if pdf_size == 0:
            return jsonify({'error': 'PDF gerado está vazio'}), 500

        output = io.BytesIO()
        with open(generated_pdf_path, 'rb') as f:
            output.write(f.read())
        output.seek(0)

        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f'inspecao_pista_{id}_{timestamp}.pdf'

        return send_file(
            output,
            mimetype='application/pdf',
            as_attachment=True,
            download_name=filename
        )

    except Exception as e:
        logging.error(f"Erro ao exportar PDF de peças: {str(e)}", exc_info=True)
        return jsonify({'error': f'Erro ao exportar PDF: {str(e)}'}), 500
    finally:
        if excel_path and os.path.exists(excel_path):
            _limpar_arquivo_temp(excel_path)
        if generated_pdf_path and os.path.exists(generated_pdf_path):
            _limpar_arquivo_temp(generated_pdf_path)
