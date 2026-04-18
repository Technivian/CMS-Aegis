
"""
Domain classes for contract repository
These classes define the data structures independent of Django models
"""
from dataclasses import dataclass, asdict
from typing import List, Optional
from enum import Enum

class ContractStatus(Enum):
    DRAFT = "DRAFT"
    ACTIVE = "ACTIVE" 
    EXPIRED = "EXPIRED"
    TERMINATED = "TERMINATED"

@dataclass
class ListParams:
    """Parameters for contract listing"""
    q: str = ""
    status: List[str] = None
    contract_type: List[str] = None
    sort: str = "updated_desc"
    page: int = 1
    page_size: int = 25
    
    def __post_init__(self):
        if self.status is None:
            self.status = []
        if self.contract_type is None:
            self.contract_type = []

@dataclass
class ContractData:
    """Contract data transfer object"""
    id: str
    title: str
    status: str
    counterparty: str = ""
    value: Optional[float] = None
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    owner: str = ""
    updated_at: Optional[str] = None
    created_at: Optional[str] = None
    content: str = ""
    
    def to_dict(self):
        """Convert to dictionary for JSON serialization"""
        return asdict(self)


@dataclass
class CareCaseData(ContractData):
    """Backward-compatible care case DTO used by legacy API views."""
    preferred_provider: str = ""

@dataclass
class ListResult:
    """Result of contract listing operation"""
    contracts: List[ContractData]
    total_count: int
    page: int
    page_size: int
    total_pages: int
    
    def to_dict(self):
        """Convert to dictionary for JSON serialization"""
        return {
            'contracts': [c.to_dict() for c in self.contracts],
            'total_count': self.total_count,
            'page': self.page,
            'page_size': self.page_size,
            'total_pages': self.total_pages
        }
