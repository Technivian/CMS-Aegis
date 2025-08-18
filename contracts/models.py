
from django.db import models
from django.contrib.auth import get_user_model
from django.core.validators import MinValueValidator
from decimal import Decimal

User = get_user_model()


class Tag(models.Model):
    name = models.CharField(max_length=50, unique=True)

    def __str__(self):
        return self.name


class TrademarkRequest(models.Model):
    class Status(models.TextChoices):
        PENDING = 'PENDING', 'Pending'
        FILED = 'FILED', 'Filed'
        IN_REVIEW = 'IN_REVIEW', 'In Review'
        APPROVED = 'APPROVED', 'Approved'
        REJECTED = 'REJECTED', 'Rejected'

    mark_text = models.CharField(max_length=200)
    description = models.TextField()
    goods_services = models.TextField()
    filing_basis = models.CharField(max_length=100)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.mark_text


class LegalTask(models.Model):
    class Priority(models.TextChoices):
        LOW = 'LOW', 'Low'
        MEDIUM = 'MEDIUM', 'Medium'
        HIGH = 'HIGH', 'High'
        URGENT = 'URGENT', 'Urgent'

    class Status(models.TextChoices):
        PENDING = 'PENDING', 'Pending'
        IN_PROGRESS = 'IN_PROGRESS', 'In Progress'
        COMPLETED = 'COMPLETED', 'Completed'
        CANCELLED = 'CANCELLED', 'Cancelled'

    title = models.CharField(max_length=200)
    description = models.TextField()
    priority = models.CharField(max_length=10, choices=Priority.choices, default=Priority.MEDIUM)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    assigned_to = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    due_date = models.DateField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.title


class RiskLog(models.Model):
    class RiskLevel(models.TextChoices):
        LOW = 'LOW', 'Low'
        MEDIUM = 'MEDIUM', 'Medium'
        HIGH = 'HIGH', 'High'

    title = models.CharField(max_length=200)
    description = models.TextField()
    risk_level = models.CharField(max_length=10, choices=RiskLevel.choices)
    mitigation_strategy = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.title


class ComplianceChecklist(models.Model):
    class RegulationType(models.TextChoices):
        GDPR = 'GDPR', 'GDPR'
        HIPAA = 'HIPAA', 'HIPAA'
        SOX = 'SOX', 'Sarbanes-Oxley'
        PCI = 'PCI', 'PCI DSS'
        OTHER = 'OTHER', 'Other'

    title = models.CharField(max_length=200)
    description = models.TextField()
    regulation_type = models.CharField(max_length=20, choices=RegulationType.choices)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.title


class ChecklistItem(models.Model):
    checklist = models.ForeignKey(ComplianceChecklist, on_delete=models.CASCADE, related_name='items')
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    is_completed = models.BooleanField(default=False)
    order = models.PositiveIntegerField(default=1)

    class Meta:
        ordering = ['order']

    def __str__(self):
        return self.title


class WorkflowTemplate(models.Model):
    class Category(models.TextChoices):
        CONTRACT_REVIEW = 'CONTRACT_REVIEW', 'Contract Review'
        DUE_DILIGENCE = 'DUE_DILIGENCE', 'Due Diligence'
        TRADEMARK = 'TRADEMARK', 'Trademark'
        COMPLIANCE = 'COMPLIANCE', 'Compliance'
        GENERAL = 'GENERAL', 'General'

    name = models.CharField(max_length=200)
    description = models.TextField()
    category = models.CharField(max_length=30, choices=Category.choices, default=Category.GENERAL)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name


class WorkflowTemplateStep(models.Model):
    template = models.ForeignKey(WorkflowTemplate, on_delete=models.CASCADE, related_name='steps')
    title = models.CharField(max_length=200)
    description = models.TextField()
    order = models.PositiveIntegerField()
    estimated_duration_days = models.PositiveIntegerField(default=1)

    class Meta:
        ordering = ['order']

    def __str__(self):
        return f"{self.template.name} - {self.title}"


class Workflow(models.Model):
    class Status(models.TextChoices):
        ACTIVE = 'ACTIVE', 'Active'
        COMPLETED = 'COMPLETED', 'Completed'
        CANCELLED = 'CANCELLED', 'Cancelled'

    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    template = models.ForeignKey(WorkflowTemplate, on_delete=models.SET_NULL, null=True, blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.ACTIVE)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.title


class WorkflowStep(models.Model):
    class Status(models.TextChoices):
        PENDING = 'PENDING', 'Pending'
        IN_PROGRESS = 'IN_PROGRESS', 'In Progress'
        COMPLETED = 'COMPLETED', 'Completed'
        SKIPPED = 'SKIPPED', 'Skipped'

    workflow = models.ForeignKey(Workflow, on_delete=models.CASCADE, related_name='steps')
    title = models.CharField(max_length=200)
    description = models.TextField()
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    assigned_to = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    order = models.PositiveIntegerField()
    due_date = models.DateField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['order']

    def __str__(self):
        return f"{self.workflow.title} - {self.title}"


