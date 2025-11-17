"""Client self-service portal for Netcup API Filter.
Provides token-based login and DNS record management UI backed by the existing API.
"""
from __future__ import annotations

from datetime import datetime
from functools import wraps
from typing import Any, Dict, List, Optional, Tuple

from flask import (
    Blueprint,
    abort,
    current_app,
    flash,
    g,
    redirect,
    render_template,
    request,
    session,
    url_for,
)

SESSION_KEY = "client_portal_token"
client_portal_bp = Blueprint(
    "client_portal",
    __name__,
    template_folder="templates/client",
    url_prefix="/client",
)


def _get_access_control():
    """Return the active AccessControl instance if available."""
    return current_app.config.get("access_control")


def _load_token_from_session() -> Tuple[Optional[str], Optional[Dict[str, Any]]]:
    """Return (token, token_info) for current session if valid."""
    token = session.get(SESSION_KEY)
    if not token:
        return None, None

    access_control = _get_access_control()
    if not access_control or not access_control.validate_token(token):
        session.pop(SESSION_KEY, None)
        return None, None

    token_info = access_control.get_token_info(token)
    if not token_info:
        session.pop(SESSION_KEY, None)
        return None, None

    return token, token_info


def client_login_required(view):
    """Decorator to enforce client authentication."""

    @wraps(view)
    def wrapped_view(*args, **kwargs):
        token, token_info = _load_token_from_session()
        if not token:
            flash("Please sign in with your API token to continue.", "warning")
            return redirect(url_for("client_portal.login", next=request.full_path))

        g.client_token = token
        g.client_token_info = token_info
        return view(*args, **kwargs)

    return wrapped_view


def _call_internal_api(action: str, param: Dict[str, Any]) -> Tuple[bool, Optional[Dict[str, Any]], Optional[str]]:
    """Call the existing /api endpoint using the client's token.

    Returns (success, data, error_message).
    """
    token = getattr(g, "client_token", None)
    if not token:
        token, _ = _load_token_from_session()
    if not token:
        return False, None, "Missing client session"

    payload = {"action": action, "param": param}
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {token}",
    }
    remote_addr = request.remote_addr or "127.0.0.1"

    with current_app.test_client() as client:
        response = client.post(
            "/api",
            json=payload,
            headers=headers,
            environ_overrides={"REMOTE_ADDR": remote_addr},
        )

    try:
        data = response.get_json()
    except Exception:  # pragma: no cover - defensive fallback
        data = None

    if response.status_code != 200 or not data or data.get("status") != "success":
        message = (data or {}).get("message", "Request failed")
        return False, data, message

    return True, data.get("responsedata"), None


def _allowed_domains(token_info: Dict[str, Any]) -> List[str]:
    """Derive the list of domains this token can manage."""
    access_control = _get_access_control()
    if not token_info or not access_control:
        return []

    if getattr(access_control, "use_database", False):
        domain = token_info.get("realm_value")
        return [domain] if domain else []

    domains: List[str] = []
    for permission in token_info.get("permissions", []):
        domain = permission.get("domain")
        if domain and domain not in domains:
            domains.append(domain)
    return domains


def _aggregate_operations(token_info: Dict[str, Any]) -> List[str]:
    """Return sorted list of allowed operations for the token."""
    access_control = _get_access_control()
    if not token_info or not access_control:
        return []

    if getattr(access_control, "use_database", False):
        return sorted(token_info.get("allowed_operations", []))

    ops = set()
    for permission in token_info.get("permissions", []):
        for op in permission.get("operations", []):
            ops.add(op)
    return sorted(ops)


def _aggregate_record_types(token_info: Dict[str, Any]) -> List[str]:
    """Return sorted list of record types available to the token."""
    access_control = _get_access_control()
    if not token_info or not access_control:
        return []

    if getattr(access_control, "use_database", False):
        return sorted(token_info.get("allowed_record_types", []))

    record_types = set()
    for permission in token_info.get("permissions", []):
        for record_type in permission.get("record_types", []):
            record_types.add(record_type)
    if "*" in record_types:
        return ["*"]
    return sorted(record_types)


def _load_records(domain: str) -> Tuple[bool, List[Dict[str, Any]], Optional[str]]:
    """Fetch DNS records for a domain."""
    success, data, error = _call_internal_api("infoDnsRecords", {"domainname": domain})
    if not success:
        return False, [], error
    records = data.get("dnsrecords", []) if isinstance(data, dict) else []
    return True, records, None


