"""
SSH key management for Obsidian Timemachine.

Provides functions for finding, generating, and managing SSH keys.
"""

from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass
from pathlib import Path

from .logger import get_logger


DEFAULT_SSH_DIR = Path.home() / ".ssh"
DEFAULT_KEY_NAME = "id_ed25519_obsidian_sync"


@dataclass
class SSHKey:
    """Represents an SSH key pair.
    
    Attributes:
        private_key_path: Path to the private key file.
        public_key_path: Path to the public key file.
        key_type: Type of key (e.g., "ed25519", "rsa").
    """
    private_key_path: Path
    public_key_path: Path
    key_type: str | None = None
    
    @property
    def exists(self) -> bool:
        """Check if both key files exist."""
        return self.private_key_path.exists() and self.public_key_path.exists()
    
    def get_public_key_content(self) -> str | None:
        """Read the public key content."""
        if not self.public_key_path.exists():
            return None
        try:
            return self.public_key_path.read_text().strip()
        except OSError:
            return None


def find_ssh_keys(ssh_dir: Path | None = None) -> list[SSHKey]:
    """Find existing SSH private keys.
    
    Args:
        ssh_dir: Directory to search. Defaults to ~/.ssh
        
    Returns:
        List of found SSH keys.
    """
    ssh_dir = Path(ssh_dir or DEFAULT_SSH_DIR).expanduser().resolve()
    
    if not ssh_dir.exists():
        return []
    
    keys: list[SSHKey] = []
    
    # Common private key patterns
    for key_file in ssh_dir.glob("id_*"):
        # Skip public keys and known_hosts
        if key_file.suffix == ".pub" or "known_hosts" in key_file.name:
            continue
        
        # Skip if it's a directory
        if key_file.is_dir():
            continue
        
        # Check for corresponding public key
        public_key = key_file.with_suffix(key_file.suffix + ".pub")
        if not public_key.exists():
            public_key = Path(str(key_file) + ".pub")
        
        # Determine key type from filename
        key_type = None
        if "ed25519" in key_file.name:
            key_type = "ed25519"
        elif "rsa" in key_file.name:
            key_type = "rsa"
        elif "ecdsa" in key_file.name:
            key_type = "ecdsa"
        elif "dsa" in key_file.name:
            key_type = "dsa"
        
        keys.append(SSHKey(
            private_key_path=key_file,
            public_key_path=public_key,
            key_type=key_type,
        ))
    
    return keys


def check_key_permissions(key_path: Path) -> tuple[bool, str]:
    """Check if SSH key has correct permissions.
    
    SSH keys should have permissions 600 or 400.
    
    Args:
        key_path: Path to the private key.
        
    Returns:
        Tuple of (is_valid, current_permissions).
    """
    key_path = Path(key_path).expanduser().resolve()
    
    if not key_path.exists():
        return False, "file not found"
    
    try:
        mode = key_path.stat().st_mode & 0o777
        mode_str = oct(mode)[2:]
        
        is_valid = mode in (0o600, 0o400)
        return is_valid, mode_str
    except OSError:
        return False, "error"


def fix_key_permissions(key_path: Path) -> bool:
    """Fix SSH key permissions to 600.
    
    Args:
        key_path: Path to the private key.
        
    Returns:
        True if permissions were fixed successfully.
    """
    logger = get_logger()
    key_path = Path(key_path).expanduser().resolve()
    
    try:
        os.chmod(key_path, 0o600)
        logger.info(f"✅ Fixed SSH key permissions for {key_path}")
        return True
    except OSError as e:
        logger.error(f"❌ Failed to fix SSH key permissions: {e}")
        return False


def generate_ssh_key(
    email: str,
    key_path: Path | None = None,
    key_type: str = "ed25519",
    overwrite: bool = False,
) -> SSHKey | None:
    """Generate a new SSH key pair.
    
    Args:
        email: Email address for the key comment.
        key_path: Path for the private key. Defaults to ~/.ssh/id_ed25519_obsidian_sync
        key_type: Key type (ed25519 or rsa).
        overwrite: Whether to overwrite existing key.
        
    Returns:
        SSHKey object if successful, None otherwise.
    """
    logger = get_logger()
    
    if key_path is None:
        key_path = DEFAULT_SSH_DIR / DEFAULT_KEY_NAME
    
    key_path = Path(key_path).expanduser().resolve()
    public_key_path = Path(str(key_path) + ".pub")
    
    # Check if key exists
    if key_path.exists() and not overwrite:
        logger.warning(f"⚠️ Key already exists: {key_path}")
        return SSHKey(
            private_key_path=key_path,
            public_key_path=public_key_path,
            key_type=key_type,
        )
    
    # Ensure directory exists
    key_path.parent.mkdir(parents=True, exist_ok=True)
    
    logger.info(f"⚙️ Generating new {key_type.upper()} SSH key...")
    
    # Build ssh-keygen command
    cmd = [
        "ssh-keygen",
        "-t", key_type,
        "-C", email,
        "-f", str(key_path),
        "-N", "",  # No passphrase (security trade-off for automation)
    ]
    
    # Log security warning about passphrase-less key
    logger.warning(
        "⚠️ Generating SSH key without passphrase. "
        "This is required for automated operation but reduces security. "
        "Keep the private key file secure!"
    )
    
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=30,
        )
        
        if result.returncode == 0 and key_path.exists():
            logger.info(f"✅ SSH key generated: {key_path}")
            return SSHKey(
                private_key_path=key_path,
                public_key_path=public_key_path,
                key_type=key_type,
            )
        else:
            logger.error(f"❌ ssh-keygen failed: {result.stderr}")
            return None
    
    except subprocess.TimeoutExpired:
        logger.error("❌ ssh-keygen timed out")
        return None
    except OSError as e:
        logger.error(f"❌ Failed to run ssh-keygen: {e}")
        return None


def test_ssh_connection(
    host: str = "github.com",
    ssh_key_path: Path | None = None,
) -> bool:
    """Test SSH connection to a host.
    
    Args:
        host: Host to connect to.
        ssh_key_path: Path to SSH private key.
        
    Returns:
        True if connection is successful.
    """
    logger = get_logger()
    
    cmd = ["ssh", "-T", f"git@{host}"]
    
    env = os.environ.copy()
    if ssh_key_path:
        ssh_key_path = Path(ssh_key_path).expanduser().resolve()
        env["GIT_SSH_COMMAND"] = f"ssh -i {ssh_key_path} -o IdentitiesOnly=yes"
    
    # Add StrictHostKeyChecking=accept-new to auto-accept new hosts
    cmd = [
        "ssh", "-T",
        "-o", "StrictHostKeyChecking=accept-new",
        "-o", "ConnectTimeout=10",
    ]
    
    if ssh_key_path:
        cmd.extend(["-i", str(ssh_key_path), "-o", "IdentitiesOnly=yes"])
    
    cmd.append(f"git@{host}")
    
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=15,
        )
        
        # GitHub returns exit code 1 but with success message
        if "successfully authenticated" in result.stderr.lower():
            logger.info(f"✅ SSH connection to {host} successful")
            return True
        
        # GitLab and others might return 0
        if result.returncode == 0:
            logger.info(f"✅ SSH connection to {host} successful")
            return True
        
        logger.warning(f"⚠️ SSH connection test unclear: {result.stderr}")
        return False
    
    except subprocess.TimeoutExpired:
        logger.error(f"❌ SSH connection to {host} timed out")
        return False
    except OSError as e:
        logger.error(f"❌ SSH test failed: {e}")
        return False
