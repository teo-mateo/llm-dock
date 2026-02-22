"""
Model discovery for HuggingFace cache.
Adapted from ai-toolbox/models-backup for dashboard use.
"""

import logging
from pathlib import Path
from typing import List, Dict, Any, Set
import re
import os

logger = logging.getLogger(__name__)


class ModelDiscovery:
    """Base class for model discovery."""

    def __init__(self, base_path: Path):
        """Initialize with base path for model storage."""
        self.base_path = base_path

    def discover(self) -> List[Dict[str, Any]]:
        """Discover models in the base path. Must be implemented by subclasses."""
        raise NotImplementedError("Subclasses must implement discover()")

    def get_size(self, path: Path) -> int:
        """Get total size of a directory in bytes."""
        total_size = 0
        try:
            for item in path.rglob('*'):
                # Skip symlinks to avoid double-counting (HuggingFace uses symlinks to blobs)
                if item.is_file() and not item.is_symlink():
                    total_size += item.stat().st_size
        except PermissionError:
            # Skip files we can't access
            pass
        return total_size

    def format_size(self, size_bytes: int) -> str:
        """Format size in bytes to human-readable format."""
        for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
            if size_bytes < 1024.0:
                return f"{size_bytes:.2f} {unit}"
            size_bytes /= 1024.0
        return f"{size_bytes:.2f} PB"


class GenericModelDiscovery(ModelDiscovery):
    """Discovery for generic model directories containing GGUF files."""

    def discover(self) -> List[Dict[str, Any]]:
        """Discover GGUF models in a generic directory structure."""
        models = []

        if not self.base_path.exists():
            return models

        # Find all .gguf files recursively
        for gguf_file in self.base_path.rglob('*.gguf'):
            try:
                size = gguf_file.stat().st_size

                # Extract a display name from the file
                # Use parent directory name if it's not the base path
                if gguf_file.parent != self.base_path:
                    # Use relative path from base as the model name
                    rel_path = gguf_file.relative_to(self.base_path)
                    name = str(rel_path.parent / gguf_file.stem)
                else:
                    name = gguf_file.stem

                # Check for related files (mmproj, etc.)
                files = [{
                    'name': gguf_file.name,
                    'path': str(gguf_file),
                    'actual_path': str(gguf_file.resolve()),
                    'size': size,
                    'size_str': self.format_size(size)
                }]

                # Look for mmproj files in same directory
                for item in gguf_file.parent.iterdir():
                    if item != gguf_file and item.is_file() and item.suffix == '.mmproj':
                        try:
                            mmproj_size = item.stat().st_size
                            files.append({
                                'name': item.name,
                                'path': str(item),
                                'actual_path': str(item.resolve()),
                                'size': mmproj_size,
                                'size_str': self.format_size(mmproj_size),
                                'related': True
                            })
                        except Exception as e:
                            logger.warning("Failed to read mmproj file %s: %s", item, e)

                total_size = sum(f['size'] for f in files)
                models.append({
                    "name": name,
                    "path": str(gguf_file.parent),
                    "type": "generic",
                    "files": files,
                    "file_count": len(files),
                    "size": total_size,
                    "size_str": self.format_size(total_size),
                    "source_path": str(self.base_path)
                })

            except Exception as e:
                logger.warning("Failed to process model %s: %s", gguf_file, e)

        return sorted(models, key=lambda x: x["size"], reverse=True)


