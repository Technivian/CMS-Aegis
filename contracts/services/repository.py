
"""
Repository service layer for contracts
Provides abstraction between UI and data layer
"""
from django.contrib.auth.models import User
from contracts.models import Contract
from contracts.domain.contracts import ListParams, ContractData, ListResult, ContractStatus
from django.core.paginator import Paginator
from django.db.models import Q
import time
from typing import List, Optional
from contracts.tenancy import get_user_organization, scope_queryset_for_organization

def get_repository_service(user: User, use_mock: bool = False):
    """Factory function to get repository service"""
    if use_mock:
        return MockRepositoryService(user)
    else:
        return DjangoRepositoryService(user)

class RepositoryServiceInterface:
    """Interface for repository services"""
    
    def list(self, params: ListParams) -> ListResult:
        raise NotImplementedError
        
    def get_by_id(self, contract_id: str) -> Optional[ContractData]:
        raise NotImplementedError
        
    def bulk_update(self, contract_ids: List[str], updates: dict) -> int:
        raise NotImplementedError

class DjangoRepositoryService(RepositoryServiceInterface):
    """Production repository service using Django ORM"""
    
    def __init__(self, user: User):
        self.user = user
        self.organization = get_user_organization(user)
    
    def list(self, params: ListParams) -> ListResult:
        """List contracts with filtering and pagination"""
        queryset = scope_queryset_for_organization(Contract.objects.all(), self.organization)
        
        # Apply search
        if params.q:
            queryset = queryset.filter(
                Q(title__icontains=params.q) |
                Q(counterparty__icontains=params.q) |
                Q(content__icontains=params.q)
            )
        
        # Apply status filter
        if params.status:
            queryset = queryset.filter(status__in=params.status)
            
        # Apply type filter (if we had a contract_type field)
        if params.contract_type:
            # queryset = queryset.filter(contract_type__in=params.contract_type)
            pass
        
        # Apply sorting
        if params.sort == 'updated_desc':
            queryset = queryset.order_by('-updated_at')
        elif params.sort == 'updated_asc':
            queryset = queryset.order_by('updated_at')
        elif params.sort == 'title':
            queryset = queryset.order_by('title')
        elif params.sort == 'status':
            queryset = queryset.order_by('status')
            
        # Paginate
        paginator = Paginator(queryset, params.page_size)
        page_obj = paginator.get_page(params.page)
        
        # Convert to domain objects
        contracts = []
        for contract in page_obj:
            contracts.append(ContractData(
                id=str(contract.id),
                title=contract.title,
                status=contract.status,
                counterparty=getattr(contract, 'counterparty', ''),
                value=float(contract.value) if hasattr(contract, 'value') and contract.value else None,
                start_date=contract.start_date.isoformat() if hasattr(contract, 'start_date') and contract.start_date else None,
                end_date=contract.end_date.isoformat() if hasattr(contract, 'end_date') and contract.end_date else None,
                owner=contract.created_by.get_full_name() if contract.created_by else 'System',
                updated_at=contract.updated_at.isoformat() if hasattr(contract, 'updated_at') and contract.updated_at else None,
                created_at=contract.created_at.isoformat() if contract.created_at else None
            ))
        
        return ListResult(
            contracts=contracts,
            total_count=paginator.count,
            page=params.page,
            page_size=params.page_size,
            total_pages=paginator.num_pages
        )
    
    def get_by_id(self, contract_id: str) -> Optional[ContractData]:
        """Get single contract by ID"""
        try:
            queryset = scope_queryset_for_organization(Contract.objects.all(), self.organization)
            contract = queryset.get(id=contract_id)
            return ContractData(
                id=str(contract.id),
                title=contract.title,
                status=contract.status,
                counterparty=getattr(contract, 'counterparty', ''),
                value=float(contract.value) if hasattr(contract, 'value') and contract.value else None,
                start_date=contract.start_date.isoformat() if hasattr(contract, 'start_date') and contract.start_date else None,
                end_date=contract.end_date.isoformat() if hasattr(contract, 'end_date') and contract.end_date else None,
                owner=contract.created_by.get_full_name() if contract.created_by else 'System',
                updated_at=contract.updated_at.isoformat() if hasattr(contract, 'updated_at') and contract.updated_at else None,
                created_at=contract.created_at.isoformat() if contract.created_at else None,
                content=contract.content
            )
        except Contract.DoesNotExist:
            return None
    
    def bulk_update(self, contract_ids: List[str], updates: dict) -> int:
        """Bulk update contracts"""
        queryset = scope_queryset_for_organization(Contract.objects.filter(id__in=contract_ids), self.organization)
        return queryset.update(**updates)

class MockRepositoryService(RepositoryServiceInterface):
    """Mock service for testing with simulated latency"""
    
    def __init__(self, user: User):
        self.user = user
        
    def list(self, params: ListParams) -> ListResult:
        """Mock list with simulated data and latency"""
        time.sleep(0.1)  # Simulate network latency
        
        # Generate mock data
        mock_contracts = []
        for i in range(1, 26):
            mock_contracts.append(ContractData(
                id=str(i),
                title=f"Sample Contract {i}",
                status="ACTIVE" if i % 2 == 0 else "DRAFT",
                counterparty=f"Company {i}",
                value=10000.0 * i,
                start_date="2024-01-15",
                end_date="2025-01-15",
                owner="John Doe",
                updated_at="2024-01-15T10:00:00Z",
                created_at="2024-01-01T10:00:00Z"
            ))
        
        # Apply filtering (simplified)
        filtered = mock_contracts
        if params.q:
            filtered = [c for c in filtered if params.q.lower() in c.title.lower()]
        if params.status:
            filtered = [c for c in filtered if c.status in params.status]
            
        return ListResult(
            contracts=filtered,
            total_count=len(filtered),
            page=params.page,
            page_size=params.page_size,
            total_pages=(len(filtered) + params.page_size - 1) // params.page_size
        )
    
    def get_by_id(self, contract_id: str) -> Optional[ContractData]:
        """Mock get by ID"""
        time.sleep(0.05)
        return ContractData(
            id=contract_id,
            title=f"Sample Contract {contract_id}",
            status="ACTIVE",
            counterparty="Sample Company",
            value=50000.0,
            start_date="2024-01-15",
            end_date="2025-01-15",
            owner="John Doe",
            updated_at="2024-01-15T10:00:00Z",
            created_at="2024-01-01T10:00:00Z",
            content="Sample contract content..."
        )
    
    def bulk_update(self, contract_ids: List[str], updates: dict) -> int:
        """Mock bulk update"""
        time.sleep(0.2)
        return len(contract_ids)