def _load_zone(domain: str) -> Tuple[bool, Dict[str, Any], Optional[str]]:
    """Fetch zone metadata for a domain."""
    success, data, error = _call_internal_api("infoDnsZone", {"domainname": domain})
    return success, data or {}, error


@client_portal_bp.route("/login", methods=["GET", "POST"])
def login():
    """Render and process the token login form."""
    if session.get(SESSION_KEY):
        return redirect(url_for("client_portal.dashboard"))

    access_control = _get_access_control()
    if not access_control:
        return render_template("client/login_modern.html", access_control_ready=False)

    if request.method == "POST":
        token = request.form.get("token", "").strip()
        if not token:
            flash("Token is required.", "danger")
        elif not access_control.validate_token(token):
            flash("Invalid token or token is inactive.", "danger")
        else:
            token_info = access_control.get_token_info(token)
            if not token_info:
                flash("Token lookup failed. Please try again.", "danger")
            else:
                session[SESSION_KEY] = token
                session["client_login_at"] = datetime.utcnow().isoformat()
                session.permanent = True
                flash("Signed in successfully.", "success")
                next_url = request.args.get("next") or url_for("client_portal.dashboard")
                return redirect(next_url)

    return render_template("client/login_modern.html", access_control_ready=True)


@client_portal_bp.route("/logout")
def logout():
    """Clear session and redirect to login."""
    session.pop(SESSION_KEY, None)
    session.pop("client_login_at", None)
    flash("You have been signed out.", "info")
    return redirect(url_for("client_portal.login"))


@client_portal_bp.route("/")
@client_login_required
def dashboard():
    """Client dashboard with allowed domains and recent stats."""
    token_info = g.client_token_info
    domains = _allowed_domains(token_info)
    domain_cards = []

    for domain in domains:
        card = {"domain": domain, "records": [], "record_count": 0, "zone": {}, "error": None}
        zone_ok, zone_data, zone_error = _load_zone(domain)
        if zone_ok:
            card["zone"] = zone_data
        else:
            card["error"] = zone_error or "Unable to load zone"

        records_ok, records, records_error = _load_records(domain)
        if records_ok:
            card["record_count"] = len(records)
            card["records"] = records[:5]  # preview
        else:
            card["error"] = records_error or card["error"]
        domain_cards.append(card)

    meta = {
        "operations": _aggregate_operations(token_info),
        "record_types": _aggregate_record_types(token_info),
        "description": token_info.get("description"),
        "client_id": token_info.get("client_id"),
    }

    return render_template(
        "client/dashboard_modern.html",
        domain_cards=domain_cards,
        meta=meta,
        login_ts=session.get("client_login_at"),
    )


@client_portal_bp.route("/domains/<string:domain>")
@client_login_required
def domain_detail(domain: str):
    """Detailed view of DNS records for a domain."""
    domain = domain.strip()
    token_info = g.client_token_info
    domains = _allowed_domains(token_info)
    if domain not in domains:
        abort(404)

    zone_ok, zone_data, zone_error = _load_zone(domain)
    records_ok, records, records_error = _load_records(domain)

    if not zone_ok:
        flash(zone_error or "Failed to load zone info", "danger")
    if not records_ok:
        flash(records_error or "Failed to load DNS records", "danger")

    return render_template(
        "client/domain_detail_modern.html",
        domain=domain,
        zone=zone_data,
        records=records,
        operations=_aggregate_operations(token_info),
        record_types=_aggregate_record_types(token_info),
    )


def _build_record_payload(form_data: Dict[str, Any], record_id: Optional[str] = None, delete: bool = False) -> Dict[str, Any]:
    """Convert form fields to Netcup DNS record payload."""
    payload = {
        "hostname": form_data.get("hostname", "").strip(),
        "type": form_data.get("type", "").strip().upper(),
        "destination": form_data.get("destination", "").strip(),
        "priority": form_data.get("priority", "0").strip() or "0",
        "ttl": form_data.get("ttl", "3600").strip() or "3600",
        "state": form_data.get("state", "yes").strip().lower() or "yes",
        "deleterecord": delete,
    }
    if record_id:
        payload["id"] = str(record_id)
    return payload


