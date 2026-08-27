"""Baiyer ya sabe quién es el usuario: no hay que preguntárselo por chat.

`baiyer_status` devolvía sólo el id y el nombre de la organización, así que un
cliente MCP terminaba pidiendo por chat el correo, la dirección o quién autoriza
—datos que el usuario ya cargó una vez y están en la base.
"""
from unittest.mock import MagicMock, patch

from app.services.contexto_identidad import contexto_identidad
from app.services.mcp_context import ApplicationActorContext

PERFIL = {"rut": "76.123.456-7", "industria": "Tecnología", "pais": "Chile",
          "sitio_web": "https://vital.cl", "direccion": "Av. Providencia 1234"}
DESPACHO = {"direccion_despacho": "Bodega Central, Maipú", "despacho_contacto": "Paula Soto"}


def actor():
    return ApplicationActorContext("user-1", "org-1", "Vital", ("user-1", "user-2"),
                                   is_admin=True, client_id="codex")


def _identidad(*, perfil=PERFIL, despacho=DESPACHO, responsables=None, roles=None, falla=None):
    responsables = responsables if responsables is not None else [
        {"id": "r1", "nombre": "Juako", "email": "j.gonzalez.plc@gmail.com", "cargo": "Gerente"},
    ]
    sb = MagicMock()
    sb.table.return_value.select.return_value.in_.return_value.execute.return_value = MagicMock(
        data=roles if roles is not None else [
            {"responsable_id": "r1", "workflow_roles": {"clave": "autorizador"}},
        ]
    )
    usuario = MagicMock()
    usuario.user.email = "jogonzalezp@udd.cl"
    usuario.user.user_metadata = {"nombre_usuario": "Joaquín"}
    sb.auth.admin.get_user_by_id.return_value = usuario

    with patch("app.services.supabase.get_supabase", return_value=sb), \
         patch("app.services.organizacion.obtener_perfil_organizacion",
               side_effect=falla or (lambda _o: perfil)), \
         patch("app.services.organizacion.obtener_despacho_organizacion", return_value=despacho), \
         patch("app.services.workflow_service.listar_responsables",
               side_effect=lambda uid, **_k: responsables if uid == "user-1" else []):
        return contexto_identidad(actor())


# ─── Lo que ahora viaja ──────────────────────────────────────────────────────

def test_trae_al_usuario():
    usuario = _identidad()["usuario"]
    assert usuario["email"] == "jogonzalezp@udd.cl"
    assert usuario["nombre"] == "Joaquín"
    assert usuario["es_admin"] is True


def test_trae_el_perfil_de_la_empresa():
    org = _identidad()["organizacion"]
    assert org["nombre"] == "Vital"
    assert org["rut"] == "76.123.456-7"
    assert org["industria"] == "Tecnología"


def test_trae_los_roles_con_su_persona():
    roles = _identidad()["roles"]
    assert roles == [{"nombre": "Juako", "email": "j.gonzalez.plc@gmail.com",
                      "cargo": "Gerente", "roles": ["autorizador"]}]


def test_los_roles_cubren_a_toda_la_organizacion():
    """Quien autoriza rara vez es quien inicia la compra."""
    identidad = _identidad(responsables=[{"id": "r1", "nombre": "Juako", "email": "j@x.cl"}])
    assert identidad["roles"], "debe listar responsables de otros miembros también"


# ─── Las dos direcciones no se mezclan ───────────────────────────────────────

def test_la_direccion_administrativa_va_etiquetada_como_tal():
    """No es un destino de entrega: la scrapea el onboarding y no está verificada."""
    org = _identidad()["organizacion"]
    assert org["direccion_administrativa"] == "Av. Providencia 1234"
    assert "direccion" not in org, "el nombre a secas invita a usarla como despacho"


def test_el_despacho_va_aparte_y_declara_si_esta_configurado():
    org = _identidad()["organizacion"]
    assert org["despacho"]["direccion_despacho"] == "Bodega Central, Maipú"
    assert org["despacho_configurado"] is True


def test_sin_despacho_lo_dice_explicito():
    org = _identidad(despacho={})["organizacion"]
    assert org["despacho"] is None
    assert org["despacho_configurado"] is False


# ─── Nunca lanza: un bloque roto no puede dejar sin estado al cliente ────────

def test_un_perfil_que_falla_no_tumba_el_resto():
    identidad = _identidad(falla=lambda _o: (_ for _ in ()).throw(Exception("supabase caído")))
    assert identidad["organizacion"]["id"] == "org-1"
    assert identidad["usuario"]["user_id"] == "user-1"
    assert "roles" in identidad


def test_sin_responsables_devuelve_lista_vacia():
    assert _identidad(responsables=[])["roles"] == []


def test_un_responsable_sin_rol_asignado_igual_aparece():
    """Está cargado como persona aunque nadie le haya dado un rol todavía."""
    roles = _identidad(roles=[])["roles"]
    assert roles[0]["nombre"] == "Juako"
    assert roles[0]["roles"] == []
