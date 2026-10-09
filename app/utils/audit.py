import json

from app.models.audit_log import AuditLog


def create_audit_log(
    db,
    user_id: int,
    action: str,
    entity_type: str,
    entity_id: int | None = None,
    old_value=None,
    new_value=None
):
    audit = AuditLog(
        user_id=user_id,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        old_value=json.dumps(old_value) if old_value is not None else None,
        new_value=json.dumps(new_value) if new_value is not None else None
    )

    db.add(audit)