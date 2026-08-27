"""Saber si el ciclo de compras configurado se está usando de verdad.

Una empresa puede tener su proceso dibujado, validado y con responsables
asignados, y aun así el grafo NO gobernar nada: el motor arranca en `legacy` por
defecto y ahí las autorizaciones salen al correo fijo de configuración, no a los
responsables del canvas.

Desde el MCP no había forma de enterarse. `get_purchase_context` decía
`origen: "derivado"` y punto — una palabra que no significa nada para quien no
leyó el código.
"""
from unittest.mock import MagicMock, patch

from app.services.mcp_context import ApplicationActorContext
from app.services.workflow_lectura import estado_rollout, workflow_activo

WORKFLOW = {"id": "wf-1", "nombre": "Compras Vital", "estado": "activo", "version": 3,
            "nodos": [{"id": "n1", "tipo": "inicio", "label": "Solicitud"},
                      {"id": "n2", "tipo": "aprobacion", "label": "Aprobación financiera"}]}


def actor():
    return ApplicationActorContext("user-1", "org-1", "Vital", ("user-1",), client_id="codex")


def _contexto(*, modo="legacy", workflow=WORKFLOW, roles=None, vinculos=None):
    sb = MagicMock()
    cadena = sb.table.return_value.select.return_value.eq.return_value
    cadena.execute.return_value = MagicMock(data=roles if roles is not None else [
        {"id": "rol-1", "clave": "autorizador", "nombre": "Autorizador"},
    ])
    (sb.table.return_value.select.return_value.in_.return_value
     .execute.return_value) = MagicMock(data=vinculos if vinculos is not None else [
        {"rol_id": "rol-1", "responsables": {"nombre": "Juako", "email": "j@x.cl"}},
    ])
    return (
        patch("app.services.workflow_rollout.obtener_rollout",
              return_value={"execution_mode": modo}),
        patch("app.services.workflow_execution.obtener_workflow_activo", return_value=workflow),
        patch("app.services.supabase.get_supabase", return_value=sb),
    )


def _estado(**kwargs):
    a, b, c = _contexto(**kwargs)
    with a, b, c:
        return estado_rollout(actor())


def _workflow(**kwargs):
    a, b, c = _contexto(**kwargs)
    with a, b, c:
        return workflow_activo(actor())


# ─── El caso que motivó las tools ────────────────────────────────────────────

def test_ciclo_configurado_pero_motor_apagado_avisa():
    """El estado real de esta cuenta: canvas listo, grafo sin gobernar."""
    estado = _estado(modo="legacy", workflow=WORKFLOW)
    assert estado["workflow_activo"] is True
    assert estado["el_grafo_gobierna_las_compras"] is False
    assert "NO gobierna" in estado["aviso"]
    assert estado["configurar_en"].endswith("/settings/rollout")


def test_el_aviso_explica_la_consecuencia_no_solo_el_estado():
    """"legacy" no significa nada para quien no leyó el código."""
    aviso = _estado(modo="legacy", workflow=WORKFLOW)["aviso"]
    assert "correo fijo" in aviso
    assert "Compras Vital" in aviso, "nombra el ciclo que existe pero no se usa"


def test_sin_ciclo_configurado_manda_a_configurarlo():
    estado = _estado(workflow=None)
    assert estado["workflow_activo"] is False
    assert estado["configurar_en"].endswith("/settings/autorizaciones")
    assert "No hay ningún ciclo" in estado["aviso"]


def test_con_el_motor_encendido_no_hay_aviso():
    """Si el camino feliz avisa, se aprende a ignorar los avisos."""
    estado = _estado(modo="unified", workflow=WORKFLOW)
    assert estado["el_grafo_gobierna_las_compras"] is True
    assert estado["aviso"] is None
    assert "configurar_en" not in estado


def test_modo_compatibility_tambien_gobierna():
    assert _estado(modo="compatibility")["el_grafo_gobierna_las_compras"] is True


def test_un_ciclo_sin_motor_no_se_declara_gobernando():
    """Ni el modo solo ni el ciclo solo alcanzan: hacen falta los dos."""
    assert _estado(modo="unified", workflow=None)["el_grafo_gobierna_las_compras"] is False


# ─── El ciclo en sí ──────────────────────────────────────────────────────────

def test_devuelve_las_etapas_con_el_nombre_de_la_empresa():
    """Las etiquetas salen del canvas, no de un diccionario genérico."""
    etapas = _workflow()["etapas"]
    assert [e["label"] for e in etapas] == ["Solicitud", "Aprobación financiera"]


def test_marca_los_roles_sin_responsable():
    """Un rol vacío es un hueco real del proceso: se lista, no se omite."""
    roles = _workflow(vinculos=[])["roles"]
    assert roles[0]["clave"] == "autorizador"
    assert roles[0]["sin_responsable"] is True


def test_rol_con_responsable_lo_nombra():
    rol = _workflow()["roles"][0]
    assert rol["responsables"] == [{"nombre": "Juako", "email": "j@x.cl"}]
    assert rol["sin_responsable"] is False


def test_sin_workflow_devuelve_existe_false_con_link():
    resultado = _workflow(workflow=None)
    assert resultado["existe"] is False
    assert resultado["configurar_en"].endswith("/settings/autorizaciones")


def test_el_link_del_ciclo_lleva_a_su_canvas():
    assert _workflow()["configurar_en"].endswith("/settings/autorizaciones/canvas/wf-1")


# ─── Nunca lanza ─────────────────────────────────────────────────────────────

def test_un_rollout_ilegible_asume_legacy():
    """Ante la duda, el estado conservador: el grafo NO gobierna."""
    with patch("app.services.workflow_rollout.obtener_rollout", side_effect=Exception("caído")), \
         patch("app.services.workflow_execution.obtener_workflow_activo", return_value=None):
        estado = estado_rollout(actor())
    assert estado["execution_mode"] == "legacy"
    assert estado["el_grafo_gobierna_las_compras"] is False
