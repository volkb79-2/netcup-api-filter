from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, IntegerField, BooleanField, SubmitField
from wtforms.validators import DataRequired, Email, Optional, NumberRange, URL

class NetcupConfigForm(FlaskForm):
    customer_id = StringField('Customer ID', validators=[DataRequired()], description='Your Netcup customer number')
    api_key = StringField('API Key', validators=[DataRequired()], description='Your Netcup API key')
    api_password = PasswordField('API Password', validators=[DataRequired()], description='Your Netcup API password')
    api_url = StringField('API URL', validators=[DataRequired(), URL()], default='https://ccp.netcup.net/run/webservice/servers/endpoint.php?JSON', description='Netcup API endpoint URL')
    timeout = IntegerField('Timeout (seconds)', validators=[DataRequired(), NumberRange(min=5, max=120)], default=30, description='API request timeout')

class EmailConfigForm(FlaskForm):
    smtp_server = StringField('SMTP Server', validators=[DataRequired()])
    smtp_port = IntegerField('SMTP Port', validators=[DataRequired()], default=465)
    smtp_username = StringField('SMTP Username', validators=[Optional()])
    smtp_password = PasswordField('SMTP Password', validators=[Optional()])
    sender_email = StringField('Sender Email', validators=[DataRequired(), Email()], description='Email address to send from')
    use_ssl = BooleanField('Use SSL/TLS', default=True)
    admin_email = StringField('Admin Notification Email', validators=[Optional(), Email()], description='Email address to receive admin notifications')
    
    # Test email field (not saved, used for testing)
    test_email = StringField('Test Email Recipient', validators=[Optional(), Email()], description='Enter an email to send a test message')
