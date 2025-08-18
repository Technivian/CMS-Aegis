
"""
Clause library service for managing reusable contract clauses
"""
from typing import List, Dict, Optional
from datetime import datetime
import uuid
from config.feature_flags import is_test_mode

class Clause:
    def __init__(self, id: str, title: str, content: str, category: str = "general",
                 tags: List[str] = None, version: str = "1.0", created_by: str = ""):
        self.id = id
        self.title = title
        self.content = content
        self.category = category
        self.tags = tags or []
        self.version = version
        self.created_by = created_by
        self.created_at = datetime.now().isoformat()

class ClauseService:
    def __init__(self):
        self._clauses = self._get_mock_clauses() if is_test_mode() else {}
    
    def _get_mock_clauses(self) -> Dict[str, Clause]:
        """Generate mock clause data for testing"""
        mock_clauses = [
            Clause("cls-1", "Limitation of Liability", 
                  "IN NO EVENT SHALL THE COMPANY BE LIABLE...", "liability",
                  tags=["liability", "protection"]),
            Clause("cls-2", "Force Majeure", 
                  "Neither party shall be liable for any delay...", "general",
                  tags=["force-majeure", "delays"]),
            Clause("cls-3", "Confidentiality", 
                  "Each party acknowledges that it may receive...", "confidentiality",
                  tags=["confidentiality", "nda"]),
            Clause("cls-4", "Termination", 
                  "This agreement may be terminated by either party...", "termination",
                  tags=["termination", "cancellation"]),
            Clause("cls-5", "Intellectual Property", 
                  "All intellectual property rights in...", "ip",
                  tags=["ip", "ownership"]),
        ]
        return {clause.id: clause for clause in mock_clauses}
    
    def search_clauses(self, query: str = "", category: Optional[str] = None,
                      tags: List[str] = None) -> List[Clause]:
        """Search clauses by content, category, or tags"""
        clauses = list(self._clauses.values())
        
        if query:
            query_lower = query.lower()
            clauses = [c for c in clauses 
                      if query_lower in c.title.lower() or query_lower in c.content.lower()]
        
        if category:
            clauses = [c for c in clauses if c.category == category]
        
        if tags:
            clauses = [c for c in clauses if any(tag in c.tags for tag in tags)]
        
        return sorted(clauses, key=lambda c: c.created_at, reverse=True)
    
    def get_clause(self, clause_id: str) -> Optional[Clause]:
        """Get a specific clause by ID"""
        return self._clauses.get(clause_id)
    
    def create_clause(self, title: str, content: str, category: str = "general",
                     tags: List[str] = None) -> Clause:
        """Create a new clause"""
        clause_id = f"cls-{uuid.uuid4().hex[:8]}"
        clause = Clause(clause_id, title, content, category, tags=tags or [])
        self._clauses[clause_id] = clause
        return clause
    
    def get_categories(self) -> List[str]:
        """Get all unique clause categories"""
        return list(set(clause.category for clause in self._clauses.values()))
    
    def get_all_tags(self) -> List[str]:
        """Get all unique tags used in clauses"""
        all_tags = set()
        for clause in self._clauses.values():
            all_tags.update(clause.tags)
        return sorted(list(all_tags))

# Global service instance
clause_service = ClauseService()
