from io import BytesIO
from flask import Blueprint, jsonify, render_template, request, send_file, current_app, url_for
from sqlalchemy.orm import defer
from werkzeug.utils import secure_filename
from sqlalchemy import or_
from models.upload import Upload
from models.database import db

upload_bp = Blueprint('uploads', __name__)


def extensao_permitida(filename):
    if '.' not in filename:
        return False
    ext = filename.rsplit('.', 1)[1].lower()
    return ext in current_app.config.get('ALLOWED_EXTENSIONS', set())


@upload_bp.route('/', defaults={'upload_id': None}, methods=['GET'])
def index(upload_id=None):
    return render_template('admin/uploads/index.html')


@upload_bp.route('/datatables', methods=['POST'])
def datatables():
    draw = int(request.form.get('draw', 1))
    start = int(request.form.get('start', 0))
    length = int(request.form.get('length', 25))
    search_value = (request.form.get('search[value]') or '').strip()

    filename = (request.form.get('filename') or '').strip()
    pai = (request.form.get('pai') or '').strip()
    tipo = (request.form.get('tipo') or '').strip()
    dados_adicionais = (request.form.get('dados_adicionais') or '').strip()

    query = Upload.query.options(defer(Upload.blob))
    total_records = query.count()

    if filename:
        query = query.filter(Upload.filename.ilike(f'%{filename}%'))
    if pai:
        query = query.filter(Upload.pai.ilike(f'%{pai}%'))
    if tipo:
        query = query.filter(Upload.tipo == tipo)
    if dados_adicionais:
        query = query.filter(Upload.dados_adicionais.ilike(f'%{dados_adicionais}%'))

    if search_value:
        query = query.filter(
            or_(
                Upload.filename.ilike(f'%{search_value}%'),
                Upload.pai.ilike(f'%{search_value}%'),
                Upload.dados_adicionais.ilike(f'%{search_value}%'),
            )
        )

    records_filtered = query.count()

    col_map = {
        0: Upload.id,
        1: Upload.filename,
        2: Upload.pai,
        3: Upload.pai_id,
        4: Upload.tipo,
        5: Upload.mimetype,
        6: Upload.uploaded_at,
    }
    col_idx = int(request.form.get('order[0][column]', 6))
    direction = request.form.get('order[0][dir]', 'desc')
    order_col = col_map.get(col_idx, Upload.uploaded_at)
    order_col = order_col.desc() if direction == 'desc' else order_col.asc()

    uploads = query.order_by(order_col).offset(start).limit(length).all()

    data = []
    for upload in uploads:
        data.append(
            {
                'id': upload.id,
                'filename': upload.filename or '',
                'pai': upload.pai or '',
                'pai_id': upload.pai_id or '',
                'tipo': upload.tipo or '',
                'mimetype': upload.mimetype or '',
                'uploaded_at': upload.uploaded_at.strftime('%d/%m/%Y %H:%M') if upload.uploaded_at else '',
                'uploaded_at_sort': upload.uploaded_at.strftime('%Y-%m-%d %H:%M:%S') if upload.uploaded_at else '',
                'dados_adicionais': upload.dados_adicionais or '',
                'download_url': url_for('uploads.download_upload', upload_id=upload.id),
                'excluir_url': url_for('uploads.excluir_upload', upload_id=upload.id),
            }
        )

    return jsonify(
        {
            'draw': draw,
            'recordsTotal': total_records,
            'recordsFiltered': records_filtered,
            'data': data,
        }
    )


@upload_bp.route('/download/<int:upload_id>', methods=['GET'])
def download_upload(upload_id):
    upload = Upload.query.get_or_404(upload_id)
    nome_seguro = secure_filename(upload.filename) or 'download'
    return send_file(BytesIO(upload.blob), as_attachment=True, download_name=nome_seguro)


@upload_bp.route('/excluir/<int:upload_id>', methods=['POST'])
def excluir_upload(upload_id):
    upload = Upload.query.get_or_404(upload_id)
    try:
        db.session.delete(upload)
        db.session.commit()
        return jsonify({'success': True, 'message': 'Upload excluido com sucesso.'})
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': f'Erro ao excluir upload: {str(e)}'}), 500