from io import BytesIO
from flask import Blueprint, render_template, request, send_file
from models.upload import Upload

upload_bp = Blueprint('upload', __name__)

@upload_bp.route('/', defaults={'upload_id': None}, methods=['GET'])
def list_uploads():
    filename = request.args.get('filename', '').strip()
    pai = request.args.get('pai', '').strip()
    tipo = request.args.get('tipo', '').strip()

    query = Upload.query
    if filename:
        query = query.filter(Upload.filename.ilike(f'%{filename}%'))
    if pai:
        query = query.filter(Upload.pai.ilike(f'%{pai}%'))
    if tipo:
        query = query.filter(Upload.tipo == tipo)
    uploads = query.order_by(Upload.uploaded_at.desc()).all()

    return render_template('uploads_list.html', uploads=uploads) 
@upload_bp.route('/download/<int:upload_id>', methods=['GET'])
def download_upload(upload_id):
    upload = Upload.query.get_or_404(upload_id)
    return send_file(BytesIO(upload.blob), as_attachment=True, download_name=upload.filename)   