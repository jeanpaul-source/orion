"""
Tests for GitHub provider.

Run with: pytest tests/test_github_provider.py -v
"""

import sys
from pathlib import Path
import pytest
from unittest.mock import Mock, patch, MagicMock

# Add src/ to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from providers.github import GitHubProvider


class TestGitHubProvider:
    """Test GitHub provider functionality"""

    @patch('providers.github.Github')
    def test_github_provider_initialization(self, mock_github_class):
        """GitHub provider should initialize with token"""
        mock_github_instance = Mock()
        mock_github_class.return_value = mock_github_instance

        provider = GitHubProvider(token="test_token")

        assert provider is not None
        assert provider.token == "test_token"
        mock_github_class.assert_called_once_with("test_token")

    @patch('providers.github.Github')
    def test_github_provider_requires_token(self, mock_github_class):
        """GitHub provider should require token"""
        # Mock environment variable not set
        with patch.dict('os.environ', {}, clear=True):
            with pytest.raises(ValueError, match="GitHub token required"):
                GitHubProvider()

    def test_get_provider_name(self):
        """Provider name should be 'github'"""
        with patch('providers.github.Github'):
            provider = GitHubProvider(token="test")
            assert provider.get_provider_name() == "github"

    def test_get_provider_type(self):
        """Provider type should be 'documentation'"""
        with patch('providers.github.Github'):
            provider = GitHubProvider(token="test")
            assert provider.get_provider_type() == "documentation"

    @patch('providers.github.Github')
    def test_discover_starred_repos(self, mock_github_class):
        """Should discover starred repositories"""
        # Setup mocks
        mock_github = Mock()
        mock_github_class.return_value = mock_github

        mock_user = Mock()
        mock_repo1 = Mock()
        mock_repo1.full_name = "owner1/repo1"
        mock_repo2 = Mock()
        mock_repo2.full_name = "owner2/repo2"

        mock_user.get_starred.return_value = [mock_repo1, mock_repo2]
        mock_github.get_user.return_value = mock_user

        # Create provider and discover
        provider = GitHubProvider(token="test", starred=True)
        repos = provider.discover()

        assert len(repos) == 2
        assert "owner1/repo1" in repos
        assert "owner2/repo2" in repos

    @patch('providers.github.Github')
    def test_discover_manual_repo_list(self, mock_github_class):
        """Should use manually provided repo list"""
        mock_github = Mock()
        mock_github_class.return_value = mock_github

        repo_list = ["test/repo1", "test/repo2"]
        provider = GitHubProvider(token="test", repo_list=repo_list)

        repos = provider.discover()

        assert len(repos) == 2
        assert "test/repo1" in repos
        assert "test/repo2" in repos

    @patch('providers.github.Github')
    def test_fetch_readme(self, mock_github_class):
        """Should fetch README from repository"""
        # Setup mocks
        mock_github = Mock()
        mock_github_class.return_value = mock_github

        mock_repo = Mock()
        mock_repo.name = "test-repo"
        mock_repo.full_name = "owner/test-repo"
        mock_repo.html_url = "https://github.com/owner/test-repo"
        mock_repo.description = "Test repository"
        mock_repo.stargazers_count = 100
        mock_repo.language = "Python"
        mock_repo.get_topics.return_value = ["python", "testing"]
        mock_repo.created_at = None
        mock_repo.updated_at = None

        mock_readme = Mock()
        mock_readme.decoded_content = b"# Test README\n\nThis is a test."
        mock_readme.html_url = "https://github.com/owner/test-repo/blob/main/README.md"

        mock_repo.get_readme.return_value = mock_readme
        mock_github.get_repo.return_value = mock_repo

        # Create provider and fetch
        provider = GitHubProvider(token="test")
        doc = provider.fetch("owner/test-repo")

        assert doc is not None
        assert doc.title in ["# Test README", "test-repo"]  # Either extracted title or repo name
        assert b"test" in doc.raw_content.lower()
        assert doc.source_provider == "github"
        assert doc.metadata["repo_name"] == "test-repo"
        assert doc.metadata["stars"] == 100

    @patch('providers.github.Github')
    def test_fetch_no_readme(self, mock_github_class):
        """Should return None when README doesn't exist"""
        # Setup mocks
        mock_github = Mock()
        mock_github_class.return_value = mock_github

        mock_repo = Mock()
        from providers.github import GithubException
        mock_repo.get_readme.side_effect = GithubException(404, "Not found")

        mock_github.get_repo.return_value = mock_repo

        # Create provider and fetch
        provider = GitHubProvider(token="test")
        doc = provider.fetch("owner/no-readme")

        assert doc is None

    @patch('providers.github.Github')
    def test_rate_limit_status(self, mock_github_class):
        """Should return rate limit status"""
        # Setup mocks
        mock_github = Mock()
        mock_github_class.return_value = mock_github

        mock_rate_limit = Mock()
        mock_core = Mock()
        mock_core.remaining = 4500
        mock_core.limit = 5000
        mock_core.reset = Mock()
        mock_core.reset.isoformat.return_value = "2024-01-01T12:00:00"

        mock_search = Mock()
        mock_search.remaining = 25
        mock_search.limit = 30
        mock_search.reset = Mock()
        mock_search.reset.isoformat.return_value = "2024-01-01T12:00:00"

        mock_rate_limit.core = mock_core
        mock_rate_limit.search = mock_search
        mock_github.get_rate_limit.return_value = mock_rate_limit

        # Create provider and check rate limit
        provider = GitHubProvider(token="test")
        status = provider.get_rate_limit_status()

        assert status["core"]["remaining"] == 4500
        assert status["core"]["limit"] == 5000
        assert status["search"]["remaining"] == 25
