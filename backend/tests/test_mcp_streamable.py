import pytest
from fastapi.testclient import TestClient
from mcp.server.auth.provider import AccessToken

from app.main import app


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as value:
        yield value


def test_streamable_http_sin_token_responde_401_con_resource_metadata(client):
    response = client.post("/api/mcp", json={
        "jsonrpc": "2.0", "id": 1, "method": "initialize",
        "params": {"protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": {"name": "test", "version": "1"}},
    })
    assert response.status_code == 401
    challenge = response.headers.get("www-authenticate", "")
    assert challenge.startswith("Bearer")
    assert "resource_metadata=" in challenge
    assert "/.well-known/oauth-protected-resource/api/mcp" in challenge


def test_discovery_publica_endpoint_unico_y_scopes(client):
    auth = client.get("/.well-known/oauth-authorization-server")
    resource = client.get("/.well-known/oauth-protected-resource")
    resource_path = client.get("/.well-known/oauth-protected-resource/api/mcp")
    assert auth.status_code == 200
    assert auth.json()["code_challenge_methods_supported"] == ["S256"]
    assert auth.json()["token_endpoint_auth_methods_supported"] == ["none"]
    assert "lists:read" in auth.json()["scopes_supported"]
    assert resource.json()["resource"].endswith("/api/mcp")
    assert resource_path.status_code == 200
    assert resource_path.json()["resource"].endswith("/api/mcp")
    assert "lists:read" in resource_path.json()["scopes_supported"]


def test_oauth_error_no_se_envuelve_en_detail(client):
    response = client.post("/api/mcp/oauth/register", json={"redirect_uris": ["http://evil.example/callback"]})
    assert response.status_code == 400
    assert response.json()["error"] == "invalid_client_metadata"
    assert "detail" not in response.json()


def test_initialize_y_tools_list_usan_jsonrpc_estandar(client, monkeypatch):
    async def verified(_raw):
        return AccessToken(
            token="test", client_id="test-client", scopes=["lists:read"],
            resource="http://localhost:8000/api/mcp", subject="user-1",
            claims={"organization_id": "org-1"},
        )

    from app.mcp.streamable import mcp
    monkeypatch.setattr(mcp._token_verifier, "verify_token", verified)
    headers = {
        "Authorization": "Bearer test",
        "Accept": "application/json, text/event-stream",
        "MCP-Protocol-Version": "2025-06-18",
    }
    initialized = client.post("/api/mcp", headers=headers, json={
        "jsonrpc": "2.0", "id": 1, "method": "initialize",
        "params": {"protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": {"name": "test", "version": "1"}},
    })
    assert initialized.status_code == 200
    assert initialized.json()["result"]["serverInfo"]["name"] == "Baiyer"

    tools = client.post("/api/mcp", headers=headers, json={"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}})
    assert tools.status_code == 200
    names = {tool["name"] for tool in tools.json()["result"]["tools"]}
    assert {
        "baiyer_status", "list_lists", "get_list", "create_list", "rename_list",
        "add_list_items", "update_list_item", "remove_list_item",
        "start_project_intake", "continue_project_intake", "commit_project_intake",
        "preview_document_import", "commit_document_import",
        "get_job", "list_jobs", "cancel_job", "start_web_quote",
        "search_alternatives", "get_web_quote", "get_item_quotes", "get_list_coverage",
        "suggest_suppliers", "get_supplier_matrix", "set_supplier_matrix",
        "select_supplier_for_item",
        "prepare_rfq", "get_rfq_preview", "update_rfq_draft", "send_rfq",
        "get_rfq_status", "sync_supplier_replies", "list_supplier_replies",
        "get_supplier_reply", "apply_reply_proposal", "reject_reply_proposal",
        "compare_item", "compare_list", "explain_quote_recommendation",
        "select_final_quote", "clear_final_quote", "get_approval_status",
        "get_approval_route", "request_approval", "approve_request",
        "reject_request", "list_workflow_events",
        "prepare_purchase_order", "create_purchase_order", "list_purchase_orders",
        "get_purchase_order", "update_purchase_order", "send_purchase_order",
        "get_purchase_order_tracking", "preview_invoice_import",
        "commit_invoice_import", "list_invoices", "get_invoice",
        "reconcile_invoice_po", "match_invoice_to_po", "mark_invoice_paid",
        "scan_invoice_inbox",
        "search_suppliers", "get_supplier", "create_supplier", "update_supplier",
        "research_supplier", "preview_supplier_import", "commit_supplier_import",
        "block_supplier", "unblock_supplier", "set_supplier_categories",
        "get_supplier_history", "generate_list_report", "get_spend_metrics",
        "get_supplier_metrics",
        "describe_query_schema", "query_baiyer_data",
    }.issubset(names)


def test_resources_y_prompts_fase_8_se_publican(client, monkeypatch):
    async def verified(_raw):
        return AccessToken(token="test", client_id="test-client", scopes=["lists:read"],
                           resource="http://localhost:8000/api/mcp", subject="user-1",
                           claims={"organization_id": "org-1"})
    from app.mcp.streamable import mcp
    monkeypatch.setattr(mcp._token_verifier, "verify_token", verified)
    headers = {"Authorization": "Bearer test", "Accept": "application/json, text/event-stream",
               "MCP-Protocol-Version": "2025-06-18"}
    resources = client.post("/api/mcp", headers=headers, json={"jsonrpc": "2.0", "id": 3, "method": "resources/templates/list", "params": {}})
    prompts = client.post("/api/mcp", headers=headers, json={"jsonrpc": "2.0", "id": 4, "method": "prompts/list", "params": {}})
    assert resources.status_code == 200
    assert "baiyer://lists/{list_id}" in {r["uriTemplate"] for r in resources.json()["result"]["resourceTemplates"]}
    assert {"quote_project", "reconcile_invoice"}.issubset({p["name"] for p in prompts.json()["result"]["prompts"]})
