"""
Environment File Manager

This module handles updating the .env file with different model configurations
and backing up/restoring the original .env file.
"""

import os
import shutil
from typing import Dict
from benchmark.config.benchmark_settings import ENV_FILE


class EnvManager:
    """Manages .env file updates for benchmarking."""

    def __init__(self):
        self.env_file = ENV_FILE
        self.backup_file = ENV_FILE + ".backup"
        self.original_env = {}

    def backup_env(self):
        """Create a backup of the current .env file."""
        if os.path.exists(self.env_file):
            shutil.copy2(self.env_file, self.backup_file)
            print(f" Backed up .env to {self.backup_file}")
            # Also load original values
            self.original_env = self._load_env()
        else:
            raise FileNotFoundError(f".env file not found at {self.env_file}")

    def restore_env(self):
        """Restore the original .env file from backup."""
        if os.path.exists(self.backup_file):
            shutil.copy2(self.backup_file, self.env_file)
            print(f" Restored .env from backup")
        else:
            print("WARNING: No backup file found to restore")

    def update_env(self, config: Dict[str, str]):
        """
        Update .env file with new configuration values.

        Args:
            config: Dictionary of environment variables to update
        """
        # Read current .env file
        env_lines = []
        if os.path.exists(self.env_file):
            with open(self.env_file, 'r') as f:
                env_lines = f.readlines()

        # Track which keys we've updated
        updated_keys = set()

        # Update existing keys
        for i, line in enumerate(env_lines):
            line = line.strip()
            if not line or line.startswith('#'):
                continue

            if '=' in line:
                key = line.split('=')[0].strip()
                if key in config:
                    env_lines[i] = f"{key}={config[key]}\n"
                    updated_keys.add(key)

        # Add any new keys that weren't in the file
        for key, value in config.items():
            if key not in updated_keys:
                env_lines.append(f"{key}={value}\n")

        # Write updated .env file
        with open(self.env_file, 'w') as f:
            f.writelines(env_lines)

        print(f" Updated .env with {len(config)} configuration values")

    def _load_env(self) -> Dict[str, str]:
        """Load current .env file into a dictionary."""
        env_dict = {}
        if os.path.exists(self.env_file):
            with open(self.env_file, 'r') as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith('#') and '=' in line:
                        key, value = line.split('=', 1)
                        env_dict[key.strip()] = value.strip()
        return env_dict

    def get_current_value(self, key: str) -> str:
        """Get the current value of a specific environment variable."""
        env_dict = self._load_env()
        return env_dict.get(key, "")

    def cleanup_backup(self):
        """Remove the backup file."""
        if os.path.exists(self.backup_file):
            os.remove(self.backup_file)
            print(f" Cleaned up backup file")


def switch_to_model_config(model_name: str, config: Dict[str, str]):
    """
    Convenience function to switch to a specific model configuration.

    Args:
        model_name: Name of the model (for logging)
        config: Configuration dictionary to apply
    """
    env_manager = EnvManager()
    env_manager.update_env(config)
    print(f" Switched to {model_name} configuration")


if __name__ == "__main__":
    # Test the EnvManager
    manager = EnvManager()
    print(f"Current AI_MODEL: {manager.get_current_value('AI_MODEL')}")
    print(f"Current USE_LOCAL_LLM: {manager.get_current_value('USE_LOCAL_LLM')}")
