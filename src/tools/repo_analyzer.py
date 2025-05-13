# Copyright (c) 2025 Bytedance Ltd. and/or its affiliates
# SPDX-License-Identifier: MIT

import logging
import os
import re
from typing import Dict, List, Optional, Any, Set, Tuple
from dataclasses import dataclass
import subprocess
from pathlib import Path

logger = logging.getLogger(__name__)

@dataclass
class FileInfo:
    """Information about a file in the repository."""
    path: str
    size: int
    last_modified: str
    content_preview: Optional[str] = None
    language: Optional[str] = None
    
    @property
    def extension(self) -> str:
        """Get the file extension."""
        return os.path.splitext(self.path)[1].lower()

@dataclass
class DirectoryInfo:
    """Information about a directory in the repository."""
    path: str
    files: List[FileInfo]
    subdirectories: List[str]
    
    @property
    def file_count(self) -> int:
        """Get the number of files in this directory."""
        return len(self.files)

@dataclass
class RepoAnalysisResult:
    """Result of repository analysis."""
    root_path: str
    directories: Dict[str, DirectoryInfo]
    languages: Dict[str, int]  # Language -> file count
    file_count: int
    directory_count: int
    readme_content: Optional[str] = None
    gitignore_patterns: List[str] = None
    dependencies: Dict[str, List[str]] = None  # Framework/language -> list of dependencies
    
    def __post_init__(self):
        if self.gitignore_patterns is None:
            self.gitignore_patterns = []
        if self.dependencies is None:
            self.dependencies = {}

