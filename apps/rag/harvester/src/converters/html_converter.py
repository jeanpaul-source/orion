"""HTML to Markdown converter for web documentation.

Strips navigation, ads, and non-content elements while preserving structure.

ELI5: Like extracting just the story from a webpage, throwing away all the 
buttons, menus, and decorations - keeping only the useful text.
"""

from typing import Optional, Dict
from bs4 import BeautifulSoup
import html2text
import re


class HTMLConverter:
    """Convert HTML to clean Markdown."""

    def __init__(self) -> None:
        """Initialize HTML to Markdown converter."""
        self.h2t = html2text.HTML2Text()
        self.h2t.ignore_links = False
        self.h2t.ignore_images = False
        self.h2t.ignore_emphasis = False
        self.h2t.body_width = 0  # No line wrapping
        self.h2t.unicode_snob = True
        self.h2t.skip_internal_links = True
    
    def convert(self, html_content: str, base_url: Optional[str] = None) -> str:
        """
        Convert HTML to Markdown.
        
        Args:
            html_content: Raw HTML string
            base_url: Base URL for resolving relative links
            
        Returns:
            Markdown string
        """
        # Parse with BeautifulSoup for pre-cleaning
        soup = BeautifulSoup(html_content, 'html.parser')
        
        # Remove unwanted elements
        for element in soup.find_all(['script', 'style', 'nav', 'footer', 
                                      'header', 'aside', 'iframe']):
            element.decompose()
        
        # Remove elements by class/id (common patterns)
        for selector in [
            {'class': re.compile(r'(nav|menu|sidebar|footer|header|ad|banner|cookie)', re.I)},
            {'id': re.compile(r'(nav|menu|sidebar|footer|header|ad|banner)', re.I)}
        ]:
            for element in soup.find_all(attrs=selector):
                element.decompose()
        
        # Try to find main content area
        main_content = (
            soup.find('main') or
            soup.find('article') or
            soup.find('div', class_=re.compile(r'content|main|body', re.I)) or
            soup.find('div', id=re.compile(r'content|main|body', re.I)) or
            soup.body or
            soup
        )
        
        # Convert to markdown
        if base_url:
            self.h2t.baseurl = base_url
        
        markdown = self.h2t.handle(str(main_content))
        
        # Post-process markdown
        markdown = self._clean_markdown(markdown)
        
        return markdown
    
    def _clean_markdown(self, markdown: str) -> str:
        """Clean up converted markdown."""
        # Remove excessive blank lines
        markdown = re.sub(r'\n{3,}', '\n\n', markdown)
        
        # Remove leading/trailing whitespace
        markdown = markdown.strip()
        
        # Fix malformed links [text]() with no URL
        markdown = re.sub(r'\[([^\]]+)\]\(\)', r'\1', markdown)
        
        # Remove empty emphasis
        markdown = re.sub(r'\*\*\s*\*\*', '', markdown)
        markdown = re.sub(r'__\s*__', '', markdown)
        
        return markdown
    
    def estimate_text_density(self, html_content: str) -> float:
        """
        Estimate text density (ratio of text to total content).
        
        Lower density suggests image-heavy or low-content pages.
        
        Args:
            html_content: Raw HTML string
            
        Returns:
            Text density ratio (0.0 to 1.0)
        """
        soup = BeautifulSoup(html_content, 'html.parser')
        
        # Remove script/style
        for element in soup.find_all(['script', 'style']):
            element.decompose()
        
        # Get all text
        text = soup.get_text()
        text_length = len(text.strip())
        
        # Get total HTML length
        html_length = len(html_content)
        
        if html_length == 0:
            return 0.0
        
        return min(text_length / html_length, 1.0)
    
    def extract_title(self, html_content: str) -> Optional[str]:
        """Extract page title from HTML."""
        soup = BeautifulSoup(html_content, 'html.parser')
        
        # Try multiple strategies
        title = None
        
        # 1. <title> tag
        if soup.title and soup.title.string:
            title = soup.title.string.strip()
        
        # 2. <h1> tag
        elif soup.h1:
            title = soup.h1.get_text().strip()
        
        # 3. og:title meta tag
        elif soup.find('meta', property='og:title'):
            title = soup.find('meta', property='og:title').get('content', '').strip()
        
        return title
    
    def extract_metadata(self, html_content: str) -> Dict[str, str]:
        """Extract metadata from HTML."""
        soup = BeautifulSoup(html_content, 'html.parser')
        metadata: Dict[str, str] = {}
        
        # Title
        if soup.title:
            metadata['title'] = soup.title.string.strip()
        
        # Meta description
        if soup.find('meta', attrs={'name': 'description'}):
            metadata['description'] = soup.find('meta', attrs={'name': 'description'}).get('content', '').strip()
        
        # Open Graph metadata
        for prop in ['og:title', 'og:description', 'og:type', 'og:url']:
            tag = soup.find('meta', property=prop)
            if tag:
                metadata[prop] = tag.get('content', '').strip()
        
        # Author
        if soup.find('meta', attrs={'name': 'author'}):
            metadata['author'] = soup.find('meta', attrs={'name': 'author'}).get('content', '').strip()
        
        return metadata
