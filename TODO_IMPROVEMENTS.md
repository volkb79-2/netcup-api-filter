# TODO: Project Improvements

This document tracks recommended improvements from the security and code quality audit (2025-11-25).

## Completed ✅

- [x] Create missing requirements.txt at project root
- [x] Fix hardcoded session configuration in database.py (made config-driven)
- [x] Add GitHub Actions CI/CD workflow (tests.yml)
- [x] Add linting configuration (.flake8, pyproject.toml)
- [x] Add security audit job (pip-audit in CI)

## High Priority ⚠️

- [ ] **Security: Run pip-audit for CVE check**
  ```bash
  pip install pip-audit
  pip-audit -r requirements.txt
  ```
  - Check for known vulnerabilities in dependencies
  - Update vulnerable packages
  - Document findings in SECURITY.md

## Medium Priority 💡

- [x] **CI/CD: Add GitHub Actions workflow** ✅ COMPLETED
  - Created `.github/workflows/tests.yml`
  - Runs pytest on PRs and pushes
  - Includes flake8, black, mypy checks
  - Multi-version testing (Python 3.9, 3.10, 3.11)
  - Security audit with pip-audit
  - Non-blocking checks for gradual improvement

- [ ] **Testing: Add unit tests for utilities**
  - Create `test_utils.py`
  - Test `generate_token()`
  - Test `hash_password()` and `verify_password()`
  - Test `validate_domain()` and `validate_hostname()`
  - Test `validate_email()` and `validate_ip_range()`
  - Target: >80% coverage for utils.py

- [ ] **Monitoring: Document production recommendations**
  - Add section to README or DEPLOYMENT.md
  - Log aggregation (ELK, Splunk, CloudWatch)
  - Metrics collection (Prometheus, Datadog)
  - Alert rules (failed logins, rate limits, errors)
  - Performance monitoring (slow queries, memory usage)

## Low Priority 📝

- [ ] **Code Quality: Improve type hints coverage**
  - Current: ~40% (80/200 functions)
  - Target: >80%
  - Priority order:
    1. `filter_proxy.py` - public API functions
    2. `access_control.py` - permission validation
    3. `utils.py` - utility functions
    4. `database.py` - query functions
  - Use `mypy` for validation:
    ```bash
    pip install mypy
    mypy --strict filter_proxy.py
    ```

- [ ] **Documentation: Add OpenAPI/Swagger spec**
  - Create `openapi.yaml` for API endpoint
  - Document request/response schemas
  - Document error codes (400, 401, 403, 429, 500)
  - Add to README with link to Swagger UI

- [ ] **Compatibility: Test Python 3.12**
  - Update CI to test Python 3.12
  - Update setup.py classifiers if compatible
  - Consider dropping Python 3.7 (EOL June 2023)

- [ ] **Performance: Add query profiling**
  - Enable SQLAlchemy query logging in dev
  - Identify slow queries
  - Add composite indexes if needed
  - Monitor in production

- [ ] **Code Quality: Add docstrings**
  - Priority functions without docstrings:
    - Functions in `client_portal.py`
    - Complex permission logic in `access_control.py`
  - Use Google or NumPy docstring format
  - Example:
    ```python
    def example_function(param: str) -> bool:
        """
        One-line summary.
        
        Longer description if needed.
        
        Args:
            param: Description of parameter
            
        Returns:
            Description of return value
            
        Raises:
            ValueError: When parameter is invalid
        """
    ```

## Dependency Management 📦

- [ ] **Setup Dependabot**
  - Create `.github/dependabot.yml`
  - Enable automated PR for updates
  - Configure update schedule (weekly)

- [ ] **Review Flask 4.x compatibility**
  - Current constraint: `flask>=2.3.0,<4.0.0`
  - Test with Flask 4.x when released
  - Update constraint if compatible

- [ ] **Check deprecated dependencies**
  - Review Flask-Admin compatibility
  - Check for deprecated Flask extensions
  - Update to maintained alternatives if needed

## Future Enhancements 🚀

- [ ] **Feature: API versioning**
  - Add `/api/v1/` prefix
  - Maintain backward compatibility
  - Document version policy

- [ ] **Feature: Webhook notifications**
  - Alternative to email notifications
  - POST to configurable URL on events
  - Include event type and metadata

- [ ] **Feature: Multi-admin support**
  - Currently single admin user
  - Add admin user management
  - Role-based access control

- [ ] **Feature: Rate limit per-client**
  - Currently per-IP only
  - Add per-token rate limits
  - Configurable in admin UI

- [ ] **Feature: Audit log export**
  - Export as CSV/JSON
  - Filter by date range
  - Filter by client/operation

## Notes

- All high and medium priority items should be completed before version 2.0
- Low priority items can be addressed incrementally
- Assign items to milestones/releases as appropriate
- Update this document when items are completed

---

**Last Updated:** 2025-11-25  
**Next Review:** After completing high priority items
