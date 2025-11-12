#!/usr/bin/env python3
"""
Example client for testing the Netcup API Filter Proxy

This script demonstrates how to use the filter proxy to:
1. Read DNS zone information
2. List DNS records (with filtering)
3. Update a DNS record
"""
import requests
import json
import argparse


def make_request(base_url: str, token: str, action: str, param: dict):
    """Make a request to the filter proxy"""
    url = f"{base_url}/api"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {token}"
    }
    payload = {
        "action": action,
        "param": param
    }
    
    try:
        response = requests.post(url, headers=headers, json=payload, timeout=10)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        print(f"Error: {e}")
        if hasattr(e, 'response') and e.response is not None:
            print(f"Response: {e.response.text}")
        return None


def test_info_dns_zone(base_url: str, token: str, domain: str):
    """Test getting DNS zone information"""
    print(f"\n=== Testing infoDnsZone for {domain} ===")
    result = make_request(base_url, token, "infoDnsZone", {
        "domainname": domain
    })
    print(json.dumps(result, indent=2))
    return result


def test_info_dns_records(base_url: str, token: str, domain: str):
    """Test getting DNS records"""
    print(f"\n=== Testing infoDnsRecords for {domain} ===")
    result = make_request(base_url, token, "infoDnsRecords", {
        "domainname": domain
    })
    print(json.dumps(result, indent=2))
    return result


def test_update_dns_record(base_url: str, token: str, domain: str, 
                          record_id: str, hostname: str, record_type: str, destination: str):
    """Test updating a DNS record"""
    print(f"\n=== Testing updateDnsRecords for {domain}/{hostname} ===")
    result = make_request(base_url, token, "updateDnsRecords", {
        "domainname": domain,
        "dnsrecordset": {
            "dnsrecords": [
                {
                    "id": record_id,
                    "hostname": hostname,
                    "type": record_type,
                    "destination": destination,
                    "priority": "0",
                    "state": "yes",
                    "deleterecord": False
                }
            ]
        }
    })
    print(json.dumps(result, indent=2))
    return result


def test_unauthorized_access(base_url: str, token: str, domain: str):
    """Test access to a record that token doesn't have permission for"""
    print(f"\n=== Testing unauthorized access ===")
    result = make_request(base_url, token, "updateDnsRecords", {
        "domainname": domain,
        "dnsrecordset": {
            "dnsrecords": [
                {
                    "hostname": "unauthorized-host",
                    "type": "A",
                    "destination": "1.2.3.4",
                    "priority": "0",
                    "state": "yes",
                    "deleterecord": False
                }
            ]
        }
    })
    print(json.dumps(result, indent=2))
    return result


def main():
    parser = argparse.ArgumentParser(description="Test the Netcup API Filter Proxy")
    parser.add_argument("--url", default="http://localhost:5000", 
                       help="Base URL of the filter proxy")
    parser.add_argument("--token", required=True, 
                       help="Authentication token")
    parser.add_argument("--domain", required=True, 
                       help="Domain name to test with")
    parser.add_argument("--test", choices=["zone", "records", "update", "unauthorized", "all"],
                       default="all", help="Which test to run")
    
    # Optional parameters for update test
    parser.add_argument("--record-id", help="Record ID for update test")
    parser.add_argument("--hostname", help="Hostname for update test")
    parser.add_argument("--type", help="Record type for update test (e.g., A, AAAA)")
    parser.add_argument("--destination", help="Destination IP for update test")
    
    args = parser.parse_args()
    
    print(f"Testing Netcup API Filter Proxy at {args.url}")
    print(f"Using token: {args.token[:10]}...")
    print(f"Domain: {args.domain}")
    
    # Run tests based on selection
    if args.test in ["zone", "all"]:
        test_info_dns_zone(args.url, args.token, args.domain)
    
    if args.test in ["records", "all"]:
        test_info_dns_records(args.url, args.token, args.domain)
    
    if args.test == "update":
        if not all([args.record_id, args.hostname, args.type, args.destination]):
            print("\nError: --record-id, --hostname, --type, and --destination required for update test")
            return
        test_update_dns_record(args.url, args.token, args.domain,
                              args.record_id, args.hostname, args.type, args.destination)
    
    if args.test in ["unauthorized", "all"]:
        test_unauthorized_access(args.url, args.token, args.domain)


if __name__ == "__main__":
    main()