def _record_by_id(records: List[Dict[str, Any]], record_id: str) -> Optional[Dict[str, Any]]:
    """Find record entry by its ID."""
    for record in records:
        if str(record.get("id")) == str(record_id):
            return record
    return None


@client_portal_bp.route("/domains/<string:domain>/records/new", methods=["GET", "POST"])
@client_login_required
def new_record(domain: str):
    """Create a new DNS record within the allowed scope."""
    token_info = g.client_token_info
    domains = _allowed_domains(token_info)
    if domain not in domains:
        abort(404)

    if request.method == "POST":
        record_payload = _build_record_payload(request.form)
        success, _, error = _call_internal_api(
            "updateDnsRecords",
            {
                "domainname": domain,
                "dnsrecordset": {"dnsrecords": [record_payload]},
            },
        )
        if success:
            flash("DNS record created successfully.", "success")
            return redirect(url_for("client_portal.domain_detail", domain=domain))
        flash(error or "Failed to create record", "danger")

    return render_template(
        "client/record_form_modern.html",
        domain=domain,
        record=None,
        record_types=_aggregate_record_types(token_info) or ["A", "AAAA", "CNAME", "TXT", "MX"],
        mode="create",
    )


@client_portal_bp.route("/domains/<string:domain>/records/<record_id>/edit", methods=["GET", "POST"])
@client_login_required
def edit_record(domain: str, record_id: str):
    """Edit an existing DNS record."""
    token_info = g.client_token_info
    domains = _allowed_domains(token_info)
    if domain not in domains:
        abort(404)

    _, records, _ = _load_records(domain)
    record = _record_by_id(records, record_id)
    if not record:
        flash("Record not found or not visible to your token.", "danger")
        return redirect(url_for("client_portal.domain_detail", domain=domain))

    if request.method == "POST":
        updated_payload = _build_record_payload(request.form, record_id=record_id)
        success, _, error = _call_internal_api(
            "updateDnsRecords",
            {
                "domainname": domain,
                "dnsrecordset": {"dnsrecords": [updated_payload]},
            },
        )
        if success:
            flash("DNS record updated successfully.", "success")
            return redirect(url_for("client_portal.domain_detail", domain=domain))
        flash(error or "Failed to update record", "danger")

    return render_template(
        "client/record_form_modern.html",
        domain=domain,
        record=record,
        record_types=_aggregate_record_types(token_info) or ["A", "AAAA", "CNAME", "TXT", "MX"],
        mode="edit",
    )


@client_portal_bp.route("/domains/<string:domain>/records/<record_id>/delete", methods=["POST"])
@client_login_required
def delete_record(domain: str, record_id: str):
    """Delete a DNS record (sets deleterecord flag)."""
    token_info = g.client_token_info
    domains = _allowed_domains(token_info)
    if domain not in domains:
        abort(404)

    _, records, _ = _load_records(domain)
    record = _record_by_id(records, record_id)
    if not record:
        flash("Record not found or not visible to your token.", "danger")
        return redirect(url_for("client_portal.domain_detail", domain=domain))

    payload = _build_record_payload(record, record_id=record_id, delete=True)
    success, _, error = _call_internal_api(
        "updateDnsRecords",
        {
            "domainname": domain,
            "dnsrecordset": {"dnsrecords": [payload]},
        },
    )
    if success:
        flash("DNS record deleted successfully.", "success")
    else:
        flash(error or "Failed to delete record", "danger")
    return redirect(url_for("client_portal.domain_detail", domain=domain))


@client_portal_bp.route("/activity")
@client_login_required
def activity():
    """Display recent audit log entries for this client when available."""
    token_info = g.client_token_info
    client_id = token_info.get("client_id")
    logs = []

    if client_id:
        try:
            from database import AuditLog

            logs = (
                AuditLog.query.filter_by(client_id=client_id)
                .order_by(AuditLog.timestamp.desc())
                .limit(25)
                .all()
            )
        except Exception:  # pragma: no cover - database might not be available
            logs = []

    return render_template("client/activity_modern.html", logs=logs, client_id=client_id)


@client_portal_bp.app_context_processor
def inject_client_info() -> Dict[str, Any]:
    """Expose client info to Jinja templates within the portal."""
    return {"client_info": getattr(g, "client_token_info", None)}