
"""
Obligations service for tracking contract obligations and key dates
"""
from typing import List, Dict, Optional
from datetime import datetime, date, timedelta
import uuid
from config.feature_flags import is_test_mode

class Obligation:
    def __init__(self, id: str, title: str, description: str, due_date: str,
                 contract_id: str, assigned_to: str = "", priority: str = "medium",
                 status: str = "pending", reminder_days: int = 7):
        self.id = id
        self.title = title
        self.description = description
        self.due_date = due_date
        self.contract_id = contract_id
        self.assigned_to = assigned_to
        self.priority = priority  # low, medium, high, critical
        self.status = status  # pending, in_progress, completed, overdue
        self.reminder_days = reminder_days
        self.created_at = datetime.now().isoformat()

class ObligationService:
    def __init__(self):
        self._obligations = self._get_mock_obligations() if is_test_mode() else {}
    
    def _get_mock_obligations(self) -> Dict[str, Obligation]:
        """Generate mock obligation data for testing"""
        today = date.today()
        mock_obligations = [
            Obligation("obl-1", "Contract Renewal Review", 
                      "Review terms for annual renewal", 
                      (today + timedelta(days=30)).isoformat(),
                      "contract-1", "admin", "high"),
            Obligation("obl-2", "Insurance Certificate Update", 
                      "Obtain updated insurance certificate", 
                      (today + timedelta(days=15)).isoformat(),
                      "contract-2", "admin", "medium"),
            Obligation("obl-3", "Performance Review", 
                      "Quarterly performance review meeting", 
                      (today + timedelta(days=7)).isoformat(),
                      "contract-3", "admin", "medium"),
            Obligation("obl-4", "Payment Due", 
                      "Monthly service fee payment", 
                      (today + timedelta(days=3)).isoformat(),
                      "contract-1", "admin", "high"),
            Obligation("obl-5", "Compliance Audit", 
                      "Annual compliance audit required", 
                      (today - timedelta(days=5)).isoformat(),
                      "contract-4", "admin", "critical", "overdue"),
        ]
        return {obligation.id: obligation for obligation in mock_obligations}
    
    def list_obligations(self, contract_id: Optional[str] = None,
                        assigned_to: Optional[str] = None,
                        status: Optional[str] = None) -> List[Obligation]:
        """List obligations with optional filtering"""
        obligations = list(self._obligations.values())
        
        if contract_id:
            obligations = [o for o in obligations if o.contract_id == contract_id]
        
        if assigned_to:
            obligations = [o for o in obligations if o.assigned_to == assigned_to]
        
        if status:
            obligations = [o for o in obligations if o.status == status]
        
        # Update overdue status
        today = date.today().isoformat()
        for obligation in obligations:
            if obligation.due_date < today and obligation.status == "pending":
                obligation.status = "overdue"
        
        return sorted(obligations, key=lambda o: o.due_date)
    
    def get_upcoming_obligations(self, days_ahead: int = 30) -> List[Obligation]:
        """Get obligations due within specified days"""
        cutoff_date = (date.today() + timedelta(days=days_ahead)).isoformat()
        today = date.today().isoformat()
        
        obligations = [o for o in self._obligations.values() 
                      if today <= o.due_date <= cutoff_date]
        
        return sorted(obligations, key=lambda o: o.due_date)
    
    def get_overdue_obligations(self) -> List[Obligation]:
        """Get all overdue obligations"""
        today = date.today().isoformat()
        obligations = [o for o in self._obligations.values() 
                      if o.due_date < today and o.status in ["pending", "in_progress"]]
        
        for obligation in obligations:
            obligation.status = "overdue"
        
        return sorted(obligations, key=lambda o: o.due_date)
    
    def create_obligation(self, title: str, description: str, due_date: str,
                         contract_id: str, assigned_to: str = "", 
                         priority: str = "medium") -> Obligation:
        """Create a new obligation"""
        obligation_id = f"obl-{uuid.uuid4().hex[:8]}"
        obligation = Obligation(obligation_id, title, description, due_date,
                              contract_id, assigned_to, priority)
        self._obligations[obligation_id] = obligation
        return obligation
    
    def update_obligation(self, obligation_id: str, **kwargs) -> Optional[Obligation]:
        """Update an existing obligation"""
        obligation = self._obligations.get(obligation_id)
        if not obligation:
            return None
        
        for key, value in kwargs.items():
            if hasattr(obligation, key):
                setattr(obligation, key, value)
        
        return obligation
    
    def get_dashboard_timeline(self, days_ahead: int = 60) -> List[Obligation]:
        """Get obligations for dashboard timeline view"""
        return self.get_upcoming_obligations(days_ahead)

# Global service instance
obligation_service = ObligationService()
