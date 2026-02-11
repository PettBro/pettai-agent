"""
Unit tests for session token encryption functionality.

Tests the encryption, decryption, and secure storage of session tokens.
"""

import base64
import json
import os
import stat
import tempfile
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from cryptography.fernet import InvalidToken

# Import the class we're testing
import sys

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "olas-sdk-starter"))

from agent.pett_websocket_client import PettWebSocketClient


class TestSessionTokenEncryption:
    """Test suite for session token encryption and secure storage."""

    @staticmethod
    def _build_fake_jwt(exp_timestamp: int) -> str:
        """Build an unsigned JWT-like token for expiry parsing tests."""

        def _encode(data: dict) -> str:
            raw = json.dumps(data, separators=(",", ":")).encode("utf-8")
            return base64.urlsafe_b64encode(raw).decode("utf-8").rstrip("=")

        header = _encode({"alg": "none", "typ": "JWT"})
        payload = _encode({"exp": exp_timestamp})
        return f"{header}.{payload}.signature"

    @pytest.fixture
    def temp_dir(self):
        """Create a temporary directory for test files."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield Path(tmpdir)

    @pytest.fixture
    def client(self, temp_dir):
        """Create a test client with temporary storage."""
        with patch.dict(os.environ, {"STORE_PATH": str(temp_dir)}):
            client = PettWebSocketClient(
                websocket_url="wss://test.example.com", session_token="test_token_12345"
            )
            return client

    def test_encryption_key_generation(self, client):
        """Test that encryption key is generated consistently."""
        key1 = client._get_encryption_key()
        key2 = client._get_encryption_key()

        assert key1 == key2, "Encryption key should be deterministic"
        assert (
            len(key1) == 44
        ), "Fernet key should be 44 bytes (base64 encoded 32 bytes)"

    def test_token_encryption_decryption(self, client):
        """Test that tokens can be encrypted and decrypted."""
        original_token = "test_session_token_xyz123"

        encrypted = client._encrypt_token(original_token)
        assert (
            encrypted != original_token
        ), "Encrypted token should differ from original"

        decrypted = client._decrypt_token(encrypted)
        assert decrypted == original_token, "Decrypted token should match original"

    def test_token_encryption_uniqueness(self, client):
        """Test that same token produces different ciphertext each time."""
        token = "test_token_123"

        encrypted1 = client._encrypt_token(token)
        encrypted2 = client._encrypt_token(token)

        # Fernet includes timestamp and random IV, so ciphertexts differ
        assert (
            encrypted1 != encrypted2
        ), "Encryptions should produce different ciphertexts"

        # But both should decrypt to same plaintext
        assert client._decrypt_token(encrypted1) == token
        assert client._decrypt_token(encrypted2) == token

    def test_invalid_token_decryption(self, client):
        """Test that invalid encrypted tokens raise proper exception."""
        invalid_encrypted = "invalid_base64_gibberish"

        with pytest.raises(Exception):  # Could be InvalidToken or other crypto error
            client._decrypt_token(invalid_encrypted)

    def test_tampered_token_decryption(self, client):
        """Test that tampered tokens cannot be decrypted."""
        original_token = "test_token_123"
        encrypted = client._encrypt_token(original_token)

        # Tamper with the encrypted token (flip a bit)
        tampered = encrypted[:-4] + ("XXXX" if encrypted[-4:] != "XXXX" else "YYYY")

        with pytest.raises((InvalidToken, Exception)):
            client._decrypt_token(tampered)

    def test_persist_encrypted_token(self, client, temp_dir):
        """Test that tokens are persisted in encrypted form."""
        test_token = "my_secret_session_token"
        client.session_token = test_token

        # Persist the token
        client._persist_session_token()

        # Read the raw file
        token_file = client._session_store_path
        assert token_file.exists(), "Token file should exist"

        with open(token_file, "r") as f:
            data = json.load(f)

        # Verify token is encrypted
        assert "encryptedSessionToken" in data, "Should have encrypted token field"
        assert "sessionToken" not in data, "Should not have plaintext token field"
        assert data["encryptedSessionToken"] != test_token, "Token should be encrypted"

    def test_load_encrypted_token(self, client, temp_dir):
        """Test that encrypted tokens are loaded correctly."""
        import time

        test_token = "my_secret_session_token"
        # Use a future timestamp (10 years from now)
        expires_at = int(time.time()) + (10 * 365 * 24 * 60 * 60)

        # Create a new client and persist a token
        client.session_token = test_token
        client._session_expires_at = expires_at
        client._persist_session_token()

        # Create a new client to load the token
        with patch.dict(os.environ, {"STORE_PATH": str(temp_dir)}):
            new_client = PettWebSocketClient(websocket_url="wss://test.example.com")

        # Token should be loaded automatically in __init__
        assert new_client.session_token == test_token, "Token should be loaded"
        # Expiry is normalized to milliseconds, so check for that
        expected_expires_at_ms = (
            expires_at * 1000 if expires_at < 10**12 else expires_at
        )
        assert (
            new_client._session_expires_at == expected_expires_at_ms
        ), "Expiry should be loaded"

    def test_load_legacy_plaintext_token(self, client, temp_dir):
        """Test that legacy plaintext tokens can still be loaded."""
        import time

        test_token = "legacy_plaintext_token"
        # Use a future timestamp (10 years from now)
        expires_at = int(time.time()) + (10 * 365 * 24 * 60 * 60)

        # Manually write a plaintext token file (legacy format)
        token_file = client._session_store_path
        token_file.parent.mkdir(parents=True, exist_ok=True)

        with open(token_file, "w") as f:
            json.dump({"sessionToken": test_token, "sessionExpiresAt": expires_at}, f)

        # Load the token
        loaded_token, loaded_expiry = client._load_persisted_session_token()

        assert loaded_token == test_token, "Legacy token should be loaded"
        # Expiry is normalized to milliseconds, so check for that
        expected_expires_at_ms = (
            expires_at * 1000 if expires_at < 10**12 else expires_at
        )
        assert loaded_expiry == expected_expires_at_ms, "Legacy expiry should be loaded"

    def test_expired_token_not_loaded(self, client, temp_dir):
        """Test that expired tokens are not loaded."""
        test_token = "expired_token"
        expires_at = 1000000000  # Old timestamp (expired)

        # Persist an expired token
        client.session_token = test_token
        client._session_expires_at = expires_at
        client._persist_session_token()

        # Try to load it with a new client
        with patch.dict(os.environ, {"STORE_PATH": str(temp_dir)}):
            new_client = PettWebSocketClient(websocket_url="wss://test.example.com")

        # Token should not be loaded (expired)
        assert new_client.session_token == "", "Expired token should not be loaded"

        # File should be deleted
        token_file = new_client._session_store_path
        assert not token_file.exists(), "Expired token file should be deleted"

    @pytest.mark.skipif(os.name == "nt", reason="Unix-only permission test")
    def test_file_permissions_unix(self, client, temp_dir):
        """Test that token files have restrictive permissions on Unix."""
        test_token = "test_token_permissions"
        client.session_token = test_token

        # Persist the token
        client._persist_session_token()

        # Check file permissions
        token_file = client._session_store_path
        file_stat = os.stat(token_file)
        mode = stat.filemode(file_stat.st_mode)

        assert mode == "-rw-------", f"File should have mode -rw-------, got {mode}"

        # Check octal permissions
        octal_mode = oct(file_stat.st_mode)[-3:]
        assert (
            octal_mode == "600"
        ), f"File should have permissions 600, got {octal_mode}"

    def test_delete_persisted_token(self, client, temp_dir):
        """Test that persisted tokens can be deleted."""
        test_token = "test_token_delete"
        client.session_token = test_token

        # Persist the token
        client._persist_session_token()
        token_file = client._session_store_path
        assert token_file.exists(), "Token file should exist"

        # Delete the token
        client._delete_persisted_session_token()
        assert not token_file.exists(), "Token file should be deleted"

    def test_clear_session_token(self, client, temp_dir):
        """Test that clearing session token removes persisted file."""
        test_token = "test_token_clear"
        client.session_token = test_token

        # Persist the token
        client._persist_session_token()
        token_file = client._session_store_path
        assert token_file.exists(), "Token file should exist"

        # Clear the token
        client.clear_session_token()

        assert client.session_token == "", "Token should be cleared from memory"
        assert not token_file.exists(), "Token file should be deleted"

    def test_auth_candidates_include_privy_fallback(self, client):
        """Test that auth candidates always include Privy as fallback."""
        # Set both session and Privy tokens
        client.session_token = "session_token_123"
        client.privy_token = "privy_token_456"

        candidates = client._get_auth_candidates()

        # Should have both tokens
        assert len(candidates) >= 2, "Should have at least session and Privy tokens"

        # Extract token types
        token_types = [auth_type for auth_type, _, _ in candidates]

        assert "session" in token_types, "Session token should be in candidates"
        assert "privy" in token_types, "Privy token should be in candidates"

        # Session should come first
        assert candidates[0][0] == "session", "Session should be tried first"

    def test_auth_candidates_privy_only_when_no_session(self, client):
        """Test that Privy is used when no session token exists."""
        # Set only Privy token
        client.session_token = ""
        client.privy_token = "privy_token_789"

        candidates = client._get_auth_candidates()

        # Should have only Privy token
        assert len(candidates) == 1, "Should have only Privy token"
        assert candidates[0][0] == "privy", "Should be Privy auth"
        assert candidates[0][1] == "privy_token_789", "Should have correct token"

    def test_auth_candidates_skip_locally_expired_privy_jwt(self, client):
        """Expired JWTs should be skipped from auth candidates."""
        client.session_token = ""
        expired_jwt = self._build_fake_jwt(int(time.time()) - 60)
        client.set_privy_token(expired_jwt)

        candidates = client._get_auth_candidates()

        assert candidates == [], "Expired Privy JWT should not be used as candidate"
        assert client.is_jwt_expired() is True

    def test_same_expired_privy_token_keeps_expired_state(self, client):
        """Re-setting the same expired token should not clear expiry state."""
        expired_jwt = self._build_fake_jwt(int(time.time()) - 120)
        client._mark_privy_jwt_expired("Invalid or expired token", token=expired_jwt)

        client.set_privy_token(expired_jwt)

        assert client.is_jwt_expired() is True
        assert client.is_known_expired_privy_token(expired_jwt) is True

    def test_new_privy_token_clears_expired_state(self, client):
        """A different Privy token should clear previous JWT-expired state."""
        expired_jwt = self._build_fake_jwt(int(time.time()) - 120)
        fresh_jwt = self._build_fake_jwt(int(time.time()) + 3600)
        client._mark_privy_jwt_expired("Invalid or expired token", token=expired_jwt)

        client.set_privy_token(fresh_jwt)

        assert client.is_jwt_expired() is False
        assert client.is_known_expired_privy_token(fresh_jwt) is False


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