class RepoAnalyzer:
    """Analyzes a repository to understand its structure and content."""
    
    def __init__(self, repo_path: str):
        """Initialize the repository analyzer.
        
        Args:
            repo_path: Path to the repository root
        """
        self.repo_path = repo_path
        self.max_file_preview_size = 1024  # 1KB preview
        self.max_files_per_dir = 50  # Limit files per directory for performance
        self.ignored_dirs = {'.git', '__pycache__', 'node_modules', 'venv', 'env', '.venv', '.env', 'dist', 'build'}
        self.ignored_extensions = {'.pyc', '.pyo', '.pyd', '.so', '.dll', '.exe', '.obj', '.o'}
        
        # Language detection by extension
        self.language_map = {
            '.py': 'Python',
            '.js': 'JavaScript',
            '.jsx': 'JavaScript (React)',
            '.ts': 'TypeScript',
            '.tsx': 'TypeScript (React)',
            '.html': 'HTML',
            '.css': 'CSS',
            '.scss': 'SCSS',
            '.java': 'Java',
            '.c': 'C',
            '.cpp': 'C++',
            '.h': 'C/C++ Header',
            '.rb': 'Ruby',
            '.go': 'Go',
            '.rs': 'Rust',
            '.php': 'PHP',
            '.swift': 'Swift',
            '.kt': 'Kotlin',
            '.md': 'Markdown',
            '.json': 'JSON',
            '.yml': 'YAML',
            '.yaml': 'YAML',
            '.toml': 'TOML',
            '.sql': 'SQL',
            '.sh': 'Shell',
            '.bat': 'Batch',
            '.ps1': 'PowerShell'
        }
    
    def analyze(self) -> RepoAnalysisResult:
        """Analyze the repository.
        
        Returns:
            RepoAnalysisResult object with analysis information
        """
        logger.info(f"Analyzing repository at {self.repo_path}")
        
        # Initialize result
        result = RepoAnalysisResult(
            root_path=self.repo_path,
            directories={},
            languages={},
            file_count=0,
            directory_count=0
        )
        
        # Parse .gitignore if it exists
        gitignore_path = os.path.join(self.repo_path, '.gitignore')
        if os.path.exists(gitignore_path):
            with open(gitignore_path, 'r') as f:
                result.gitignore_patterns = [line.strip() for line in f if line.strip() and not line.startswith('#')]
        
        # Find README
        readme_path = self._find_readme()
        if readme_path:
            with open(readme_path, 'r', encoding='utf-8', errors='replace') as f:
                result.readme_content = f.read()
        
        # Analyze dependencies
        result.dependencies = self._analyze_dependencies()
        
        # Walk the repository
        for root, dirs, files in os.walk(self.repo_path):
            # Skip ignored directories
            dirs[:] = [d for d in dirs if d not in self.ignored_dirs]
            
            # Get relative path from repo root
            rel_path = os.path.relpath(root, self.repo_path)
            if rel_path == '.':
                rel_path = ''
            
            # Create directory info
            file_infos = []
            for file in files[:self.max_files_per_dir]:  # Limit files per directory
                file_path = os.path.join(root, file)
                rel_file_path = os.path.join(rel_path, file) if rel_path else file
                
                # Skip files with ignored extensions
                ext = os.path.splitext(file)[1].lower()
                if ext in self.ignored_extensions:
                    continue
                
                try:
                    # Get file info
                    stat = os.stat(file_path)
                    
                    # Detect language
                    language = self.language_map.get(ext)
                    
                    # Update language stats
                    if language:
                        result.languages[language] = result.languages.get(language, 0) + 1
                    
                    # Get content preview for text files
                    content_preview = None
                    if self._is_text_file(file_path) and stat.st_size <= self.max_file_preview_size:
                        try:
                            with open(file_path, 'r', encoding='utf-8', errors='replace') as f:
                                content_preview = f.read(self.max_file_preview_size)
                        except Exception as e:
                            logger.warning(f"Error reading file {file_path}: {e}")
                    
                    file_info = FileInfo(
                        path=rel_file_path,
                        size=stat.st_size,
                        last_modified=self._format_timestamp(stat.st_mtime),
                        content_preview=content_preview,
                        language=language
                    )
                    file_infos.append(file_info)
                    result.file_count += 1
                except Exception as e:
                    logger.warning(f"Error processing file {file_path}: {e}")
            
            # Create directory info
            dir_info = DirectoryInfo(
                path=rel_path,
                files=file_infos,
                subdirectories=[d for d in dirs]
            )
            result.directories[rel_path] = dir_info
            result.directory_count += 1
        
        logger.info(f"Repository analysis complete: {result.file_count} files, {result.directory_count} directories")
        return result
    
    def _find_readme(self) -> Optional[str]:
        """Find the README file in the repository.
        
        Returns:
            Path to the README file, or None if not found
        """
        readme_patterns = ['README.md', 'README.txt', 'README', 'readme.md']
        for pattern in readme_patterns:
            path = os.path.join(self.repo_path, pattern)
            if os.path.exists(path):
                return path
        return None
    
    def _analyze_dependencies(self) -> Dict[str, List[str]]:
        """Analyze dependencies in the repository.
        
        Returns:
            Dictionary mapping framework/language to list of dependencies
        """
        dependencies = {}
        
        # Check for Python dependencies
        requirements_path = os.path.join(self.repo_path, 'requirements.txt')
        if os.path.exists(requirements_path):
            try:
                with open(requirements_path, 'r') as f:
                    python_deps = []
                    for line in f:
                        line = line.strip()
                        if line and not line.startswith('#'):
                            # Extract package name (remove version specifiers)
                            match = re.match(r'^([a-zA-Z0-9_.-]+)', line)
                            if match:
                                python_deps.append(match.group(1))
                    dependencies['Python'] = python_deps
            except Exception as e:
                logger.warning(f"Error parsing requirements.txt: {e}")
        
        # Check for JavaScript dependencies
        package_json_path = os.path.join(self.repo_path, 'package.json')
        if os.path.exists(package_json_path):
            try:
                import json
                with open(package_json_path, 'r') as f:
                    package_data = json.load(f)
                    js_deps = []
                    
                    # Regular dependencies
                    if 'dependencies' in package_data:
                        js_deps.extend(package_data['dependencies'].keys())
                    
                    # Dev dependencies
                    if 'devDependencies' in package_data:
                        js_deps.extend(package_data['devDependencies'].keys())
                    
                    dependencies['JavaScript'] = js_deps
            except Exception as e:
                logger.warning(f"Error parsing package.json: {e}")
        
        return dependencies
    
    def _is_text_file(self, file_path: str) -> bool:
        """Check if a file is a text file.
        
        Args:
            file_path: Path to the file
            
        Returns:
            True if the file is a text file, False otherwise
        """
        # Simple check based on extension
        ext = os.path.splitext(file_path)[1].lower()
        text_extensions = {
            '.txt', '.md', '.py', '.js', '.jsx', '.ts', '.tsx', '.html', '.css', '.scss',
            '.java', '.c', '.cpp', '.h', '.rb', '.go', '.rs', '.php', '.swift', '.kt',
            '.json', '.yml', '.yaml', '.toml', '.sql', '.sh', '.bat', '.ps1', '.xml',
            '.csv', '.ini', '.cfg', '.conf', '.properties'
        }
        
        if ext in text_extensions:
            return True
        
        # For other files, try to read the first few bytes
        try:
            with open(file_path, 'rb') as f:
                data = f.read(1024)
                # Check for null bytes (common in binary files)
                if b'\x00' in data:
                    return False
                # Try to decode as UTF-8
                try:
                    data.decode('utf-8')
                    return True
                except UnicodeDecodeError:
                    return False
        except Exception:
            return False
    
    def _format_timestamp(self, timestamp: float) -> str:
        """Format a timestamp as a human-readable string.
        
        Args:
            timestamp: Unix timestamp
            
        Returns:
            Formatted timestamp string
        """
        from datetime import datetime
        dt = datetime.fromtimestamp(timestamp)
        return dt.strftime('%Y-%m-%d %H:%M:%S')
    
    @staticmethod
    def get_git_info(repo_path: str) -> Dict[str, Any]:
        """Get Git information for the repository.
        
        Args:
            repo_path: Path to the repository
            
        Returns:
            Dictionary with Git information
        """
        git_info = {
            'current_branch': None,
            'remote_url': None,
            'last_commit': None,
            'uncommitted_changes': False
        }
        
        try:
            # Get current branch
            result = subprocess.run(
                ['git', 'rev-parse', '--abbrev-ref', 'HEAD'],
                cwd=repo_path,
                capture_output=True,
                text=True,
                check=True
            )
            git_info['current_branch'] = result.stdout.strip()
            
            # Get remote URL
            result = subprocess.run(
                ['git', 'config', '--get', 'remote.origin.url'],
                cwd=repo_path,
                capture_output=True,
                text=True,
                check=True
            )
            git_info['remote_url'] = result.stdout.strip()
            
            # Get last commit info
            result = subprocess.run(
                ['git', 'log', '-1', '--pretty=format:%h|%an|%ad|%s'],
                cwd=repo_path,
                capture_output=True,
                text=True,
                check=True
            )
            if result.stdout:
                parts = result.stdout.strip().split('|', 3)
                if len(parts) == 4:
                    git_info['last_commit'] = {
                        'hash': parts[0],
                        'author': parts[1],
                        'date': parts[2],
                        'message': parts[3]
                    }
            
            # Check for uncommitted changes
            result = subprocess.run(
                ['git', 'status', '--porcelain'],
                cwd=repo_path,
                capture_output=True,
                text=True,
                check=True
            )
            git_info['uncommitted_changes'] = bool(result.stdout.strip())
            
        except subprocess.CalledProcessError as e:
            logger.warning(f"Error getting Git information: {e}")
        except Exception as e:
            logger.warning(f"Unexpected error getting Git information: {e}")
        
        return git_info
