"""
User role constants. Use these instead of string literals throughout the codebase.
"""

ROLE_ADMIN = "admin"
ROLE_PI = "pi"
ROLE_RESEARCHER = "researcher"

ROLES_ALL = (ROLE_ADMIN, ROLE_PI, ROLE_RESEARCHER)
ROLES_CAN_CREATE_PROJECT = (ROLE_ADMIN, ROLE_PI, ROLE_RESEARCHER)
