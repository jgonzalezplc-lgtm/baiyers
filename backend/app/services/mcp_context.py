"""Contexto de aplicación compartido por MCP y otros canales autenticados.

No verifica tokens: adapta una identidad que ya fue verificada por el borde
(FastAPI/Supabase hoy; OAuth MCP en la fase siguiente). Así la lógica de
negocio no depende de Request, headers ni de argumentos controlados por el
modelo.
"""
from dataclasses import dataclass, field
from typing import FrozenSet, Iterable, Optional

from fastapi import HTTPException

from app.services.auth_context import AuthContext


@dataclass(frozen=True)
class ApplicationActorContext:
    actor_user_id: str
    organization_id: str
    organization_name: str
    organization_user_ids: tuple[str, ...]
    is_admin: bool = False
    client_id: str = "baiyer-web"
    scopes: FrozenSet[str] = field(default_factory=frozenset)
    request_id: Optional[str] = None

    @classmethod
    def from_auth_context(
        cls,
        ctx: AuthContext,
        *,
        client_id: str = "baiyer-web",
        scopes: Iterable[str] = (),
        request_id: Optional[str] = None,
    ) -> "ApplicationActorContext":
        return cls(
            actor_user_id=ctx.actor_user_id,
            organization_id=ctx.organization_id,
            organization_name=ctx.organization_nombre,
            organization_user_ids=tuple(ctx.user_ids_organizacion),
            is_admin=ctx.es_admin,
            client_id=client_id,
            scopes=frozenset(scopes),
            request_id=request_id,
        )

    def require_scope(self, scope: str) -> None:
        if scope not in self.scopes:
            raise HTTPException(status_code=403, detail=f"Falta el scope requerido: {scope}")

    def require_admin(self) -> None:
        if not self.is_admin:
            raise HTTPException(status_code=403, detail="Esta operación requiere rol administrador")

    def to_auth_context(self) -> AuthContext:
        """Adapta hacia routers aún no extraídos, sin reconstruir identidad desde argumentos."""
        return AuthContext(
            actor_user_id=self.actor_user_id,
            organization_id=self.organization_id,
            organization_nombre=self.organization_name,
            user_ids_organizacion=list(self.organization_user_ids),
            es_admin=self.is_admin,
        )
