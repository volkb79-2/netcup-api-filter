"""In-memory stand-in for the Netcup upstream, shared by the hermetic HTTP tests.

No sockets, no containers: it implements the three calls the app makes
(``info_dns_records``, ``update_dns_records``) with create/update/delete
semantics close to the real API, so tests can assert BACKEND TRUTH (what the
zone holds after the HTTP call) instead of only status codes.
"""
from __future__ import annotations


class FakeNetcupBackend:
    """Stateful fake of ``NetcupClient`` / ``MockNetcupClient``."""

    def __init__(self, zones=None):
        self._zones = {d: [dict(r) for r in recs] for d, recs in (zones or {}).items()}
        self._next_id = 5000
        self.update_calls = []   # [(domain, [record, ...]), ...]
        self.fail_info = None    # set to a message to make info_dns_records return an error envelope
        self.fail_update = None  # set to a message to make update_dns_records return an error envelope

    def records_for(self, domain):
        return self._zones.get(domain, [])

    def find(self, domain, hostname, rtype):
        for rec in self.records_for(domain):
            if rec.get("hostname") == hostname and rec.get("type") == rtype:
                return rec
        return None

    def info_dns_records(self, domain):
        if self.fail_info:
            return {"status": "error", "message": self.fail_info}
        return [dict(r) for r in self._zones.get(domain, [])]

    def update_dns_records(self, domain, dns_records):
        self.update_calls.append((domain, [dict(r) for r in dns_records]))
        if self.fail_update:
            return {"status": "error", "message": self.fail_update}
        zone = self._zones.setdefault(domain, [])
        for incoming in dns_records:
            rid = incoming.get("id")
            if incoming.get("deleterecord"):
                zone[:] = [r for r in zone if str(r.get("id")) != str(rid)]
                continue
            for i, existing in enumerate(zone):
                if rid is not None and str(existing.get("id")) == str(rid):
                    zone[i] = {**existing, **incoming}
                    break
            else:
                rec = dict(incoming)
                if rec.get("id") is None:
                    rec["id"] = str(self._next_id)
                    self._next_id += 1
                zone.append(rec)
        return {"status": "success"}


def install_fake_netcup(monkeypatch, backend, *modules):
    """Route ``get_netcup_client`` in each given api module to *backend*."""
    for module in modules:
        monkeypatch.setattr(module, "get_netcup_client", lambda: backend)
    return backend
