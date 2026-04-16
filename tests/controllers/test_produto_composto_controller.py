import io
import importlib.util
import sys
import types
from pathlib import Path

from flask import Flask, Response
from flask_login import LoginManager


def _make_app():
    # App mínimo só para testar o blueprint do controller, sem importar `app.py`
    app = Flask(__name__)
    app.config.update(
        SECRET_KEY="teste",
        TESTING=True,
        WTF_CSRF_ENABLED=False,
        LOGIN_DISABLED=True,  # bypass do @login_required
    )
    LoginManager(app)
    return app


def _carregar_modulo_controller():
    """
    Carrega `controllers/cadastro_operacional/produto_composto_controller.py` sem executar
    `controllers/cadastro_operacional/__init__.py` (que puxa dependências de outros módulos).
    """
    raiz = Path(__file__).resolve().parents[2]  # .../tests/controllers -> repo root
    controllers_dir = raiz / "controllers"
    cadastro_dir = controllers_dir / "cadastro_operacional"

    # Garante pacote `controllers`
    if "controllers" not in sys.modules:
        pkg = types.ModuleType("controllers")
        pkg.__path__ = [str(controllers_dir)]
        sys.modules["controllers"] = pkg

    # Stub do pacote `controllers.cadastro_operacional` sem rodar __init__.py
    if "controllers.cadastro_operacional" not in sys.modules:
        pkg = types.ModuleType("controllers.cadastro_operacional")
        pkg.__path__ = [str(cadastro_dir)]
        sys.modules["controllers.cadastro_operacional"] = pkg

    # Dependências opcionais/pesadas que não são necessárias para estes testes
    # (permite importar models/utils sem instalar stack de PDF/imagem no ambiente)
    if "pdf2image" not in sys.modules:
        m = types.ModuleType("pdf2image")

        def _convert_from_bytes(*_args, **_kwargs):
            return []

        m.convert_from_bytes = _convert_from_bytes
        sys.modules["pdf2image"] = m

    if "pyzbar" not in sys.modules:
        pkg = types.ModuleType("pyzbar")
        pkg.__path__ = []
        sys.modules["pyzbar"] = pkg

    if "pyzbar.pyzbar" not in sys.modules:
        m = types.ModuleType("pyzbar.pyzbar")

        def _decode(*_args, **_kwargs):
            return []

        m.decode = _decode
        sys.modules["pyzbar.pyzbar"] = m

    if "xmltodict" not in sys.modules:
        m = types.ModuleType("xmltodict")

        def _parse(*_args, **_kwargs):
            return {}

        m.parse = _parse
        sys.modules["xmltodict"] = m

    mod_name = "controllers.cadastro_operacional.produto_composto_controller"
    if mod_name in sys.modules:
        return sys.modules[mod_name]

    path = cadastro_dir / "produto_composto_controller.py"
    spec = importlib.util.spec_from_file_location(mod_name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[mod_name] = module
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def test_importar_excel_rejeita_quando_nao_envia_arquivo(monkeypatch):
    controller = _carregar_modulo_controller()
    produto_composto_bp = controller.produto_composto_bp

    app = _make_app()
    app.register_blueprint(produto_composto_bp, url_prefix="/produto-composto")

    client = app.test_client()
    resp = client.post("/produto-composto/importar-excel", data={}, content_type="multipart/form-data")

    assert resp.status_code == 400
    payload = resp.get_json()
    assert payload["success"] is False
    assert "Nenhum arquivo" in payload["message"]


def test_importar_excel_rejeita_quando_filename_vazio(monkeypatch):
    controller = _carregar_modulo_controller()
    produto_composto_bp = controller.produto_composto_bp

    app = _make_app()
    app.register_blueprint(produto_composto_bp, url_prefix="/produto-composto")

    client = app.test_client()
    data = {"arquivo_excel": (io.BytesIO(b"conteudo"), "")}
    resp = client.post("/produto-composto/importar-excel", data=data, content_type="multipart/form-data")

    assert resp.status_code == 400
    payload = resp.get_json()
    assert payload["success"] is False
    assert "Nenhum arquivo selecionado" in payload["message"]


def test_importar_excel_rejeita_extensao_invalida(monkeypatch):
    controller = _carregar_modulo_controller()
    produto_composto_bp = controller.produto_composto_bp

    app = _make_app()
    app.register_blueprint(produto_composto_bp, url_prefix="/produto-composto")

    client = app.test_client()
    data = {"arquivo_excel": (io.BytesIO(b"conteudo"), "arquivo.txt")}
    resp = client.post("/produto-composto/importar-excel", data=data, content_type="multipart/form-data")

    assert resp.status_code == 400
    payload = resp.get_json()
    assert payload["success"] is False
    assert "Apenas arquivos Excel" in payload["message"]


def test_importar_excel_delega_para_service_e_remove_temp(tmp_path, monkeypatch):
    controller = _carregar_modulo_controller()
    produto_composto_bp = controller.produto_composto_bp

    app = _make_app()
    app.register_blueprint(produto_composto_bp, url_prefix="/produto-composto")
    client = app.test_client()

    temp_file = tmp_path / "import.xlsx"
    temp_file.write_bytes(b"fake")

    chamado = {"salvou": False, "importou": False, "removido": False}

    def _fake_salvar_upload_excel_temporario(_arquivo):
        chamado["salvou"] = True
        return str(temp_file)

    def _fake_importar(temp_path, sobrescrever):
        assert temp_path == str(temp_file)
        assert sobrescrever is True
        chamado["importou"] = True
        return {"success": True, "criados": 1, "atualizados": 0, "erros": 0, "erros_detalhes": []}

    def _fake_remove(path):
        assert path == str(temp_file)
        chamado["removido"] = True
        Path(path).unlink(missing_ok=True)

    monkeypatch.setattr(controller, "salvar_upload_excel_temporario", _fake_salvar_upload_excel_temporario)
    monkeypatch.setattr(controller, "importar_produtos_compostos_de_excel", _fake_importar)
    monkeypatch.setattr(controller.os, "remove", _fake_remove)

    data = {
        "arquivo_excel": (io.BytesIO(b"conteudo"), "import.xlsx"),
        "sobrescrever": "1",
    }
    resp = client.post("/produto-composto/importar-excel", data=data, content_type="multipart/form-data")

    assert resp.status_code == 200
    payload = resp.get_json()
    assert payload["success"] is True
    assert chamado["salvou"] is True
    assert chamado["importou"] is True
    assert chamado["removido"] is True


def test_exportar_excel_redireciona_quando_nenhum_selecionado(monkeypatch):
    controller = _carregar_modulo_controller()
    produto_composto_bp = controller.produto_composto_bp

    app = _make_app()
    app.register_blueprint(produto_composto_bp, url_prefix="/produto-composto")

    client = app.test_client()
    resp = client.post("/produto-composto/exportar-excel", data={})

    assert resp.status_code in (302, 303)
    assert "/produto-composto/" in resp.headers.get("Location", "")


def test_exportar_excel_delega_para_service_quando_encontra_produtos(monkeypatch):
    controller = _carregar_modulo_controller()
    produto_composto_bp = controller.produto_composto_bp

    class _QueryFake:
        def filter(self, *_args, **_kwargs):
            return self

        def all(self):
            return [object(), object()]

    class _IdColunaFake:
        def in_(self, _valores):
            return True

    class _ProdutoCompostoFake:
        id = _IdColunaFake()
        query = _QueryFake()

    app = _make_app()
    app.register_blueprint(produto_composto_bp, url_prefix="/produto-composto")
    client = app.test_client()

    chamado = {"exportou": False, "send_file": False}

    def _fake_exportar(produtos):
        assert len(produtos) == 2
        chamado["exportou"] = True
        return io.BytesIO(b"xlsx"), "arquivo.xlsx"

    def _fake_send_file(output, download_name, as_attachment, mimetype):
        assert download_name == "arquivo.xlsx"
        assert as_attachment is True
        assert "spreadsheetml" in mimetype
        chamado["send_file"] = True
        return Response(output.getvalue(), status=200, mimetype=mimetype)

    monkeypatch.setattr(controller, "ProdutoComposto", _ProdutoCompostoFake)
    monkeypatch.setattr(controller, "exportar_produtos_compostos_para_excel", _fake_exportar)
    monkeypatch.setattr(controller, "send_file", _fake_send_file)

    resp = client.post("/produto-composto/exportar-excel", data={"produto_ids": ["1", "2"]})
    assert resp.status_code == 200
    assert chamado["exportou"] is True
    assert chamado["send_file"] is True

