"""
Authentication module for LiveKit Manager API.

Provides HTTP Basic Authentication for API endpoints.
"""

from .basic_auth import verify_basic_auth, security

__all__ = ["verify_basic_auth", "security"]
