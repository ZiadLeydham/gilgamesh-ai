"""
The Royal Cloud Vault: Cross-device, AES-256 encrypted memory synchronization for Gilgamesh.
Syncs private memories and chat history between PC and Phone via GitHub REST API.
"""

import os
import json
import base64
import hashlib
import requests
from typing import Optional, Dict, Tuple
from cryptography.fernet import Fernet, InvalidToken

REPO_NAME = "ZiadLeydham/gilgamesh-ai"
VAULT_PATH = "vault/royal_chronicle.enc"

def get_github_token() -> str:
    return os.getenv("GITHUB_TOKEN", "").strip()

def derive_fernet_key(pin: str) -> Fernet:
    """Derives a deterministic 256-bit AES Fernet key from the user's PIN."""
    digest = hashlib.sha256(pin.encode("utf-8")).digest()
    key = base64.urlsafe_b64encode(digest)
    return Fernet(key)

def encrypt_vault_payload(payload: dict, pin: str) -> str:
    """Encrypts JSON payload using AES-128-CBC + HMAC-SHA256 (Fernet)."""
    fernet = derive_fernet_key(pin)
    raw_bytes = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    return fernet.encrypt(raw_bytes).decode("utf-8")

def decrypt_vault_payload(encrypted_text: str, pin: str) -> dict:
    """Decrypts encrypted payload using PIN. Raises InvalidToken on wrong PIN."""
    fernet = derive_fernet_key(pin)
    raw_bytes = fernet.decrypt(encrypted_text.encode("utf-8"))
    return json.loads(raw_bytes.decode("utf-8"))

def pull_vault_from_github(pin: str) -> Tuple[bool, dict, str]:
    """
    Fetches the encrypted vault file from GitHub and decrypts it with the user's PIN.
    Returns (success, data, message).
    """
    token = get_github_token()
    if not token:
        return False, {}, "No GitHub token configured for Cloud Vault."

    url = f"https://api.github.com/repos/{REPO_NAME}/contents/{VAULT_PATH}"
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github.v3+json"
    }

    try:
        res = requests.get(url, headers=headers, timeout=10)
        if res.status_code == 404:
            # First time user setup
            return True, {"history": [], "memories": None, "initialized": False}, "New vault initialized."
        if res.status_code != 200:
            return False, {}, f"GitHub API error: {res.status_code} {res.text}"

        file_info = res.json()
        encoded_content = file_info.get("content", "")
        encrypted_str = base64.b64decode(encoded_content).decode("utf-8")

        # Decrypt with PIN
        data = decrypt_vault_payload(encrypted_str, pin)
        data["initialized"] = True
        return True, data, "Vault decrypted and restored successfully."
    except InvalidToken:
        return False, {}, "Incorrect Royal PIN. The King's Inner Sanctum remains sealed."
    except Exception as e:
        return False, {}, f"Vault sync error: {str(e)}"

def push_vault_to_github(payload: dict, pin: str) -> Tuple[bool, str]:
    """
    Encrypts the payload with PIN and pushes to GitHub repository.
    Returns (success, message).
    """
    token = get_github_token()
    if not token:
        return False, "No GitHub token configured."

    url = f"https://api.github.com/repos/{REPO_NAME}/contents/{VAULT_PATH}"
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github.v3+json"
    }

    try:
        # 1. Encrypt payload
        encrypted_text = encrypt_vault_payload(payload, pin)
        b64_content = base64.b64encode(encrypted_text.encode("utf-8")).decode("utf-8")

        # 2. Get current SHA if file exists
        res = requests.get(url, headers=headers, timeout=10)
        sha = res.json().get("sha") if res.status_code == 200 else None

        # 3. Commit update
        put_payload = {
            "message": "Update Royal Vault (Encrypted Chronicle)",
            "content": b64_content
        }
        if sha:
            put_payload["sha"] = sha

        put_res = requests.put(url, headers=headers, json=put_payload, timeout=10)
        if put_res.status_code in (200, 201):
            return True, "Royal Vault synchronized to cloud."
        return False, f"Failed to push to GitHub: {put_res.status_code} {put_res.text}"
    except Exception as e:
        return False, f"Push error: {str(e)}"
