"""
Email notification system for netcup-api-filter
Sends notifications for API access and security events
"""
import logging
import smtplib
import threading
import time
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)


class EmailNotifier:
    """Handles email notifications with async sending"""
    
    def __init__(self, smtp_server: str, smtp_port: int, smtp_username: str,
                 smtp_password: str, sender_email: str, use_ssl: bool = True):
        """
        Initialize email notifier
        
        Args:
            smtp_server: SMTP server hostname
            smtp_port: SMTP server port
            smtp_username: SMTP username
            smtp_password: SMTP password
            sender_email: Sender email address
            use_ssl: Whether to use SSL (default True)
        """
        self.smtp_server = smtp_server
        self.smtp_port = smtp_port
        self.smtp_username = smtp_username
        self.smtp_password = smtp_password
        self.sender_email = sender_email
        self.use_ssl = use_ssl
    
    def _send_email_sync(self, to_email: str, subject: str, body: str,
                         html_body: Optional[str] = None):
        """
        Send email synchronously (called by async thread)
        
        Args:
            to_email: Recipient email address
            subject: Email subject
            body: Plain text body
            html_body: Optional HTML body
        """
        # Create message
        msg = MIMEMultipart('alternative')
        msg['From'] = self.sender_email
        msg['To'] = to_email
        msg['Subject'] = subject

        # Attach plain text
        msg.attach(MIMEText(body, 'plain'))

        # Attach HTML if provided
        if html_body:
            msg.attach(MIMEText(html_body, 'html'))

        # Connect and send
        if self.use_ssl:
            with smtplib.SMTP_SSL(self.smtp_server, self.smtp_port, timeout=30) as server:
                if self.smtp_username and self.smtp_password:
                    server.login(self.smtp_username, self.smtp_password)
                server.send_message(msg)
        else:
            with smtplib.SMTP(self.smtp_server, self.smtp_port, timeout=30) as server:
                # Only use STARTTLS and login if credentials are provided
                if self.smtp_username and self.smtp_password:
                    server.starttls()
                    server.login(self.smtp_username, self.smtp_password)
                server.send_message(msg)

        logger.info(f"Email sent successfully to {to_email}")
    
    def send_email_async(self, to_email: str, subject: str, body: str,
                        html_body: Optional[str] = None, delay: int = 5):
        """
        Send email asynchronously with delay
        
        Args:
            to_email: Recipient email address
            subject: Email subject
            body: Plain text body
            html_body: Optional HTML body
            delay: Delay in seconds before sending (default 5)
        """
        def delayed_send():
            time.sleep(delay)
            try:
                self._send_email_sync(to_email, subject, body, html_body)
            except Exception as e:
                logger.error(f"Failed to send email to {to_email}: {e}")
        
        thread = threading.Thread(target=delayed_send, daemon=True)
        thread.start()
        logger.debug(f"Email queued for {to_email} with {delay}s delay")
    
    def send_client_notification(self, client_id: str, to_email: str,
                                 timestamp: datetime, operation: str,
                                 ip_address: str, success: bool,
                                 domain: str, record_details: Optional[Dict[str, Any]] = None,
                                 error_message: Optional[str] = None):
        """
        Send client notification for API access
        
        Args:
            client_id: Client identifier
            to_email: Client email address
            timestamp: Timestamp of request
            operation: Operation performed
            ip_address: Client IP address
            success: Whether operation succeeded
            domain: Domain accessed
            record_details: Optional DNS record details
            error_message: Optional error message
        """
        result = "SUCCESS" if success else "FAILURE"
        
        subject = f"[Netcup API Filter] API Access Notification - {result}"
        
        # Plain text body
        body = f"""
Netcup API Filter - Access Notification

Client ID: {client_id}
Timestamp: {timestamp.strftime('%Y-%m-%d %H:%M:%S UTC')}
Operation: {operation}
IP Address: {ip_address}
Domain: {domain}
Result: {result}

"""
        
        if record_details:
            body += "Record Details:\n"
            for key, value in record_details.items():
                body += f"  {key}: {value}\n"
            body += "\n"
        
        if error_message:
            body += f"Error: {error_message}\n\n"
        
        body += """
---
This is an automated notification from Netcup API Filter.
If you did not perform this action, please contact your administrator immediately.
"""
        
        # HTML body
        html_body = f"""
<html>
<body style="font-family: Arial, sans-serif; line-height: 1.6;">
    <h2 style="color: {'#27ae60' if success else '#e74c3c'};">Netcup API Filter - Access Notification</h2>
    
    <table style="border-collapse: collapse; width: 100%; max-width: 600px;">
        <tr>
            <td style="padding: 8px; border: 1px solid #ddd; background-color: #f9f9f9; font-weight: bold;">Client ID</td>
            <td style="padding: 8px; border: 1px solid #ddd;">{client_id}</td>
        </tr>
        <tr>
            <td style="padding: 8px; border: 1px solid #ddd; background-color: #f9f9f9; font-weight: bold;">Timestamp</td>
            <td style="padding: 8px; border: 1px solid #ddd;">{timestamp.strftime('%Y-%m-%d %H:%M:%S UTC')}</td>
        </tr>
        <tr>
            <td style="padding: 8px; border: 1px solid #ddd; background-color: #f9f9f9; font-weight: bold;">Operation</td>
            <td style="padding: 8px; border: 1px solid #ddd;">{operation}</td>
        </tr>
        <tr>
            <td style="padding: 8px; border: 1px solid #ddd; background-color: #f9f9f9; font-weight: bold;">IP Address</td>
            <td style="padding: 8px; border: 1px solid #ddd;">{ip_address}</td>
        </tr>
        <tr>
            <td style="padding: 8px; border: 1px solid #ddd; background-color: #f9f9f9; font-weight: bold;">Domain</td>
            <td style="padding: 8px; border: 1px solid #ddd;">{domain}</td>
        </tr>
        <tr>
            <td style="padding: 8px; border: 1px solid #ddd; background-color: #f9f9f9; font-weight: bold;">Result</td>
            <td style="padding: 8px; border: 1px solid #ddd; color: {'#27ae60' if success else '#e74c3c'}; font-weight: bold;">{result}</td>
        </tr>
    </table>
"""
        
        if record_details:
            html_body += """
    <h3>Record Details</h3>
    <table style="border-collapse: collapse; width: 100%; max-width: 600px;">
"""
            for key, value in record_details.items():
                html_body += f"""
        <tr>
            <td style="padding: 8px; border: 1px solid #ddd; background-color: #f9f9f9; font-weight: bold;">{key}</td>
            <td style="padding: 8px; border: 1px solid #ddd;">{value}</td>
        </tr>
"""
            html_body += "    </table>\n"
        
        if error_message:
            html_body += f"""
    <div style="background-color: #ffe6e6; border-left: 4px solid #e74c3c; padding: 10px; margin-top: 10px;">
        <strong>Error:</strong> {error_message}
    </div>
"""
        
        html_body += """
    <hr style="margin-top: 20px; border: none; border-top: 1px solid #ddd;">
    <p style="color: #888; font-size: 12px;">
        This is an automated notification from Netcup API Filter.<br>
        If you did not perform this action, please contact your administrator immediately.
    </p>
</body>
</html>
"""
        
        self.send_email_async(to_email, subject, body, html_body)
    
    def send_admin_notification(self, admin_email: str, event_type: str,
                               details: str, ip_address: Optional[str] = None,
                               timestamp: Optional[datetime] = None):
        """
        Send admin notification for security events
        
        Args:
            admin_email: Admin email address
            event_type: Type of security event
            details: Event details
            ip_address: Optional IP address
            timestamp: Optional timestamp (defaults to now)
        """
        if timestamp is None:
            timestamp = datetime.utcnow()
        
        subject = f"[Netcup API Filter] Security Alert - {event_type}"
        
        # Plain text body
        body = f"""
Netcup API Filter - Security Alert

Event Type: {event_type}
Timestamp: {timestamp.strftime('%Y-%m-%d %H:%M:%S UTC')}
"""
        
        if ip_address:
            body += f"IP Address: {ip_address}\n"
        
        body += f"""
Details: {details}

---
This is an automated security notification from Netcup API Filter.
Please review the event and take appropriate action if necessary.
"""
        
        # HTML body
        html_body = f"""
<html>
<body style="font-family: Arial, sans-serif; line-height: 1.6;">
    <h2 style="color: #e74c3c;">Netcup API Filter - Security Alert</h2>
    
    <table style="border-collapse: collapse; width: 100%; max-width: 600px;">
        <tr>
            <td style="padding: 8px; border: 1px solid #ddd; background-color: #f9f9f9; font-weight: bold;">Event Type</td>
            <td style="padding: 8px; border: 1px solid #ddd;">{event_type}</td>
        </tr>
        <tr>
            <td style="padding: 8px; border: 1px solid #ddd; background-color: #f9f9f9; font-weight: bold;">Timestamp</td>
            <td style="padding: 8px; border: 1px solid #ddd;">{timestamp.strftime('%Y-%m-%d %H:%M:%S UTC')}</td>
        </tr>
"""
        
        if ip_address:
            html_body += f"""
        <tr>
            <td style="padding: 8px; border: 1px solid #ddd; background-color: #f9f9f9; font-weight: bold;">IP Address</td>
            <td style="padding: 8px; border: 1px solid #ddd;">{ip_address}</td>
        </tr>
"""
        
        html_body += f"""
    </table>
    
    <div style="background-color: #fff3cd; border-left: 4px solid #ffc107; padding: 10px; margin-top: 10px;">
        <strong>Details:</strong> {details}
    </div>
    
    <hr style="margin-top: 20px; border: none; border-top: 1px solid #ddd;">
    <p style="color: #888; font-size: 12px;">
        This is an automated security notification from Netcup API Filter.<br>
        Please review the event and take appropriate action if necessary.
    </p>
</body>
</html>
"""
        
        self.send_email_async(admin_email, subject, body, html_body)
    
    def send_test_email(self, to_email: str) -> bool:
        """
        Send a test email (synchronously for immediate feedback)
        
        Args:
            to_email: Recipient email address
            
        Returns:
            True if email sent successfully, False otherwise
        """
        subject = "[Netcup API Filter] Test Email"
        body = """
This is a test email from Netcup API Filter.

If you received this email, your email configuration is working correctly.

Timestamp: {}
""".format(datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC'))
        
        html_body = f"""
<html>
<body style="font-family: Arial, sans-serif; line-height: 1.6;">
    <h2 style="color: #27ae60;">Test Email - Netcup API Filter</h2>
    <p>This is a test email from Netcup API Filter.</p>
    <p>If you received this email, your email configuration is working correctly.</p>
    <p><strong>Timestamp:</strong> {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')}</p>
</body>
</html>
"""
        
        try:
            self._send_email_sync(to_email, subject, body, html_body)
            return True
        except Exception as e:
            logger.error(f"Test email failed: {e}")
            return False


def get_email_notifier_from_config(config: Dict[str, Any]) -> Optional[EmailNotifier]:
    """
    Create EmailNotifier from configuration dictionary
    
    Args:
        config: Email configuration dictionary
        
    Returns:
        EmailNotifier instance or None if config incomplete
    """
    if not config:
        return None
    
    # Use TOML field names (smtp_host and from_email)
    # Username/password are optional (some relays like Mailpit can run without auth).
    required_fields = ['smtp_host', 'smtp_port', 'from_email']
    if not all(config.get(field) for field in required_fields):
        logger.warning("Email configuration incomplete")
        return None
    
    try:
        return EmailNotifier(
            smtp_server=config['smtp_host'],  # TOML field name
            smtp_port=int(config['smtp_port']),
            smtp_username=config.get('smtp_username', ''),
            smtp_password=config.get('smtp_password', ''),
            sender_email=config['from_email'],  # TOML field name
            use_ssl=config.get('use_ssl', True)
        )
    except Exception as e:
        logger.error(f"Failed to create EmailNotifier: {e}")
        return None