class HuggingFaceDiscovery(ModelDiscovery):
    """Discovery for HuggingFace models."""

    def _get_active_snapshot(self, model_path: Path) -> Path | None:
        """Get the active snapshot directory from refs/main."""
        refs_main = model_path / "refs" / "main"
        if not refs_main.exists():
            return None

        try:
            snapshot_hash = refs_main.read_text().strip()
            snapshot_path = model_path / "snapshots" / snapshot_hash
            if snapshot_path.exists():
                return snapshot_path
        except Exception as e:
            logger.warning("Failed to read snapshot ref for %s: %s", model_path.name, e)

        return None

    def _extract_quantization_from_filename(self, filename: str) -> str | None:
        """
        Extract quantization identifier from a GGUF filename.
        Examples:
        - 'Model-Q4_0.gguf' -> 'Q4_0'
        - 'Model-UD-Q6_K_XL.gguf' -> 'UD-Q6_K_XL'
        - 'Model-IQ3_XXS.gguf' -> 'IQ3_XXS'
        """
        # Remove .gguf extension
        name = filename.replace('.gguf', '')

        # Look for quantization patterns
        # Pattern: Optional UD- prefix + Q/IQ + digit + optional suffix
        patterns = [
            r'(UD-Q\d+[_A-Z0-9]*)',  # UD-Q6_K_XL, UD-Q4_0
            r'(IQ\d+[_A-Z0-9]*)',     # IQ3_XXS, IQ4_XS
            r'(Q\d+[_A-Z0-9]*)',      # Q4_0, Q5_K_M, Q8_0
        ]

        for pattern in patterns:
            match = re.search(pattern, name.upper())
            if match:
                return match.group(1)

        return None

    def _get_quantizations(self, snapshot_path: Path) -> tuple[List[str], str]:
        """
        Get list of quantizations in the snapshot.

        Returns:
            Tuple of (quantization_list, type) where type is 'directory' or 'file'
        """
        quantizations = []
        quant_type = None

        if not snapshot_path.exists():
            return quantizations, quant_type

        # First check for directory-based quantizations
        for item in snapshot_path.iterdir():
            if item.is_dir():
                # Check if this looks like a quantization directory
                # Typical names: Q4_0, Q5_K_M, UD-Q6_K_XL, etc.
                name = item.name
                if any(q in name.upper() for q in ['Q2', 'Q3', 'Q4', 'Q5', 'Q6', 'Q8', 'IQ', 'K_', 'UD-']):
                    quantizations.append(name)
                    quant_type = 'directory'

        # If no directory-based quantizations found, check for file-based
        if not quantizations:
            seen = set()
            for item in snapshot_path.iterdir():
                if item.is_file() and item.name.endswith('.gguf'):
                    # Extract quantization from filename
                    quant = self._extract_quantization_from_filename(item.name)
                    if quant and quant not in seen:
                        seen.add(quant)
                        quantizations.append(quant)
                        quant_type = 'file'

        return sorted(quantizations), quant_type

    def _get_blobs_for_quantization(self, quantization_path: Path, is_directory: bool = True) -> Set[str]:
        """
        Get set of blob hashes referenced by a quantization.

        Args:
            quantization_path: Path to quantization (directory or file)
            is_directory: True if quantization_path is a directory, False if it's a file

        Returns:
            Set of blob hash strings
        """
        blobs = set()

        if not quantization_path.exists():
            return blobs

        if is_directory:
            # Directory-based: scan all files in the directory
            for item in quantization_path.rglob('*'):
                if item.is_symlink() or item.is_file():
                    try:
                        # Resolve symlink to get actual blob path
                        actual_path = item.resolve()
                        # Blob hash is the filename in the blobs directory
                        if 'blobs' in actual_path.parts:
                            blob_index = actual_path.parts.index('blobs')
                            if blob_index + 1 < len(actual_path.parts):
                                blobs.add(actual_path.parts[blob_index + 1])
                    except Exception as e:
                        logger.warning("Failed to resolve blob for %s: %s", item, e)
        else:
            # File-based: single file
            try:
                actual_path = quantization_path.resolve()
                if 'blobs' in actual_path.parts:
                    blob_index = actual_path.parts.index('blobs')
                    if blob_index + 1 < len(actual_path.parts):
                        blobs.add(actual_path.parts[blob_index + 1])
            except Exception as e:
                logger.warning("Failed to resolve blob for %s: %s", quantization_path, e)

        return blobs

    def _get_files_for_quantization_flat(self, snapshot_path: Path, quantization: str) -> List[Path]:
        """
        Find all GGUF files for a given quantization in file-based storage.
        Handles sharded models (e.g., Model-Q4_K-00001-of-00003.gguf).

        Args:
            snapshot_path: Path to snapshot directory
            quantization: Quantization identifier (e.g., 'Q4_0', 'UD-Q6_K_XL')

        Returns:
            Sorted list of matching GGUF file paths
        """
        matches = []
        for item in snapshot_path.iterdir():
            if item.is_file() and item.name.endswith('.gguf'):
                file_quant = self._extract_quantization_from_filename(item.name)
                if file_quant == quantization:
                    matches.append(item)
        return sorted(matches)

    def _get_quantization_size(self, model_path: Path, blobs: Set[str]) -> int:
        """Calculate total size of blobs for a quantization."""
        total_size = 0
        blobs_dir = model_path / "blobs"

        if not blobs_dir.exists():
            return total_size

        for blob_hash in blobs:
            blob_path = blobs_dir / blob_hash
            if blob_path.exists() and blob_path.is_file():
                try:
                    total_size += blob_path.stat().st_size
                except Exception as e:
                    logger.warning("Failed to stat blob %s: %s", blob_path, e)

        return total_size

    def _get_files_for_quantization(self, quantization_path: Path, is_directory: bool = True) -> List[Dict[str, Any]]:
        """
        Get list of actual files (GGUF, mmproj, etc.) for a quantization.

        Args:
            quantization_path: Path to quantization (directory or file)
            is_directory: True if quantization_path is a directory, False if it's a file

        Returns:
            List of file dictionaries with name, path, and size
        """
        files = []

        if not quantization_path.exists():
            return files

        if is_directory:
            # Directory-based: find all .gguf and related files
            for item in sorted(quantization_path.rglob('*')):
                if item.is_file() and (item.suffix in ['.gguf', '.mmproj'] or 'gguf' in item.name.lower()):
                    try:
                        # Resolve symlink to get actual file
                        actual_path = item.resolve()
                        size = actual_path.stat().st_size

                        files.append({
                            'name': item.name,
                            'path': str(item),
                            'actual_path': str(actual_path),
                            'size': size,
                            'size_str': self.format_size(size)
                        })
                    except Exception as e:
                        logger.warning("Failed to read file %s: %s", item, e)
        else:
            # File-based: single file (or check for related files like mmproj)
            try:
                actual_path = quantization_path.resolve()
                size = actual_path.stat().st_size

                files.append({
                    'name': quantization_path.name,
                    'path': str(quantization_path),
                    'actual_path': str(actual_path),
                    'size': size,
                    'size_str': self.format_size(size)
                })

                # Check for related non-quantization files (e.g., mmproj)
                parent_dir = quantization_path.parent
                for item in parent_dir.iterdir():
                    if item != quantization_path and item.is_file() and item.suffix in ['.mmproj', '.gguf'] \
                            and not self._extract_quantization_from_filename(item.name):
                        try:
                            actual_path = item.resolve()
                            size = actual_path.stat().st_size

                            files.append({
                                'name': item.name,
                                'path': str(item),
                                'actual_path': str(actual_path),
                                'size': size,
                                'size_str': self.format_size(size),
                                'related': True  # Mark as related file
                            })
                        except Exception as e:
                            logger.warning("Failed to read related file %s: %s", item, e)

            except Exception as e:
                logger.warning("Failed to process quantization %s: %s", quantization_path, e)

        return files

    def _get_snapshot_files(self, snapshot_path: Path) -> List[Dict[str, Any]]:
        """
        Get all model files from a snapshot directory (for non-GGUF models).

        Args:
            snapshot_path: Path to snapshot directory

        Returns:
            List of file dictionaries with name, path, and size
        """
        files = []

        if not snapshot_path.exists():
            return files

        # Get all significant model files (safetensors, bin, pt, gguf, etc.)
        model_extensions = ['.safetensors', '.bin', '.pt', '.pth', '.onnx', '.msgpack', '.gguf', '.mmproj']

        for item in sorted(snapshot_path.rglob('*')):
            if item.is_file() and item.suffix in model_extensions:
                try:
                    actual_path = item.resolve()
                    size = actual_path.stat().st_size

                    files.append({
                        'name': item.name,
                        'path': str(item),
                        'actual_path': str(actual_path),
                        'size': size,
                        'size_str': self.format_size(size)
                    })
                except Exception as e:
                    logger.warning("Failed to read snapshot file %s: %s", item, e)

        return files

    def discover(self) -> List[Dict[str, Any]]:
        """Discover HuggingFace models in the cache directory, listing each quantization separately."""
        models = []

        if not self.base_path.exists():
            return models

        # HuggingFace uses models--org--name format
        for path in self.base_path.iterdir():
            if path.is_dir() and path.name.startswith("models--"):
                # Extract org and model name
                parts = path.name.split("--")
                if len(parts) >= 3:
                    org = parts[1]
                    model = "--".join(parts[2:])  # Handle names with dashes
                    model_name = f"{org}/{model}"

                    # Get active snapshot
                    snapshot_path = self._get_active_snapshot(path)
                    if not snapshot_path:
                        # No snapshot found, list as single model (old behavior)
                        size = self.get_size(path)
                        models.append({
                            "name": model_name,
                            "path": str(path),
                            "type": "huggingface",
                            "size": size,
                            "size_str": self.format_size(size)
                        })
                        continue

                    # Get quantizations
                    quantizations, quant_type = self._get_quantizations(snapshot_path)

                    if not quantizations:
                        # No quantizations found - get all model files (safetensors, bin, etc.)
                        size = self.get_size(path)
                        files = self._get_snapshot_files(snapshot_path)

                        models.append({
                            "name": model_name,
                            "path": str(path),
                            "type": "huggingface",
                            "size": size,
                            "size_str": self.format_size(size),
                            "files": files,
                            "file_count": len(files),
                            "snapshot_path": str(snapshot_path)
                        })
                    else:
                        # List each quantization separately
                        for quant in quantizations:
                            if quant_type == 'directory':
                                # Directory-based quantization
                                quant_path = snapshot_path / quant
                                blobs = self._get_blobs_for_quantization(quant_path, is_directory=True)
                                files = self._get_files_for_quantization(quant_path, is_directory=True)
                            else:  # file-based
                                # File-based quantization (may be sharded)
                                quant_files = self._get_files_for_quantization_flat(snapshot_path, quant)
                                if not quant_files:
                                    continue
                                quant_path = quant_files[0]
                                # Collect blobs and file info from all shards
                                blobs = set()
                                files = []
                                for i, qf in enumerate(quant_files):
                                    blobs |= self._get_blobs_for_quantization(qf, is_directory=False)
                                    shard_files = self._get_files_for_quantization(qf, is_directory=False)
                                    if i == 0:
                                        # First shard: include related files (mmproj etc.)
                                        files.extend(shard_files)
                                    else:
                                        # Subsequent shards: only the shard file itself
                                        files.extend(f for f in shard_files if not f.get('related'))

                            size = self._get_quantization_size(path, blobs)

                            models.append({
                                "name": model_name,
                                "quantization": quant,
                                "quantization_type": quant_type,  # 'directory' or 'file'
                                "full_name": f"{model_name} [{quant}]",
                                "base_path": str(path),
                                "snapshot_path": str(snapshot_path),
                                "quantization_path": str(quant_path),
                                "files": files,
                                "file_count": len(files),
                                "type": "huggingface",
                                "size": size,
                                "size_str": self.format_size(size)
                            })

        return sorted(models, key=lambda x: x["size"], reverse=True)


