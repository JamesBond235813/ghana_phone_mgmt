from dataclasses import dataclass, field

from app.core.permissions import PermissionCode, ScopeKind


@dataclass(slots=True)
class Scope:
    kind: ScopeKind
    values: set[str] = field(default_factory=set)

    def includes(self, *, country: str | None = None, organization_id: int | None = None,
                 location_id: int | None = None, owner_id: int | None = None,
                 actor_id: int | None = None) -> bool:
        if self.kind == ScopeKind.ALL:
            return True
        if self.kind == ScopeKind.COUNTRY:
            return country is not None and country in self.values
        if self.kind == ScopeKind.ORGANIZATION:
            return organization_id is not None and str(organization_id) in self.values
        if self.kind == ScopeKind.LOCATION:
            return location_id is not None and str(location_id) in self.values
        return owner_id is not None and actor_id == owner_id


@dataclass(slots=True)
class AccessContext:
    user_id: int
    permissions: set[PermissionCode] = field(default_factory=set)
    scopes: dict[PermissionCode, list[Scope]] = field(default_factory=dict)

    def can(self, permission: PermissionCode) -> bool:
        return permission in self.permissions

    def can_access(self, permission: PermissionCode, *, country: str | None = None,
                   organization_id: int | None = None, location_id: int | None = None,
                   owner_id: int | None = None) -> bool:
        if not self.can(permission):
            return False
        rules = self.scopes.get(permission, [])
        return any(rule.includes(country=country, organization_id=organization_id,
                                 location_id=location_id, owner_id=owner_id,
                                 actor_id=self.user_id) for rule in rules)


def require_access(context: AccessContext, permission: PermissionCode, **resource_scope: object) -> None:
    if not context.can_access(permission, **resource_scope):
        raise PermissionError(f"没有权限: {permission}")
