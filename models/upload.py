from datetime import datetime
from models.database import db
import base64
from sqlalchemy import Text

#tipo
#0 - nao definido
#1 - arquivei
#2 - protocolo
#3 - reembolso
#4 - avulso
#5 - certificado
#6 - DUA

class Upload(db.Model):
    __tablename__ = 'Uploads'
    id = db.Column(db.Integer, primary_key=True)
    pai_id = db.Column(db.Integer, nullable=True)
    pai = db.Column(db.String(255), nullable=True)
    tipo = db.Column(db.Integer, nullable=True)
    filename = db.Column(db.String(255), nullable=False)
    mimetype = db.Column(db.String(100), nullable=False)
    blob = db.Column(Text(length=4294967295), nullable=True)  # LONGTEXT
    uploaded_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    dados_adicionais = db.Column(db.Text, nullable=True)

    def __repr__(self):
        return f'<Upload {self.id} - {self.filename}>'
    
    def __init__(self, pai=None, pai_id=None, tipo=None, filename=None, mimetype=None, blob=None,dados_adicionais=None):

        #print('pai: ',pai)
        #print('pai_id: ',pai_id)
        #print('tipo: ',tipo)
        up = Upload.query.filter(Upload.pai==pai, Upload.pai_id==pai_id, Upload.tipo==tipo, Upload.filename==filename, Upload.mimetype==mimetype).first()
        if up:
            return False
            #print('upload: ',self)
        else:
            self.pai = pai
            self.pai_id = pai_id
            self.tipo = tipo
            self.filename = filename
            self.mimetype = mimetype
            self.dados_adicionais = dados_adicionais
            # Codifica o blob em base64 antes de salvar
            if isinstance(blob, bytes):
                self.blob = base64.b64encode(blob).decode('utf-8')
            else:
                self.blob = blob
            up = Upload.query.filter_by(filename=filename).first()
            if not up:
                self.save()
            else:
                self.id = up.id
                self.uploaded_at = up.uploaded_at
            self.save()
            return True
    def to_dict(self):
        return {
            'id': self.id,
            'filename': self.filename,
            'mimetype': self.mimetype,
            'uploaded_at': self.uploaded_at,
            'blob': self.blob
        }
    def save(self):
        try:
            db.session.add(self)
            db.session.commit()
            db.session.flush()
        except Exception as e:
            print('upload error: ',e)
            db.session.rollback()
            raise e

    def get_blob(self):
        """
        Retorna o blob decodificado do base64
        """
        if self.blob:
            return base64.b64decode(self.blob)
        return None

    def get(self, pai, pai_id, tipo=None):
        if tipo:
            return Upload.query.filter_by(pai=pai, pai_id=pai_id, tipo=tipo).all()
        else:
            return Upload.query.filter_by(pai=pai, pai_id=pai_id).all()
    
    def delete(self):
        try:
            db.session.delete(self)
            db.session.commit()
        except Exception as e:
            db.session.rollback()
            raise e
