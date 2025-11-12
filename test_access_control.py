"""
Unit tests for access control module
"""
import unittest
from access_control import AccessControl


class TestAccessControl(unittest.TestCase):
    """Test cases for AccessControl class"""
    
    def setUp(self):
        """Set up test fixtures"""
        self.tokens_config = [
            {
                "token": "test-token-1",
                "description": "Test token 1",
                "permissions": [
                    {
                        "domain": "example.com",
                        "record_name": "host1",
                        "record_types": ["A"],
                        "operations": ["read", "update"]
                    }
                ]
            },
            {
                "token": "test-token-2",
                "description": "Test token 2 - wildcard",
                "permissions": [
                    {
                        "domain": "example.com",
                        "record_name": "web*",
                        "record_types": ["A", "AAAA"],
                        "operations": ["read", "update", "create", "delete"]
                    }
                ]
            },
            {
                "token": "test-token-3",
                "description": "Test token 3 - readonly all",
                "permissions": [
                    {
                        "domain": "example.com",
                        "record_name": "*",
                        "record_types": ["*"],
                        "operations": ["read"]
                    }
                ]
            }
        ]
        self.ac = AccessControl(self.tokens_config)
    
    def test_validate_token(self):
        """Test token validation"""
        self.assertTrue(self.ac.validate_token("test-token-1"))
        self.assertTrue(self.ac.validate_token("test-token-2"))
        self.assertTrue(self.ac.validate_token("test-token-3"))
        self.assertFalse(self.ac.validate_token("invalid-token"))
    
    def test_check_permission_exact_match(self):
        """Test permission check with exact match"""
        # Token 1 should have read permission for host1
        self.assertTrue(
            self.ac.check_permission("test-token-1", "read", "example.com", "host1", "A")
        )
        # Token 1 should have update permission for host1
        self.assertTrue(
            self.ac.check_permission("test-token-1", "update", "example.com", "host1", "A")
        )
        # Token 1 should NOT have delete permission for host1
        self.assertFalse(
            self.ac.check_permission("test-token-1", "delete", "example.com", "host1", "A")
        )
        # Token 1 should NOT have permission for host2
        self.assertFalse(
            self.ac.check_permission("test-token-1", "read", "example.com", "host2", "A")
        )
        # Token 1 should NOT have permission for AAAA record
        self.assertFalse(
            self.ac.check_permission("test-token-1", "read", "example.com", "host1", "AAAA")
        )
    
    def test_check_permission_wildcard_name(self):
        """Test permission check with wildcard record name"""
        # Token 2 should have permission for web1, web2, etc.
        self.assertTrue(
            self.ac.check_permission("test-token-2", "read", "example.com", "web1", "A")
        )
        self.assertTrue(
            self.ac.check_permission("test-token-2", "update", "example.com", "web2", "A")
        )
        self.assertTrue(
            self.ac.check_permission("test-token-2", "create", "example.com", "webserver", "AAAA")
        )
        # Token 2 should NOT have permission for db1
        self.assertFalse(
            self.ac.check_permission("test-token-2", "read", "example.com", "db1", "A")
        )
    
    def test_check_permission_wildcard_all(self):
        """Test permission check with full wildcards"""
        # Token 3 should have read permission for any record
        self.assertTrue(
            self.ac.check_permission("test-token-3", "read", "example.com", "anything", "A")
        )
        self.assertTrue(
            self.ac.check_permission("test-token-3", "read", "example.com", "host1", "CNAME")
        )
        # Token 3 should NOT have update permission
        self.assertFalse(
            self.ac.check_permission("test-token-3", "update", "example.com", "host1", "A")
        )
    
    def test_check_permission_domain_only(self):
        """Test permission check without record details"""
        # For zone-level operations
        self.assertTrue(
            self.ac.check_permission("test-token-1", "read", "example.com")
        )
        self.assertTrue(
            self.ac.check_permission("test-token-3", "read", "example.com")
        )
        # Wrong domain
        self.assertFalse(
            self.ac.check_permission("test-token-1", "read", "other.com")
        )
    
    def test_filter_dns_records(self):
        """Test DNS record filtering"""
        records = [
            {"hostname": "host1", "type": "A", "destination": "1.2.3.4"},
            {"hostname": "host2", "type": "A", "destination": "5.6.7.8"},
            {"hostname": "web1", "type": "A", "destination": "9.10.11.12"},
            {"hostname": "web2", "type": "AAAA", "destination": "::1"},
            {"hostname": "mail", "type": "MX", "destination": "mail.example.com"},
        ]
        
        # Token 1 should only see host1 A record
        filtered = self.ac.filter_dns_records("test-token-1", "example.com", records)
        self.assertEqual(len(filtered), 1)
        self.assertEqual(filtered[0]["hostname"], "host1")
        
        # Token 2 should see web1 and web2
        filtered = self.ac.filter_dns_records("test-token-2", "example.com", records)
        self.assertEqual(len(filtered), 2)
        hostnames = [r["hostname"] for r in filtered]
        self.assertIn("web1", hostnames)
        self.assertIn("web2", hostnames)
        
        # Token 3 should see all records (readonly access)
        filtered = self.ac.filter_dns_records("test-token-3", "example.com", records)
        self.assertEqual(len(filtered), 5)
    
    def test_validate_dns_records_update(self):
        """Test DNS record update validation"""
        # Token 1 updating host1 A record (should succeed)
        records = [
            {"hostname": "host1", "type": "A", "destination": "1.2.3.4", "id": "123"}
        ]
        is_valid, error = self.ac.validate_dns_records_update("test-token-1", "example.com", records)
        self.assertTrue(is_valid)
        self.assertIsNone(error)
        
        # Token 1 updating host2 A record (should fail)
        records = [
            {"hostname": "host2", "type": "A", "destination": "1.2.3.4", "id": "456"}
        ]
        is_valid, error = self.ac.validate_dns_records_update("test-token-1", "example.com", records)
        self.assertFalse(is_valid)
        self.assertIsNotNone(error)
        
        # Token 1 creating new record (should fail - no create permission)
        records = [
            {"hostname": "host1", "type": "A", "destination": "1.2.3.4"}
        ]
        is_valid, error = self.ac.validate_dns_records_update("test-token-1", "example.com", records)
        self.assertFalse(is_valid)
        self.assertIsNotNone(error)
        
        # Token 2 creating web3 record (should succeed)
        records = [
            {"hostname": "web3", "type": "A", "destination": "1.2.3.4"}
        ]
        is_valid, error = self.ac.validate_dns_records_update("test-token-2", "example.com", records)
        self.assertTrue(is_valid)
        self.assertIsNone(error)
        
        # Token 2 deleting web1 record (should succeed)
        records = [
            {"hostname": "web1", "type": "A", "destination": "1.2.3.4", "id": "789", "deleterecord": True}
        ]
        is_valid, error = self.ac.validate_dns_records_update("test-token-2", "example.com", records)
        self.assertTrue(is_valid)
        self.assertIsNone(error)


if __name__ == "__main__":
    unittest.main()