def get_disk_usage(path: str = None) -> Dict[str, Any]:
    """Get disk usage statistics for a given path (defaults to home directory)."""
    if path is None:
        path = os.path.expanduser("~")

    try:
        stat = os.statvfs(path)
        total = stat.f_blocks * stat.f_frsize
        free = stat.f_bavail * stat.f_frsize
        used = total - free
        percent = (used / total) * 100 if total > 0 else 0

        discovery = ModelDiscovery(Path(path))

        return {
            "path": path,
            "total": total,
            "used": used,
            "free": free,
            "percent": round(percent, 2),
            "total_str": discovery.format_size(total),
            "used_str": discovery.format_size(used),
            "free_str": discovery.format_size(free)
        }
    except Exception as e:
        return {
            "error": str(e),
            "path": path
        }


def discover_huggingface_models(cache_path: str = None) -> List[Dict[str, Any]]:
    """
    Discover HuggingFace models in the cache directory.

    Args:
        cache_path: Path to HuggingFace cache (defaults to ~/.cache/huggingface/hub)

    Returns:
        List of model dictionaries with metadata
    """
    if cache_path is None:
        cache_path = os.path.expanduser("~/.cache/huggingface/hub")

    discovery = HuggingFaceDiscovery(Path(cache_path))
    return discovery.discover()


def discover_generic_models(model_path: str) -> List[Dict[str, Any]]:
    """
    Discover GGUF models in a generic directory.

    Args:
        model_path: Path to directory containing GGUF files

    Returns:
        List of model dictionaries with metadata
    """
    discovery = GenericModelDiscovery(Path(model_path))
    return discovery.discover()


def discover_all_models(additional_paths: List[str] = None) -> List[Dict[str, Any]]:
    """
    Discover models from all configured sources.

    Args:
        additional_paths: Additional paths to scan for GGUF models

    Returns:
        Combined list of models from all sources, sorted by size
    """
    all_models = []

    # Discover HuggingFace models
    hf_models = discover_huggingface_models()
    all_models.extend(hf_models)

    # Default additional paths
    default_additional = [
        os.path.expanduser("~/.cache/models")
    ]

    # Combine default and custom paths
    paths_to_scan = default_additional + (additional_paths or [])

    # Discover models from additional paths
    for path in paths_to_scan:
        expanded_path = os.path.expanduser(path)
        if os.path.exists(expanded_path):
            generic_models = discover_generic_models(expanded_path)
            all_models.extend(generic_models)

    # Sort all models by size
    return sorted(all_models, key=lambda x: x["size"], reverse=True)