class DueDiligenceProcess(models.Model):
    class ProcessStatus(models.TextChoices):
        PLANNING = 'PLANNING', 'Planning'
        IN_PROGRESS = 'IN_PROGRESS', 'In Progress'
        REVIEW = 'REVIEW', 'Review'
        COMPLETED = 'COMPLETED', 'Completed'
        ON_HOLD = 'ON_HOLD', 'On Hold'

    class TransactionType(models.TextChoices):
        MERGER = 'MERGER', 'Merger'
        ACQUISITION = 'ACQUISITION', 'Acquisition'
        JOINT_VENTURE = 'JOINT_VENTURE', 'Joint Venture'
        ASSET_PURCHASE = 'ASSET_PURCHASE', 'Asset Purchase'

    title = models.CharField(max_length=200)
    transaction_type = models.CharField(max_length=20, choices=TransactionType.choices)
    target_company = models.CharField(max_length=200)
    deal_value = models.DecimalField(max_digits=15, decimal_places=2, null=True, blank=True)
    status = models.CharField(max_length=20, choices=ProcessStatus.choices, default=ProcessStatus.PLANNING)
    lead_attorney = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='dd_processes')
    start_date = models.DateField()
    target_completion_date = models.DateField()
    description = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f'{self.title} - {self.target_company}'


class DueDiligenceTask(models.Model):
    class TaskStatus(models.TextChoices):
        PENDING = 'PENDING', 'Pending'
        IN_PROGRESS = 'IN_PROGRESS', 'In Progress'
        COMPLETED = 'COMPLETED', 'Completed'
        BLOCKED = 'BLOCKED', 'Blocked'

    class TaskCategory(models.TextChoices):
        LEGAL = 'LEGAL', 'Legal'
        FINANCIAL = 'FINANCIAL', 'Financial'
        OPERATIONAL = 'OPERATIONAL', 'Operational'
        TECHNICAL = 'TECHNICAL', 'Technical'
        REGULATORY = 'REGULATORY', 'Regulatory'
        COMMERCIAL = 'COMMERCIAL', 'Commercial'

    process = models.ForeignKey(DueDiligenceProcess, on_delete=models.CASCADE, related_name='dd_tasks')
    title = models.CharField(max_length=200)
    category = models.CharField(max_length=20, choices=TaskCategory.choices)
    description = models.TextField(blank=True)
    assigned_to = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    status = models.CharField(max_length=20, choices=TaskStatus.choices, default=TaskStatus.PENDING)
    due_date = models.DateField()
    completion_date = models.DateField(null=True, blank=True)
    notes = models.TextField(blank=True)
    order = models.PositiveIntegerField(default=1)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['order', 'due_date']

    def __str__(self):
        return f'{self.process.title} - {self.title}'


class DueDiligenceRisk(models.Model):
    class RiskLevel(models.TextChoices):
        LOW = 'LOW', 'Low'
        MEDIUM = 'MEDIUM', 'Medium'
        HIGH = 'HIGH', 'High'

    class RiskCategory(models.TextChoices):
        LEGAL = 'LEGAL', 'Legal & Regulatory'
        FINANCIAL = 'FINANCIAL', 'Financial'
        OPERATIONAL = 'OPERATIONAL', 'Operational'
        REPUTATIONAL = 'REPUTATIONAL', 'Reputational'
        STRATEGIC = 'STRATEGIC', 'Strategic'

    process = models.ForeignKey(DueDiligenceProcess, on_delete=models.CASCADE, related_name='dd_risks')
    title = models.CharField(max_length=200)
    category = models.CharField(max_length=20, choices=RiskCategory.choices)
    description = models.TextField()
    risk_level = models.CharField(max_length=10, choices=RiskLevel.choices)
    likelihood = models.CharField(max_length=10, choices=RiskLevel.choices)
    impact = models.CharField(max_length=10, choices=RiskLevel.choices)
    mitigation_strategy = models.TextField(blank=True)
    owner = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    identified_date = models.DateField(auto_now_add=True)
    target_resolution_date = models.DateField(null=True, blank=True)
    status = models.CharField(max_length=20, default='OPEN')
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f'{self.process.title} - {self.title} ({self.risk_level})'


class Budget(models.Model):
    class Quarter(models.TextChoices):
        Q1 = 'Q1', 'Q1'
        Q2 = 'Q2', 'Q2'
        Q3 = 'Q3', 'Q3'
        Q4 = 'Q4', 'Q4'

    year = models.PositiveIntegerField()
    quarter = models.CharField(max_length=2, choices=Quarter.choices)
    department = models.CharField(max_length=100)
    allocated_amount = models.DecimalField(max_digits=12, decimal_places=2, validators=[MinValueValidator(Decimal('0'))])
    description = models.TextField(blank=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ['year', 'quarter', 'department']

    def __str__(self):
        return f'{self.department} - {self.year} {self.quarter}'

    @property
    def spent_amount(self):
        return self.expenses.aggregate(total=models.Sum('amount'))['total'] or Decimal('0')

    @property
    def remaining_amount(self):
        return self.allocated_amount - self.spent_amount

    @property
    def is_over_budget(self):
        return self.spent_amount > self.allocated_amount


class BudgetExpense(models.Model):
    class Category(models.TextChoices):
        LEGAL_FEES = 'LEGAL_FEES', 'Legal Fees'
        CONSULTING = 'CONSULTING', 'Consulting'
        SOFTWARE = 'SOFTWARE', 'Software'
        TRAVEL = 'TRAVEL', 'Travel'
        OFFICE = 'OFFICE', 'Office Supplies'
        OTHER = 'OTHER', 'Other'

    budget = models.ForeignKey(Budget, on_delete=models.CASCADE, related_name='expenses')
    description = models.CharField(max_length=200)
    amount = models.DecimalField(max_digits=10, decimal_places=2, validators=[MinValueValidator(Decimal('0'))])
    category = models.CharField(max_length=20, choices=Category.choices)
    date = models.DateField()
    receipt_url = models.URLField(blank=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f'{self.budget} - {self.description} (${self.amount})'
