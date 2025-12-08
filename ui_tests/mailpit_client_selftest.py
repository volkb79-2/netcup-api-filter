"""
self-test program for a running mailpit 
"""


from mailpit_client import MailpitClient

client = MailpitClient()
try:
    info = client.info()
    print(f'✅ Mailpit connected: {info}')
    
    # Clear and check
    client.clear()
    messages = client.list_messages()
    print(f'✅ Mailpit cleared: {messages.total} messages')
    
    # Send test email via SMTP
    import smtplib
    from email.mime.text import MIMEText
    
    msg = MIMEText('Test body content with a reset link: https://example.com/reset/abc123')
    msg['Subject'] = 'Test Password Reset'
    msg['From'] = 'naf@example.com'
    msg['To'] = 'user@example.com'
    
    smtp = smtplib.SMTP('mailpit', 1025)
    smtp.send_message(msg)
    smtp.quit()
    print('✅ Test email sent')
    
    # Wait for message
    received = client.wait_for_message(timeout=5.0)
    if received:
        print(f'✅ Email received: Subject={received.subject}')
        print(f'   From: {received.from_address.address}')
        print(f'   To: {[a.address for a in received.to]}')
        print(f'   Body: {received.text[:100]}...')
    else:
        print('❌ Email not received')
    
    client.close()
except Exception as e:
    print(f'❌ Error: {e}')

    