#!/usr/bin/env python3
"""
Token Generator for Netcup API Filter
Generates cryptographically secure tokens and outputs configuration
"""
import argparse
import sys
import yaml
from .utils import generate_token as _generate_admin_token


def generate_secure_token(min_length: int = 63, max_length: int = 65) -> str:
    """Generate an [a-zA-Z0-9] token that matches the requested length window."""
    return _generate_admin_token(min_length=min_length, max_length=max_length)


def create_token_config(description: str, domain: str, record_name: str,
                       record_types: list, operations: list,
                       allowed_origins: list = None,
                       min_length: int = 63,
                       max_length: int = 65) -> dict:
    """
    Create a token configuration dictionary
    
    Args:
        description: Human-readable description of the token
        domain: Domain name for permissions
        record_name: Record name pattern (supports wildcards)
        record_types: List of allowed record types
        operations: List of allowed operations
        allowed_origins: Optional list of allowed IP addresses or domains
        min_length: Minimum token length (inclusive)
        max_length: Maximum token length (inclusive)
    
    Returns:
        Token configuration dictionary
    """
    token = generate_secure_token(min_length=min_length, max_length=max_length)
    
    config = {
        "token": token,
        "description": description,
        "permissions": [
            {
                "domain": domain,
                "record_name": record_name,
                "record_types": record_types,
                "operations": operations
            }
        ]
    }
    
    if allowed_origins:
        config["allowed_origins"] = allowed_origins
    
    return config


def main():
    parser = argparse.ArgumentParser(
        description="Generate secure tokens for Netcup API Filter",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    # Generate a token for dynamic DNS (host updates its own A record)
    %(prog)s --description "Host1 Dynamic DNS" --domain example.com --record-name host1 --record-types A --operations read,update

  # Generate a read-only monitoring token
  %(prog)s --description "Monitoring" --domain example.com --record-name "*" --record-types "*" --operations read

  # Generate a token with IP whitelist
  %(prog)s --description "Server1" --domain example.com --record-name server1 --record-types A,AAAA --operations read,update --allowed-origins 192.168.1.100,10.0.0.0/24

  # Generate a token with domain whitelist
  %(prog)s --description "API Client" --domain example.com --record-name api --record-types A --operations read,update --allowed-origins example.com,*.example.com
"""
    )
    
    parser.add_argument(
        "--description",
        required=True,
        help="Human-readable description of the token"
    )
    
    parser.add_argument(
        "--domain",
        required=True,
        help="Domain name (supports wildcards, e.g., *.example.com)"
    )
    
    parser.add_argument(
        "--record-name",
        required=True,
        help="DNS record hostname (supports wildcards, e.g., web*)"
    )
    
    parser.add_argument(
        "--record-types",
        required=True,
        help="Comma-separated list of record types (e.g., A,AAAA or * for all)"
    )
    
    parser.add_argument(
        "--operations",
        required=True,
        help="Comma-separated list of operations (read,update,create,delete or * for all)"
    )
    
    parser.add_argument(
        "--allowed-origins",
        help="Comma-separated list of allowed IP addresses (with optional CIDR) or domain names"
    )
    
    parser.add_argument(
        "--output-format",
        choices=["yaml", "json", "token-only"],
        default="yaml",
        help="Output format (default: yaml)"
    )
    
    parser.add_argument(
        "--length",
        type=int,
        default=32,
        help="Exact token length in characters (overrides --min-length/--max-length)"
    )

    parser.add_argument(
        "--min-length",
        type=int,
        default=63,
        help="Minimum token length (default: 63)"
    )

    parser.add_argument(
        "--max-length",
        type=int,
        default=65,
        help="Maximum token length (default: 65)"
    )
    
    args = parser.parse_args()
    
    # Parse comma-separated values
    record_types = [rt.strip() for rt in args.record_types.split(",")]
    operations = [op.strip() for op in args.operations.split(",")]
    allowed_origins = None
    if args.allowed_origins:
        allowed_origins = [origin.strip() for origin in args.allowed_origins.split(",")]
    
    # Generate token configuration
    # Determine token length window
    min_length = args.min_length
    max_length = args.max_length
    if args.length:
        min_length = max_length = args.length

    token_config = create_token_config(
        description=args.description,
        domain=args.domain,
        record_name=args.record_name,
        record_types=record_types,
        operations=operations,
        allowed_origins=allowed_origins,
        min_length=min_length,
        max_length=max_length
    )
    
    # Output in requested format
    if args.output_format == "token-only":
        print(token_config["token"])
    elif args.output_format == "json":
        import json
        print(json.dumps(token_config, indent=2))
    else:  # yaml
        print("# Add this to your config.yaml file under 'tokens:'")
        print("  - " + yaml.dump(token_config, default_flow_style=False).replace("\n", "\n    ").rstrip())
        print()
        print(f"# Token value (provide this to the client): {token_config['token']}")
        print(f"# Keep this token secure - it grants access as configured above!")


if __name__ == "__main__":
    main()
