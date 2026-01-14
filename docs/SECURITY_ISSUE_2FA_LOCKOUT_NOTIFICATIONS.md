# Security Issue: 2FA Lockout Email Notifications

## Summary

Implement email notifications to users and administrators when a 2FA lockout occurs due to repeated failed authentication attempts.

## Background

As part of the 2FA security improvements implemented in this release, we now track failed 2FA attempts and lock accounts temporarily after exceeding the configured threshold (default: 5 attempts within 30 minutes). However, users are currently not notified of these lockouts, which could lead to confusion or security concerns.

## Requirements

### User Notification

When a user account is locked due to 2FA failures:

1. **Send email to account owner** with:
   - Notification that their account was locked
   - Reason: Too many failed 2FA attempts
   - Lockout duration (configured via `TFA_LOCKOUT_MINUTES`)
   - Time of the incident
   - Source IP address of failed attempts (if available)
   - Instructions to wait or contact admin if suspicious activity
   - Link to password reset if they suspect compromise

2. **Email template**:
   - Subject: "Account Security: 2FA Lockout - [Account Name]"
   - Clear security warning tone
   - Action items: Wait for lockout expiry, review account security
   - Contact information for support

### Admin Notification

When a user account is locked:

1. **Send email to administrators** (or security notification email) with:
   - Which account was locked
   - Timestamp of lockout
   - Number of failed attempts
   - Source IP addresses involved
   - User's email for context
   - Link to admin panel to review activity logs

2. **Email template**:
   - Subject: "Admin Alert: User Account Locked - [Username]"
   - Summary of failed attempts
   - Link to admin activity log for the user
   - Optional: Suggest reviewing for patterns (brute force attacks)

### Recovery Code Lockout

Similar notifications for recovery code lockout:

1. **Separate notification** (different reason/threat model)
2. **Higher priority** - recovery codes are last resort, failures indicate:
   - Lost recovery codes
   - Potential compromise attempt
3. **Additional context**:
   - Number of remaining recovery codes (if any)
   - Suggestion to regenerate codes after successful login

## Implementation Details

### Configuration (.env.defaults)

```bash
# Email notifications for security events
NOTIFY_USER_ON_2FA_LOCKOUT=true
NOTIFY_ADMIN_ON_2FA_LOCKOUT=true
NOTIFY_USER_ON_RECOVERY_LOCKOUT=true
NOTIFY_ADMIN_ON_RECOVERY_LOCKOUT=true

# Admin notification email (comma-separated for multiple recipients)
ADMIN_SECURITY_EMAIL=admin@example.com
```

### Code Changes

1. **Update `account_auth.py`**:
   - Call notification service when `increment_2fa_failures()` triggers lockout
   - Call notification service when `increment_recovery_code_failures()` triggers lockout

2. **Update `notification_service.py`**:
   - Add `notify_2fa_lockout_user(account, source_ip, lockout_minutes)`
   - Add `notify_2fa_lockout_admin(account, source_ip, failed_count)`
   - Add `notify_recovery_lockout_user(account, source_ip, lockout_minutes)`
   - Add `notify_recovery_lockout_admin(account, source_ip, failed_count)`

3. **Email Templates** (HTML + plain text):
   - `templates/email/2fa_lockout_user.html`
   - `templates/email/2fa_lockout_admin.html`
   - `templates/email/recovery_lockout_user.html`
   - `templates/email/recovery_lockout_admin.html`

### Security Considerations

1. **Rate limiting for notifications**:
   - Prevent notification spam if attacker repeatedly triggers lockouts
   - Batch notifications: Max 1 per lockout period per account

2. **Information disclosure**:
   - User notifications should not reveal internal details
   - Admin notifications can include detailed forensics

3. **Email deliverability**:
   - Critical security notifications should bypass notification queue
   - Log delivery failures for audit

4. **Privacy**:
   - IP addresses in notifications may be sensitive (GDPR considerations)
   - Option to anonymize or aggregate IP data in user-facing notifications

## Testing

1. **Functional tests**:
   - Trigger 2FA lockout, verify user email sent
   - Trigger 2FA lockout, verify admin email sent
   - Trigger recovery code lockout, verify notifications
   - Verify notification rate limiting

2. **UI tests**:
   - Simulate failed attempts in Playwright tests
   - Check Mailpit for expected notifications
   - Verify email content matches templates

3. **Integration tests**:
   - End-to-end flow: lockout → notification → unlock → re-login

## Related Features

- **Activity Log**: All lockout events are already logged to `ActivityLog` table
- **Admin Dashboard**: Consider adding "Recent Lockouts" widget
- **User Dashboard**: Show lockout history to user for transparency

## Priority

**Medium** - Enhances security awareness but not blocking for core functionality.

## Implementation Estimate

- Email templates: 2 hours
- Notification service updates: 2 hours
- Integration with lockout logic: 1 hour
- Testing: 2 hours
- **Total**: ~7 hours

## Acceptance Criteria

- [ ] User receives email notification on 2FA lockout
- [ ] Admin receives email notification on 2FA lockout
- [ ] User receives email notification on recovery code lockout
- [ ] Admin receives email notification on recovery code lockout
- [ ] Notifications include relevant context (IP, timestamp, lockout duration)
- [ ] Notifications are rate-limited to prevent spam
- [ ] Email deliverability is prioritized for security events
- [ ] Tests verify notification delivery in all scenarios
- [ ] Configuration flags allow disabling notifications per type

## Future Enhancements

1. **Webhook support**: POST lockout events to admin-configured webhook
2. **SMS/Telegram notifications**: For high-security accounts
3. **Geolocation in notifications**: "Login attempt from [Country/City]"
4. **Suspicious pattern detection**: Flag unusual activity (new device/location)
5. **Self-service unlock**: Allow user to unlock via password reset flow
