"""
Audit logging system for netcup-api-filter
Logs to both file and database
"""
import logging
import os
from datetime import datetime
from typing import Optional, Dict, Any
from logging.handlers import RotatingFileHandler

logger = logging.getLogger(__name__)


class AuditLogger:
    """Combined file and database audit logger"""
    
    def __init__(self, log_file_path: Optional[str] = None, enable_db: bool = True):
        """
        Initialize audit logger
        
        Args:
            log_file_path: Path to log file (None to disable file logging)
            enable_db: Whether to enable database logging (default True)
        """
        self.log_file_path = log_file_path
        self.enable_db = enable_db
        self.file_logger = None
        
        # Setup file logging if path provided
        if log_file_path:
            self._setup_file_logger()
    
    def _setup_file_logger(self):
        """Setup file-based logging"""
        try:
            # Create directory if it doesn't exist
            log_dir = os.path.dirname(self.log_file_path)
            if log_dir and not os.path.exists(log_dir):
                os.makedirs(log_dir, exist_ok=True)
            
            # Create file logger
            self.file_logger = logging.getLogger('audit_file_logger')
            self.file_logger.setLevel(logging.INFO)
            self.file_logger.propagate = False
            
            # Remove existing handlers
            self.file_logger.handlers = []
            
            # Create file handler (no rotation - indefinite retention)
            file_handler = logging.FileHandler(self.log_file_path)
            file_handler.setLevel(logging.INFO)
            
            # Create formatter
            formatter = logging.Formatter(
                '%(asctime)s - %(message)s',
                datefmt='%Y-%m-%d %H:%M:%S'
            )
            file_handler.setFormatter(formatter)
            
            self.file_logger.addHandler(file_handler)
            
            logger.info(f"File audit logging enabled: {self.log_file_path}")
            
        except Exception as e:
            logger.error(f"Failed to setup file audit logging: {e}")
            self.file_logger = None
    
    def log_access(self, client_id: Optional[str], ip_address: str, operation: str,
                   domain: str, record_details: Optional[Dict[str, Any]] = None,
                   success: bool = True, error_message: Optional[str] = None,
                   request_data: Optional[Dict[str, Any]] = None,
                   response_data: Optional[Dict[str, Any]] = None):
        """
        Log an API access attempt
        
        Args:
            client_id: Client identifier (None if authentication failed)
            ip_address: Client IP address
            operation: Operation performed
            domain: Domain accessed
            record_details: Optional DNS record details
            success: Whether operation succeeded
            error_message: Optional error message
            request_data: Optional full request data
            response_data: Optional full response data
        """
        timestamp = datetime.utcnow()
        
        # Log to file
        if self.file_logger:
            result = "SUCCESS" if success else "FAILURE"
            log_msg = f"client_id={client_id or 'UNKNOWN'} ip={ip_address} operation={operation} domain={domain} result={result}"
            
            if error_message:
                log_msg += f" error='{error_message}'"
            
            if record_details:
                # Add key record details
                if 'hostname' in record_details:
                    log_msg += f" hostname={record_details['hostname']}"
                if 'type' in record_details:
                    log_msg += f" type={record_details['type']}"
            
            self.file_logger.info(log_msg)
        
        # Log to database
        if self.enable_db:
            try:
                from .database import create_audit_log, db
                
                # Create audit log entry
                create_audit_log(
                    client_id=client_id,
                    ip_address=ip_address,
                    operation=operation,
                    domain=domain,
                    record_details=record_details,
                    success=success,
                    error_message=error_message,
                    request_data=request_data,
                    response_data=response_data
                )
                
            except Exception as e:
                logger.error(f"Failed to log to database: {e}")
    
    def log_security_event(self, event_type: str, details: str,
                          ip_address: Optional[str] = None,
                          client_id: Optional[str] = None):
        """
        Log a security event
        
        Args:
            event_type: Type of security event
            details: Event details
            ip_address: Optional IP address
            client_id: Optional client ID
        """
        timestamp = datetime.utcnow()
        
        # Log to file
        if self.file_logger:
            log_msg = f"SECURITY_EVENT type={event_type} details='{details}'"
            
            if ip_address:
                log_msg += f" ip={ip_address}"
            
            if client_id:
                log_msg += f" client_id={client_id}"
            
            self.file_logger.warning(log_msg)
        
        # Log to database as special audit entry
        if self.enable_db:
            try:
                from .database import create_audit_log
                
                create_audit_log(
                    client_id=client_id,
                    ip_address=ip_address or 'N/A',
                    operation='SECURITY_EVENT',
                    domain=event_type,
                    record_details={'event_type': event_type, 'details': details},
                    success=False,
                    error_message=details,
                    request_data=None,
                    response_data=None
                )
                
            except Exception as e:
                logger.error(f"Failed to log security event to database: {e}")
    
    def log_authentication_failure(self, ip_address: str, reason: str):
        """
        Log an authentication failure
        
        Args:
            ip_address: Client IP address
            reason: Reason for failure
        """
        self.log_security_event(
            event_type='AUTHENTICATION_FAILURE',
            details=reason,
            ip_address=ip_address
        )
    
    def log_permission_denied(self, client_id: str, ip_address: str,
                             operation: str, domain: str, reason: str):
        """
        Log a permission denial
        
        Args:
            client_id: Client identifier
            ip_address: Client IP address
            operation: Operation attempted
            domain: Domain accessed
            reason: Reason for denial
        """
        self.log_security_event(
            event_type='PERMISSION_DENIED',
            details=f"Operation: {operation}, Domain: {domain}, Reason: {reason}",
            ip_address=ip_address,
            client_id=client_id
        )
    
    def log_origin_violation(self, client_id: str, ip_address: str,
                            origin_host: Optional[str] = None):
        """
        Log an origin restriction violation
        
        Args:
            client_id: Client identifier
            ip_address: Client IP address
            origin_host: Optional origin host
        """
        details = f"IP: {ip_address}"
        if origin_host:
            details += f", Host: {origin_host}"
        
        self.log_security_event(
            event_type='ORIGIN_VIOLATION',
            details=details,
            ip_address=ip_address,
            client_id=client_id
        )


def get_audit_logger(log_file_path: Optional[str] = None,
                     enable_db: bool = True) -> AuditLogger:
    """
    Create and return an AuditLogger instance
    
    Args:
        log_file_path: Path to log file (None to disable file logging)
        enable_db: Whether to enable database logging
        
    Returns:
        AuditLogger instance
    """
    # Default log file path if not specified
    if log_file_path is None and enable_db:
        # Try to use a log file in current directory
        try:
            log_file_path = os.path.join(os.getcwd(), 'netcup_filter_audit.log')
        except Exception:
            log_file_path = None
    
    return AuditLogger(log_file_path=log_file_path, enable_db=enable_db)
