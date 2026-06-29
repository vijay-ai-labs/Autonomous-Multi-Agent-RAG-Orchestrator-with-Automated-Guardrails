"""Unit tests for the RBAC access rules in ``core.access``."""

from uuid import uuid4

from core.access import UserScope, can_write_department, department_allowed


def _scope(role: str, departments: tuple[str, ...] = ()) -> UserScope:
    return UserScope(id=uuid4(), role=role, departments=departments)


# ── read rule: department_allowed ─────────────────────────────────────────


def test_admin_may_read_any_department():
    admin = _scope("admin")
    assert department_allowed(admin, "finance") is True
    assert department_allowed(admin, None) is True


def test_employee_may_read_own_department_and_shared():
    emp = _scope("employee", ("hr",))
    assert department_allowed(emp, "hr") is True
    assert department_allowed(emp, None) is True  # shared/no-narrowing


def test_employee_may_not_read_other_department():
    emp = _scope("employee", ("hr",))
    assert department_allowed(emp, "finance") is False


def test_manager_spans_all_its_departments():
    mgr = _scope("manager", ("hr", "it"))
    assert department_allowed(mgr, "hr") is True
    assert department_allowed(mgr, "it") is True
    assert department_allowed(mgr, "finance") is False


# ── write rule: can_write_department (stricter) ───────────────────────────


def test_only_admin_may_write_shared_docs():
    assert can_write_department(_scope("admin"), None) is True
    assert can_write_department(_scope("employee", ("hr",)), None) is False
    assert can_write_department(_scope("manager", ("hr",)), None) is False


def test_non_admin_may_write_only_own_department():
    emp = _scope("employee", ("hr",))
    assert can_write_department(emp, "hr") is True
    assert can_write_department(emp, "finance") is False
