
"""
Template service for managing contract templates
"""
from typing import List, Dict, Optional
from datetime import datetime
import uuid
from config.feature_flags import is_test_mode

class Template:
    def __init__(self, id: str, title: str, content: str, category: str = "general", 
                 created_by: str = "", created_at: str = "", tags: List[str] = None):
        self.id = id
        self.title = title
        self.content = content
        self.category = category
        self.created_by = created_by
        self.created_at = created_at or datetime.now().isoformat()
        self.tags = tags or []

class TemplateService:
    def __init__(self):
        self._templates = self._get_mock_templates() if is_test_mode() else {}
    
    def _get_mock_templates(self) -> Dict[str, Template]:
        """Generate mock template data for testing"""
        mock_templates = [
            Template("tpl-1", "Software License Agreement", 
                    "This Software License Agreement...", "licensing",
                    "admin", tags=["software", "licensing"]),
            Template("tpl-2", "Service Agreement", 
                    "This Service Agreement outlines...", "services",
                    "admin", tags=["services", "general"]),
            Template("tpl-3", "NDA Template", 
                    "This Non-Disclosure Agreement...", "confidentiality",
                    "admin", tags=["nda", "confidentiality"]),
            Template("tpl-4", "Employment Contract", 
                    "This Employment Contract establishes...", "employment",
                    "admin", tags=["employment", "hr"]),
        ]
        return {template.id: template for template in mock_templates}
    
    def list_templates(self, category: Optional[str] = None, 
                      tags: List[str] = None) -> List[Template]:
        """List all templates with optional filtering"""
        templates = list(self._templates.values())
        
        if category:
            templates = [t for t in templates if t.category == category]
        
        if tags:
            templates = [t for t in templates if any(tag in t.tags for tag in tags)]
        
        return sorted(templates, key=lambda t: t.created_at, reverse=True)
    
    def get_template(self, template_id: str) -> Optional[Template]:
        """Get a specific template by ID"""
        return self._templates.get(template_id)
    
    def create_template(self, title: str, content: str, category: str = "general",
                       tags: List[str] = None) -> Template:
        """Create a new template"""
        template_id = f"tpl-{uuid.uuid4().hex[:8]}"
        template = Template(template_id, title, content, category, 
                          "current_user", tags=tags or [])
        self._templates[template_id] = template
        return template
    
    def update_template(self, template_id: str, **kwargs) -> Optional[Template]:
        """Update an existing template"""
        template = self._templates.get(template_id)
        if not template:
            return None
        
        for key, value in kwargs.items():
            if hasattr(template, key):
                setattr(template, key, value)
        
        return template
    
    def delete_template(self, template_id: str) -> bool:
        """Delete a template"""
        if template_id in self._templates:
            del self._templates[template_id]
            return True
        return False

# Global service instance
template_service = TemplateService()
