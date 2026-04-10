from django.db import models
from django.contrib.auth import get_user_model
from django.core.validators import MinValueValidator
from django.utils import timezone
from decimal import Decimal
from datetime import date
import uuid
import os

User = get_user_model()


def document_upload_path(instance, filename):
    return f'documents/{instance.matter.id if instance.matter else "general"}/{filename}'


class Organization(models.Model):
    name = models.CharField(max_length=200, unique=True)
    slug = models.SlugField(max_length=120, unique=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return self.name


class OrganizationMembership(models.Model):
    class Role(models.TextChoices):
        OWNER = 'OWNER', 'Owner'
        ADMIN = 'ADMIN', 'Admin'
        MEMBER = 'MEMBER', 'Member'

    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name='memberships')
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='organization_memberships')
    role = models.CharField(max_length=20, choices=Role.choices, default=Role.MEMBER)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('organization', 'user')
        ordering = ['organization__name', 'user__username']

    def __str__(self):
        return f'{self.user.username} @ {self.organization.name} ({self.role})'


class OrganizationInvitation(models.Model):
    class Status(models.TextChoices):
        PENDING = 'PENDING', 'Pending'
        ACCEPTED = 'ACCEPTED', 'Accepted'
        REVOKED = 'REVOKED', 'Revoked'
        EXPIRED = 'EXPIRED', 'Expired'

    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name='invitations')
    email = models.EmailField()
    role = models.CharField(max_length=20, choices=OrganizationMembership.Role.choices, default=OrganizationMembership.Role.MEMBER)
    token = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    invited_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='sent_organization_invitations')
    invited_user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='accepted_organization_invitations')
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    expires_at = models.DateTimeField(null=True, blank=True)
    accepted_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['organization', 'status']),
            models.Index(fields=['email', 'status']),
        ]

    def __str__(self):
        return f'Invite {self.email} to {self.organization.name} ({self.get_status_display()})'


class UserProfile(models.Model):
    class Role(models.TextChoices):
        PARTNER = 'PARTNER', 'Partner'
        SENIOR_ASSOCIATE = 'SENIOR_ASSOCIATE', 'Senior Associate'
        ASSOCIATE = 'ASSOCIATE', 'Associate'
        PARALEGAL = 'PARALEGAL', 'Paralegal'
        LEGAL_ASSISTANT = 'LEGAL_ASSISTANT', 'Legal Assistant'
        ADMIN = 'ADMIN', 'Administrator'
        CLIENT = 'CLIENT', 'Client'

    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profile')
    role = models.CharField(max_length=20, choices=Role.choices, default=Role.ASSOCIATE)
    phone = models.CharField(max_length=20, blank=True)
    bar_number = models.CharField(max_length=50, blank=True)
    department = models.CharField(max_length=100, blank=True)
    hourly_rate = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True)
    bio = models.TextField(blank=True)
    avatar = models.ImageField(upload_to='avatars/', blank=True, null=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f'{self.user.get_full_name() or self.user.username} ({self.get_role_display()})'

    @property
    def can_approve(self):
        return self.role in [self.Role.PARTNER, self.Role.SENIOR_ASSOCIATE, self.Role.ADMIN]

    @property
    def is_attorney(self):
        return self.role in [self.Role.PARTNER, self.Role.SENIOR_ASSOCIATE, self.Role.ASSOCIATE]


class Client(models.Model):
    class ClientType(models.TextChoices):
        INDIVIDUAL = 'INDIVIDUAL', 'Individual'
        CORPORATION = 'CORPORATION', 'Corporation'
        LLC = 'LLC', 'LLC'
        PARTNERSHIP = 'PARTNERSHIP', 'Partnership'
        GOVERNMENT = 'GOVERNMENT', 'Government Entity'
        NON_PROFIT = 'NON_PROFIT', 'Non-Profit'
        OTHER = 'OTHER', 'Other'

    class Status(models.TextChoices):
        ACTIVE = 'ACTIVE', 'Active'
        INACTIVE = 'INACTIVE', 'Inactive'
        PROSPECTIVE = 'PROSPECTIVE', 'Prospective'
        FORMER = 'FORMER', 'Former'

    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, null=True, blank=True, related_name='clients')
    name = models.CharField(max_length=200)
    client_type = models.CharField(max_length=20, choices=ClientType.choices, default=ClientType.INDIVIDUAL)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.ACTIVE)
    email = models.EmailField(blank=True)
    phone = models.CharField(max_length=20, blank=True)
    address = models.TextField(blank=True)
    city = models.CharField(max_length=100, blank=True)
    state = models.CharField(max_length=100, blank=True)
    zip_code = models.CharField(max_length=20, blank=True)
    country = models.CharField(max_length=100, default='United States')
    tax_id = models.CharField(max_length=50, blank=True)
    website = models.URLField(blank=True)
    industry = models.CharField(max_length=100, blank=True)
    notes = models.TextField(blank=True)
    primary_contact = models.CharField(max_length=200, blank=True)
    primary_contact_email = models.EmailField(blank=True)
    primary_contact_phone = models.CharField(max_length=20, blank=True)
    responsible_attorney = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='responsible_clients')
    originating_attorney = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='originated_clients')
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='created_clients')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.name

    @property
    def total_billed(self):
        return self.invoices.aggregate(total=models.Sum('total_amount'))['total'] or Decimal('0')

    @property
    def outstanding_balance(self):
        return self.invoices.filter(status__in=['SENT', 'OVERDUE']).aggregate(
            total=models.Sum('total_amount'))['total'] or Decimal('0')

    @property
    def active_matters_count(self):
        return self.matters.filter(status='ACTIVE').count()


class Matter(models.Model):
    class Status(models.TextChoices):
        ACTIVE = 'ACTIVE', 'Active'
        PENDING = 'PENDING', 'Pending'
        CLOSED = 'CLOSED', 'Closed'
        ON_HOLD = 'ON_HOLD', 'On Hold'

    class PracticeArea(models.TextChoices):
        CORPORATE = 'CORPORATE', 'Corporate'
        LITIGATION = 'LITIGATION', 'Litigation'
        IP = 'IP', 'Intellectual Property'
        REAL_ESTATE = 'REAL_ESTATE', 'Real Estate'
        EMPLOYMENT = 'EMPLOYMENT', 'Employment'
        TAX = 'TAX', 'Tax'
        REGULATORY = 'REGULATORY', 'Regulatory'
        FAMILY = 'FAMILY', 'Family Law'
        CRIMINAL = 'CRIMINAL', 'Criminal Defense'
        BANKRUPTCY = 'BANKRUPTCY', 'Bankruptcy'
        IMMIGRATION = 'IMMIGRATION', 'Immigration'
        ESTATE = 'ESTATE', 'Estate Planning'
        ENVIRONMENTAL = 'ENVIRONMENTAL', 'Environmental'
        OTHER = 'OTHER', 'Other'

    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, null=True, blank=True, related_name='matters')
    matter_number = models.CharField(max_length=50, unique=True)
    title = models.CharField(max_length=300)
    description = models.TextField(blank=True)
    client = models.ForeignKey(Client, on_delete=models.CASCADE, related_name='matters')
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.ACTIVE)
    practice_area = models.CharField(max_length=20, choices=PracticeArea.choices, default=PracticeArea.CORPORATE)
    responsible_attorney = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='responsible_matters')
    originating_attorney = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='originated_matters')
    team_members = models.ManyToManyField(User, blank=True, related_name='matter_team')
    open_date = models.DateField(default=date.today)
    close_date = models.DateField(null=True, blank=True)
    statute_of_limitations = models.DateField(null=True, blank=True)
    court_name = models.CharField(max_length=200, blank=True)
    case_number = models.CharField(max_length=100, blank=True)
    opposing_party = models.CharField(max_length=200, blank=True)
    opposing_counsel = models.CharField(max_length=200, blank=True)
    billing_type = models.CharField(max_length=20, choices=[
        ('HOURLY', 'Hourly'),
        ('FLAT_FEE', 'Flat Fee'),
        ('CONTINGENCY', 'Contingency'),
        ('RETAINER', 'Retainer'),
        ('PRO_BONO', 'Pro Bono'),
    ], default='HOURLY')
    budget_amount = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    notes = models.TextField(blank=True)
    is_confidential = models.BooleanField(default=False)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='created_matters')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f'{self.matter_number} - {self.title}'

    def save(self, *args, **kwargs):
        if not self.matter_number:
            last = Matter.objects.order_by('-id').first()
            next_num = (last.id + 1) if last else 1
            self.matter_number = f'MTR-{next_num:05d}'
        super().save(*args, **kwargs)

    @property
    def total_time_billed(self):
        entries = self.time_entries.filter(is_billable=True)
        total = sum(e.hours for e in entries)
        return total

    @property
    def total_amount_billed(self):
        entries = self.time_entries.filter(is_billable=True)
        total = sum(e.total_amount for e in entries)
        return total


class Contract(models.Model):
    class Status(models.TextChoices):
        DRAFT = 'DRAFT', 'Draft'
        PENDING = 'PENDING', 'Pending'
        IN_REVIEW = 'IN_REVIEW', 'In Review'
        APPROVED = 'APPROVED', 'Approved'
        ACTIVE = 'ACTIVE', 'Active'
        EXPIRED = 'EXPIRED', 'Expired'
        TERMINATED = 'TERMINATED', 'Terminated'
        COMPLETED = 'COMPLETED', 'Completed'
        CANCELLED = 'CANCELLED', 'Cancelled'

    class ContractType(models.TextChoices):
        NDA = 'NDA', 'Non-Disclosure Agreement'
        MSA = 'MSA', 'Master Service Agreement'
        SOW = 'SOW', 'Statement of Work'
        EMPLOYMENT = 'EMPLOYMENT', 'Employment Agreement'
        LEASE = 'LEASE', 'Lease Agreement'
        LICENSE = 'LICENSE', 'License Agreement'
        VENDOR = 'VENDOR', 'Vendor Agreement'
        PARTNERSHIP = 'PARTNERSHIP', 'Partnership Agreement'
        SETTLEMENT = 'SETTLEMENT', 'Settlement Agreement'
        AMENDMENT = 'AMENDMENT', 'Amendment'
        OTHER = 'OTHER', 'Other'

    class RiskLevel(models.TextChoices):
        LOW = 'LOW', 'Low'
        MEDIUM = 'MEDIUM', 'Medium'
        HIGH = 'HIGH', 'High'
        CRITICAL = 'CRITICAL', 'Critical'

    class Currency(models.TextChoices):
        USD = 'USD', 'USD ($)'
        EUR = 'EUR', 'EUR (€)'
        GBP = 'GBP', 'GBP (£)'
        CHF = 'CHF', 'CHF (Fr)'
        CAD = 'CAD', 'CAD (C$)'
        AUD = 'AUD', 'AUD (A$)'
        OTHER = 'OTHER', 'Other'

    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, null=True, blank=True, related_name='contracts')
    title = models.CharField(max_length=200)
    contract_type = models.CharField(max_length=20, choices=ContractType.choices, default=ContractType.OTHER)
    content = models.TextField(blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.DRAFT)
    counterparty = models.CharField(max_length=200, blank=True)
    value = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    currency = models.CharField(max_length=5, choices=Currency.choices, default=Currency.USD)
    governing_law = models.CharField(max_length=200, blank=True, help_text='Governing law jurisdiction')
    jurisdiction = models.CharField(max_length=200, blank=True, help_text='Contract jurisdiction')
    language = models.CharField(max_length=50, default='English', blank=True)
    risk_level = models.CharField(max_length=10, choices=RiskLevel.choices, default=RiskLevel.LOW)
    data_transfer_flag = models.BooleanField(default=False, help_text='Involves cross-border data transfer (EU/US)')
    dpa_attached = models.BooleanField(default=False, help_text='Data Processing Agreement attached')
    scc_attached = models.BooleanField(default=False, help_text='Standard Contractual Clauses attached')
    start_date = models.DateField(null=True, blank=True)
    end_date = models.DateField(null=True, blank=True)
    renewal_date = models.DateField(null=True, blank=True)
    auto_renew = models.BooleanField(default=False)
    notice_period_days = models.PositiveIntegerField(null=True, blank=True)
    termination_notice_date = models.DateField(null=True, blank=True)
    lifecycle_stage = models.CharField(max_length=20, choices=[
        ('DRAFTING', 'Drafting'),
        ('INTERNAL_REVIEW', 'Internal Review'),
        ('NEGOTIATION', 'Negotiation'),
        ('APPROVAL', 'Approval'),
        ('SIGNATURE', 'Signature'),
        ('EXECUTED', 'Executed'),
        ('OBLIGATION_TRACKING', 'Obligation Tracking'),
        ('RENEWAL', 'Renewal/Termination'),
        ('ARCHIVED', 'Archived'),
    ], default='DRAFTING')
    client = models.ForeignKey('Client', on_delete=models.SET_NULL, null=True, blank=True, related_name='contracts')
    matter = models.ForeignKey('Matter', on_delete=models.SET_NULL, null=True, blank=True, related_name='contracts')
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    approved_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='approved_contracts')
    approved_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.title

    @property
    def is_expiring_soon(self):
        if self.end_date and self.status == 'ACTIVE':
            days_until = (self.end_date - date.today()).days
            return 0 <= days_until <= 30
        return False

    @property
    def days_until_expiry(self):
        if self.end_date:
            return (self.end_date - date.today()).days
        return None


class Document(models.Model):
    class DocType(models.TextChoices):
        CONTRACT = 'CONTRACT', 'Contract Document'
        AMENDMENT = 'AMENDMENT', 'Amendment'
        EXHIBIT = 'EXHIBIT', 'Exhibit/Attachment'
        CORRESPONDENCE = 'CORRESPONDENCE', 'Correspondence'
        COURT_FILING = 'COURT_FILING', 'Court Filing'
        PLEADING = 'PLEADING', 'Pleading'
        DISCOVERY = 'DISCOVERY', 'Discovery'
        MEMO = 'MEMO', 'Memorandum'
        RESEARCH = 'RESEARCH', 'Legal Research'
        INVOICE = 'INVOICE', 'Invoice'
        TEMPLATE = 'TEMPLATE', 'Template'
        OTHER = 'OTHER', 'Other'

    class Status(models.TextChoices):
        DRAFT = 'DRAFT', 'Draft'
        REVIEW = 'REVIEW', 'Under Review'
        APPROVED = 'APPROVED', 'Approved'
        FINAL = 'FINAL', 'Final'
        ARCHIVED = 'ARCHIVED', 'Archived'

    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, null=True, blank=True, related_name='documents')
    title = models.CharField(max_length=300)
    document_type = models.CharField(max_length=20, choices=DocType.choices, default=DocType.OTHER)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.DRAFT)
    description = models.TextField(blank=True)
    file = models.FileField(upload_to=document_upload_path, blank=True, null=True)
    file_size = models.PositiveIntegerField(null=True, blank=True)
    mime_type = models.CharField(max_length=100, blank=True)
    version = models.PositiveIntegerField(default=1)
    parent_document = models.ForeignKey('self', on_delete=models.SET_NULL, null=True, blank=True, related_name='versions')
    contract = models.ForeignKey(Contract, on_delete=models.CASCADE, null=True, blank=True, related_name='documents')
    matter = models.ForeignKey(Matter, on_delete=models.CASCADE, null=True, blank=True, related_name='documents')
    client = models.ForeignKey(Client, on_delete=models.CASCADE, null=True, blank=True, related_name='documents')
    uploaded_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    tags = models.CharField(max_length=500, blank=True)
    is_privileged = models.BooleanField(default=False)
    is_confidential = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.title} (v{self.version})'

    def save(self, *args, **kwargs):
        if self.file:
            self.file_size = self.file.size
            self.mime_type = getattr(self.file, 'content_type', '')
        super().save(*args, **kwargs)

    @property
    def file_extension(self):
        if self.file:
            return os.path.splitext(self.file.name)[1].lower()
        return ''


class TimeEntry(models.Model):
    class ActivityType(models.TextChoices):
        RESEARCH = 'RESEARCH', 'Legal Research'
        DRAFTING = 'DRAFTING', 'Document Drafting'
        REVIEW = 'REVIEW', 'Document Review'
        MEETING = 'MEETING', 'Meeting/Conference'
        COURT = 'COURT', 'Court Appearance'
        DEPOSITION = 'DEPOSITION', 'Deposition'
        NEGOTIATION = 'NEGOTIATION', 'Negotiation'
        COMMUNICATION = 'COMMUNICATION', 'Communication'
        TRAVEL = 'TRAVEL', 'Travel'
        ADMIN = 'ADMIN', 'Administrative'
        OTHER = 'OTHER', 'Other'

    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, null=True, blank=True, related_name='time_entries')
    matter = models.ForeignKey(Matter, on_delete=models.CASCADE, related_name='time_entries')
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='time_entries')
    date = models.DateField(default=date.today)
    hours = models.DecimalField(max_digits=5, decimal_places=2, validators=[MinValueValidator(Decimal('0.1'))])
    description = models.TextField()
    activity_type = models.CharField(max_length=20, choices=ActivityType.choices, default=ActivityType.OTHER)
    rate = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True)
    is_billable = models.BooleanField(default=True)
    is_billed = models.BooleanField(default=False)
    invoice = models.ForeignKey('Invoice', on_delete=models.SET_NULL, null=True, blank=True, related_name='time_entries')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-date', '-created_at']

    def __str__(self):
        return f'{self.user.get_full_name() or self.user.username} - {self.matter} - {self.hours}h'

    @property
    def total_amount(self):
        if self.rate:
            return self.hours * self.rate
        try:
            return self.hours * self.user.profile.hourly_rate
        except Exception:
            return Decimal('0')

    def save(self, *args, **kwargs):
        if not self.rate:
            try:
                self.rate = self.user.profile.hourly_rate
            except Exception:
                pass
        super().save(*args, **kwargs)


class Invoice(models.Model):
    class Status(models.TextChoices):
        DRAFT = 'DRAFT', 'Draft'
        SENT = 'SENT', 'Sent'
        PAID = 'PAID', 'Paid'
        PARTIALLY_PAID = 'PARTIALLY_PAID', 'Partially Paid'
        OVERDUE = 'OVERDUE', 'Overdue'
        VOID = 'VOID', 'Void'
        WRITTEN_OFF = 'WRITTEN_OFF', 'Written Off'

    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, null=True, blank=True, related_name='invoices')
    invoice_number = models.CharField(max_length=50, unique=True)
    client = models.ForeignKey(Client, on_delete=models.CASCADE, related_name='invoices')
    matter = models.ForeignKey(Matter, on_delete=models.CASCADE, null=True, blank=True, related_name='invoices')
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.DRAFT)
    issue_date = models.DateField(default=date.today)
    due_date = models.DateField()
    subtotal = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0'))
    tax_rate = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal('0'))
    tax_amount = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0'))
    total_amount = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0'))
    amount_paid = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0'))
    notes = models.TextField(blank=True)
    payment_terms = models.CharField(max_length=200, default='Net 30')
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-issue_date']

    def __str__(self):
        return f'Invoice #{self.invoice_number} - {self.client.name}'

    def save(self, *args, **kwargs):
        if not self.invoice_number:
            last = Invoice.objects.order_by('-id').first()
            next_num = (last.id + 1) if last else 1
            self.invoice_number = f'INV-{next_num:05d}'
        self.tax_amount = self.subtotal * (self.tax_rate / 100)
        self.total_amount = self.subtotal + self.tax_amount
        super().save(*args, **kwargs)

    @property
    def balance_due(self):
        return self.total_amount - self.amount_paid

    @property
    def is_overdue(self):
        return self.status in ['SENT', 'PARTIALLY_PAID'] and self.due_date < date.today()


class TrustAccount(models.Model):
    client = models.ForeignKey(Client, on_delete=models.CASCADE, related_name='trust_accounts')
    matter = models.ForeignKey(Matter, on_delete=models.CASCADE, null=True, blank=True, related_name='trust_accounts')
    account_name = models.CharField(max_length=200)
    balance = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0'))
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f'{self.account_name} - {self.client.name} (${self.balance})'


class TrustTransaction(models.Model):
    class TransactionType(models.TextChoices):
        DEPOSIT = 'DEPOSIT', 'Deposit'
        WITHDRAWAL = 'WITHDRAWAL', 'Withdrawal'
        TRANSFER = 'TRANSFER', 'Transfer'
        REFUND = 'REFUND', 'Refund'

    account = models.ForeignKey(TrustAccount, on_delete=models.CASCADE, related_name='transactions')
    transaction_type = models.CharField(max_length=20, choices=TransactionType.choices)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    description = models.CharField(max_length=300)
    reference_number = models.CharField(max_length=100, blank=True)
    invoice = models.ForeignKey(Invoice, on_delete=models.SET_NULL, null=True, blank=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.get_transaction_type_display()} - ${self.amount}'

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        if self.transaction_type in ['DEPOSIT']:
            self.account.balance += self.amount
        elif self.transaction_type in ['WITHDRAWAL', 'TRANSFER']:
            self.account.balance -= self.amount
        elif self.transaction_type == 'REFUND':
            self.account.balance -= self.amount
        self.account.save()


class DeadlineQuerySet(models.QuerySet):
    """Custom queryset for Deadline with organization-scoping support."""
    def for_organization(self, organization):
        """Filter deadlines that belong to a specific organization via contract or matter."""
        if not organization:
            return self.none()
        from django.db.models import Q
        return self.filter(
            Q(contract__organization=organization) | Q(matter__organization=organization)
        )


class DeadlineManager(models.Manager):
    """Custom manager for Deadline."""
    def get_queryset(self):
        return DeadlineQuerySet(self.model, using=self._db)
    
    def for_organization(self, organization):
        """Filter deadlines that belong to a specific organization."""
        return self.get_queryset().for_organization(organization)


class Deadline(models.Model):
    class Priority(models.TextChoices):
        LOW = 'LOW', 'Low'
        MEDIUM = 'MEDIUM', 'Medium'
        HIGH = 'HIGH', 'High'
        CRITICAL = 'CRITICAL', 'Critical'

    class DeadlineType(models.TextChoices):
        COURT = 'COURT', 'Court Deadline'
        FILING = 'FILING', 'Filing Deadline'
        SOL = 'SOL', 'Statute of Limitations'
        CONTRACT = 'CONTRACT', 'Contract Deadline'
        REGULATORY = 'REGULATORY', 'Regulatory Deadline'
        INTERNAL = 'INTERNAL', 'Internal Deadline'
        CLIENT = 'CLIENT', 'Client Deadline'
        OTHER = 'OTHER', 'Other'

    title = models.CharField(max_length=300)
    description = models.TextField(blank=True)
    deadline_type = models.CharField(max_length=20, choices=DeadlineType.choices, default=DeadlineType.OTHER)
    priority = models.CharField(max_length=10, choices=Priority.choices, default=Priority.MEDIUM)
    due_date = models.DateField()
    due_time = models.TimeField(null=True, blank=True)
    reminder_days = models.PositiveIntegerField(default=7)
    matter = models.ForeignKey(Matter, on_delete=models.CASCADE, null=True, blank=True, related_name='deadlines')
    contract = models.ForeignKey(Contract, on_delete=models.CASCADE, null=True, blank=True, related_name='deadlines')
    assigned_to = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='deadlines')
    is_completed = models.BooleanField(default=False)
    completed_at = models.DateTimeField(null=True, blank=True)
    completed_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='completed_deadlines')
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='created_deadlines')
    created_at = models.DateTimeField(auto_now_add=True)

    objects = DeadlineManager()

    class Meta:
        ordering = ['due_date']

    def __str__(self):
        return f'{self.title} - Due: {self.due_date}'

    @property
    def is_overdue(self):
        return not self.is_completed and self.due_date < date.today()

    @property
    def days_remaining(self):
        if self.is_completed:
            return None
        return (self.due_date - date.today()).days

    @property
    def needs_reminder(self):
        if self.is_completed:
            return False
        days = (self.due_date - date.today()).days
        return 0 < days <= self.reminder_days


class AuditLog(models.Model):
    class Action(models.TextChoices):
        CREATE = 'CREATE', 'Created'
        UPDATE = 'UPDATE', 'Updated'
        DELETE = 'DELETE', 'Deleted'
        VIEW = 'VIEW', 'Viewed'
        LOGIN = 'LOGIN', 'Logged In'
        LOGOUT = 'LOGOUT', 'Logged Out'
        EXPORT = 'EXPORT', 'Exported'
        APPROVE = 'APPROVE', 'Approved'
        REJECT = 'REJECT', 'Rejected'

    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='audit_logs')
    action = models.CharField(max_length=20, choices=Action.choices)
    model_name = models.CharField(max_length=100)
    object_id = models.PositiveIntegerField(null=True, blank=True)
    object_repr = models.CharField(max_length=300, blank=True)
    changes = models.JSONField(null=True, blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.TextField(blank=True)
    timestamp = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-timestamp']

    def __str__(self):
        return f'{self.user} {self.get_action_display()} {self.model_name} #{self.object_id}'


class Notification(models.Model):
    class NotificationType(models.TextChoices):
        DEADLINE = 'DEADLINE', 'Deadline Reminder'
        TASK = 'TASK', 'Task Assignment'
        CONTRACT = 'CONTRACT', 'Contract Update'
        APPROVAL = 'APPROVAL', 'Approval Request'
        SYSTEM = 'SYSTEM', 'System'
        BILLING = 'BILLING', 'Billing'

    recipient = models.ForeignKey(User, on_delete=models.CASCADE, related_name='notifications')
    notification_type = models.CharField(max_length=20, choices=NotificationType.choices)
    title = models.CharField(max_length=300)
    message = models.TextField()
    link = models.CharField(max_length=500, blank=True)
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.title} -> {self.recipient.username}'


class ConflictCheck(models.Model):
    class Status(models.TextChoices):
        PENDING = 'PENDING', 'Pending Review'
        CLEAR = 'CLEAR', 'No Conflict'
        CONFLICT = 'CONFLICT', 'Conflict Found'
        WAIVED = 'WAIVED', 'Conflict Waived'

    client = models.ForeignKey(Client, on_delete=models.CASCADE, null=True, blank=True, related_name='conflict_checks')
    matter = models.ForeignKey(Matter, on_delete=models.CASCADE, null=True, blank=True, related_name='conflict_checks')
    checked_party = models.CharField(max_length=200)
    checked_party_type = models.CharField(max_length=50, blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    notes = models.TextField(blank=True)
    conflicts_found = models.TextField(blank=True)
    checked_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='conflict_checks_performed')
    resolved_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='conflict_checks_resolved')
    created_at = models.DateTimeField(auto_now_add=True)
    resolved_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'Conflict Check: {self.checked_party} ({self.get_status_display()})'


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
    client = models.ForeignKey(Client, on_delete=models.SET_NULL, null=True, blank=True, related_name='trademark_requests')
    matter = models.ForeignKey(Matter, on_delete=models.SET_NULL, null=True, blank=True, related_name='trademark_requests')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.mark_text


class LegalTaskQuerySet(models.QuerySet):
    """Custom queryset for LegalTask with organization-scoping support."""
    def for_organization(self, organization):
        """Filter legal tasks that belong to a specific organization via contract or matter."""
        if not organization:
            return self.none()
        from django.db.models import Q
        return self.filter(
            Q(contract__organization=organization) | Q(matter__organization=organization)
        )


class LegalTaskManager(models.Manager):
    """Custom manager for LegalTask."""
    def get_queryset(self):
        return LegalTaskQuerySet(self.model, using=self._db)
    
    def for_organization(self, organization):
        """Filter legal tasks that belong to a specific organization."""
        return self.get_queryset().for_organization(organization)


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
    contract = models.ForeignKey(Contract, on_delete=models.CASCADE, null=True, blank=True)
    matter = models.ForeignKey(Matter, on_delete=models.CASCADE, null=True, blank=True, related_name='tasks')
    due_date = models.DateField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = LegalTaskManager()

    def __str__(self):
        return self.title


class Tag(models.Model):
    name = models.CharField(max_length=50, unique=True)

    def __str__(self):
        return self.name


class RiskLogQuerySet(models.QuerySet):
    """Custom queryset for RiskLog with organization-scoping support."""
    def for_organization(self, organization):
        """Filter risk logs that belong to a specific organization via contract or matter."""
        if not organization:
            return self.none()
        from django.db.models import Q
        return self.filter(
            Q(contract__organization=organization) | Q(matter__organization=organization)
        )


class RiskLogManager(models.Manager):
    """Custom manager for RiskLog."""
    def get_queryset(self):
        return RiskLogQuerySet(self.model, using=self._db)
    
    def for_organization(self, organization):
        """Filter risk logs that belong to a specific organization."""
        return self.get_queryset().for_organization(organization)


class RiskLog(models.Model):
    class RiskLevel(models.TextChoices):
        LOW = 'LOW', 'Low'
        MEDIUM = 'MEDIUM', 'Medium'
        HIGH = 'HIGH', 'High'
        CRITICAL = 'CRITICAL', 'Critical'

    title = models.CharField(max_length=200)
    description = models.TextField()
    risk_level = models.CharField(max_length=10, choices=RiskLevel.choices, default=RiskLevel.MEDIUM)
    contract = models.ForeignKey(Contract, on_delete=models.CASCADE, null=True, blank=True)
    matter = models.ForeignKey(Matter, on_delete=models.CASCADE, null=True, blank=True, related_name='risks')
    mitigation_plan = models.TextField(blank=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    objects = RiskLogManager()

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
    contract = models.ForeignKey(Contract, on_delete=models.CASCADE, null=True, blank=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.title


class ChecklistItem(models.Model):
    checklist = models.ForeignKey(ComplianceChecklist, on_delete=models.CASCADE, related_name='items')
    title = models.CharField(max_length=200, default='Untitled Item')
    description = models.TextField(blank=True)
    is_completed = models.BooleanField(default=False)
    completed_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
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
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name


class WorkflowTemplateStep(models.Model):
    template = models.ForeignKey(WorkflowTemplate, on_delete=models.CASCADE, related_name='steps')
    name = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    order = models.PositiveIntegerField(default=0)
    estimated_duration = models.DurationField(null=True, blank=True)

    class Meta:
        ordering = ['order']

    def __str__(self):
        return f"{self.template.name} - {self.name}"


class Workflow(models.Model):
    class Status(models.TextChoices):
        ACTIVE = 'ACTIVE', 'Active'
        COMPLETED = 'COMPLETED', 'Completed'
        CANCELLED = 'CANCELLED', 'Cancelled'

    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    template = models.ForeignKey(WorkflowTemplate, on_delete=models.SET_NULL, null=True, blank=True)
    contract = models.ForeignKey(Contract, on_delete=models.CASCADE, null=True, blank=True)
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
    name = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    assigned_to = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    due_date = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ['order']

    def __str__(self):
        return f"{self.workflow.title} - {self.name}"


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

    organization = models.ForeignKey(
        'Organization', on_delete=models.CASCADE, null=True, blank=True,
        related_name='due_diligence_processes',
    )
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

    organization = models.ForeignKey(
        'Organization', on_delete=models.CASCADE, null=True, blank=True,
        related_name='budgets',
    )
    year = models.PositiveIntegerField()
    quarter = models.CharField(max_length=2, choices=Quarter.choices)
    department = models.CharField(max_length=100)
    allocated_amount = models.DecimalField(max_digits=12, decimal_places=2, validators=[MinValueValidator(Decimal('0'))])
    description = models.TextField(blank=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ['organization', 'year', 'quarter', 'department']

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


class NegotiationThread(models.Model):
    contract = models.ForeignKey(Contract, on_delete=models.CASCADE, related_name='negotiation_threads')
    title = models.CharField(max_length=200)
    content = models.TextField()
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['created_at']

    def __str__(self):
        return f"{self.contract.title} - {self.title}"


class Counterparty(models.Model):
    class EntityType(models.TextChoices):
        CORPORATION = 'CORPORATION', 'Corporation'
        LLC = 'LLC', 'LLC'
        PARTNERSHIP = 'PARTNERSHIP', 'Partnership'
        INDIVIDUAL = 'INDIVIDUAL', 'Individual'
        GOVERNMENT = 'GOVERNMENT', 'Government'
        NON_PROFIT = 'NON_PROFIT', 'Non-Profit'
        OTHER = 'OTHER', 'Other'

    name = models.CharField(max_length=300)
    entity_type = models.CharField(max_length=20, choices=EntityType.choices, default=EntityType.CORPORATION)
    jurisdiction = models.CharField(max_length=200, blank=True)
    registration_number = models.CharField(max_length=100, blank=True)
    address = models.TextField(blank=True)
    contact_name = models.CharField(max_length=200, blank=True)
    contact_email = models.EmailField(blank=True)
    contact_phone = models.CharField(max_length=30, blank=True)
    website = models.URLField(blank=True)
    notes = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name_plural = 'Counterparties'

    def __str__(self):
        return self.name


class ClauseCategory(models.Model):
    name = models.CharField(max_length=100, unique=True)
    description = models.TextField(blank=True)
    order = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name_plural = 'Clause categories'
        ordering = ['order', 'name']

    def __str__(self):
        return self.name


class ClauseTemplate(models.Model):
    class JurisdictionScope(models.TextChoices):
        EU = 'EU', 'European Union'
        US = 'US', 'United States'
        UK = 'UK', 'United Kingdom'
        GLOBAL = 'GLOBAL', 'Global/Universal'
        CUSTOM = 'CUSTOM', 'Custom'

    title = models.CharField(max_length=200)
    category = models.ForeignKey(ClauseCategory, on_delete=models.SET_NULL, null=True, blank=True, related_name='clauses')
    content = models.TextField(help_text='Standard clause text')
    fallback_content = models.TextField(blank=True, help_text='Fallback/negotiation position')
    jurisdiction_scope = models.CharField(max_length=10, choices=JurisdictionScope.choices, default=JurisdictionScope.GLOBAL)
    is_mandatory = models.BooleanField(default=False, help_text='Required in all contracts of this type')
    applicable_contract_types = models.CharField(max_length=200, blank=True, help_text='Comma-separated contract types')
    version = models.PositiveIntegerField(default=1)
    is_approved = models.BooleanField(default=False)
    approved_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='approved_clauses')
    approved_at = models.DateTimeField(null=True, blank=True)
    playbook_notes = models.TextField(blank=True, help_text='Negotiation playbook guidance')
    tags = models.CharField(max_length=500, blank=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f'{self.title} (v{self.version})'


class EthicalWall(models.Model):
    name = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    matter = models.ForeignKey(Matter, on_delete=models.CASCADE, null=True, blank=True, related_name='ethical_walls')
    client = models.ForeignKey(Client, on_delete=models.CASCADE, null=True, blank=True, related_name='ethical_walls')
    restricted_users = models.ManyToManyField(User, related_name='ethical_wall_restrictions', blank=True)
    is_active = models.BooleanField(default=True)
    reason = models.TextField(blank=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='created_walls')
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return self.name


class SignatureRequest(models.Model):
    class Status(models.TextChoices):
        PENDING = 'PENDING', 'Pending'
        SENT = 'SENT', 'Sent'
        VIEWED = 'VIEWED', 'Viewed'
        SIGNED = 'SIGNED', 'Signed'
        DECLINED = 'DECLINED', 'Declined'
        EXPIRED = 'EXPIRED', 'Expired'
        CANCELLED = 'CANCELLED', 'Cancelled'

    contract = models.ForeignKey(Contract, on_delete=models.CASCADE, related_name='signature_requests')
    document = models.ForeignKey(Document, on_delete=models.SET_NULL, null=True, blank=True, related_name='signature_requests')
    signer_name = models.CharField(max_length=200)
    signer_email = models.EmailField()
    signer_role = models.CharField(max_length=100, blank=True, help_text='e.g. CEO, Legal Counsel')
    status = models.CharField(max_length=15, choices=Status.choices, default=Status.PENDING)
    external_id = models.CharField(max_length=200, blank=True, help_text='External provider reference ID')
    sent_at = models.DateTimeField(null=True, blank=True)
    viewed_at = models.DateTimeField(null=True, blank=True)
    signed_at = models.DateTimeField(null=True, blank=True)
    declined_at = models.DateTimeField(null=True, blank=True)
    decline_reason = models.TextField(blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    execution_certificate_url = models.URLField(blank=True)
    order = models.PositiveIntegerField(default=0)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['order', 'created_at']

    def __str__(self):
        return f'{self.contract.title} - {self.signer_name} ({self.get_status_display()})'


class DataInventoryRecord(models.Model):
    class LawfulBasis(models.TextChoices):
        CONSENT = 'CONSENT', 'Consent'
        CONTRACT = 'CONTRACT', 'Contractual Necessity'
        LEGAL_OBLIGATION = 'LEGAL_OBLIGATION', 'Legal Obligation'
        VITAL_INTEREST = 'VITAL_INTEREST', 'Vital Interest'
        PUBLIC_INTEREST = 'PUBLIC_INTEREST', 'Public Interest'
        LEGITIMATE_INTEREST = 'LEGITIMATE_INTEREST', 'Legitimate Interest'

    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    data_categories = models.TextField(help_text='Categories of personal data processed')
    data_subjects = models.TextField(help_text='Categories of data subjects')
    purpose = models.TextField(help_text='Purpose of processing')
    lawful_basis = models.CharField(max_length=25, choices=LawfulBasis.choices)
    retention_period = models.CharField(max_length=200, help_text='e.g. 7 years, until consent withdrawn')
    recipients = models.TextField(blank=True, help_text='Categories of recipients')
    third_country_transfers = models.BooleanField(default=False)
    transfer_safeguards = models.TextField(blank=True, help_text='SCC, DPF, adequacy decision, etc.')
    technical_measures = models.TextField(blank=True, help_text='Encryption, pseudonymization, etc.')
    organizational_measures = models.TextField(blank=True, help_text='Access controls, training, etc.')
    dpia_required = models.BooleanField(default=False, help_text='Data Protection Impact Assessment required')
    dpia_completed = models.BooleanField(default=False)
    controller = models.CharField(max_length=200, blank=True)
    processor = models.CharField(max_length=200, blank=True)
    dpo_contact = models.CharField(max_length=200, blank=True)
    client = models.ForeignKey(Client, on_delete=models.SET_NULL, null=True, blank=True, related_name='data_inventory')
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.title


class DSARRequest(models.Model):
    class RequestType(models.TextChoices):
        ACCESS = 'ACCESS', 'Right of Access'
        RECTIFICATION = 'RECTIFICATION', 'Right to Rectification'
        ERASURE = 'ERASURE', 'Right to Erasure'
        RESTRICT = 'RESTRICT', 'Right to Restrict Processing'
        PORTABILITY = 'PORTABILITY', 'Right to Data Portability'
        OBJECTION = 'OBJECTION', 'Right to Object'

    class Status(models.TextChoices):
        RECEIVED = 'RECEIVED', 'Received'
        VERIFIED = 'VERIFIED', 'Identity Verified'
        IN_PROGRESS = 'IN_PROGRESS', 'In Progress'
        COMPLETED = 'COMPLETED', 'Completed'
        DENIED = 'DENIED', 'Denied'
        EXTENDED = 'EXTENDED', 'Extended'

    reference_number = models.CharField(max_length=50, unique=True)
    request_type = models.CharField(max_length=15, choices=RequestType.choices)
    status = models.CharField(max_length=15, choices=Status.choices, default=Status.RECEIVED)
    requester_name = models.CharField(max_length=200)
    requester_email = models.EmailField()
    requester_id_verified = models.BooleanField(default=False)
    description = models.TextField()
    response = models.TextField(blank=True)
    denial_reason = models.TextField(blank=True)
    received_date = models.DateField()
    due_date = models.DateField(help_text='Must respond within 30 days (GDPR)')
    completed_date = models.DateField(null=True, blank=True)
    extended = models.BooleanField(default=False, help_text='Extension requested (up to 60 additional days)')
    client = models.ForeignKey(Client, on_delete=models.SET_NULL, null=True, blank=True, related_name='dsar_requests')
    assigned_to = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='assigned_dsars')
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'DSAR Request'

    def __str__(self):
        return f'{self.reference_number} - {self.get_request_type_display()}'

    def save(self, *args, **kwargs):
        if not self.reference_number:
            last = DSARRequest.objects.order_by('-id').first()
            next_num = (last.id + 1) if last else 1
            self.reference_number = f'DSAR-{next_num:05d}'
        super().save(*args, **kwargs)

    @property
    def is_overdue(self):
        if self.status not in ['COMPLETED', 'DENIED'] and self.due_date:
            return date.today() > self.due_date
        return False


class Subprocessor(models.Model):
    name = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    service_type = models.CharField(max_length=200, help_text='e.g. Cloud hosting, Payment processing')
    country = models.CharField(max_length=100)
    is_eu_based = models.BooleanField(default=False)
    dpa_in_place = models.BooleanField(default=False)
    scc_in_place = models.BooleanField(default=False)
    dpf_certified = models.BooleanField(default=False, help_text='Data Privacy Framework certified')
    data_categories = models.TextField(blank=True, help_text='Types of data shared')
    contact_email = models.EmailField(blank=True)
    contract_start_date = models.DateField(null=True, blank=True)
    contract_end_date = models.DateField(null=True, blank=True)
    last_audit_date = models.DateField(null=True, blank=True)
    risk_level = models.CharField(max_length=10, choices=[
        ('LOW', 'Low'), ('MEDIUM', 'Medium'), ('HIGH', 'High'),
    ], default='LOW')
    is_active = models.BooleanField(default=True)
    notes = models.TextField(blank=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f'{self.name} ({self.country})'


class TransferRecord(models.Model):
    class TransferMechanism(models.TextChoices):
        ADEQUACY = 'ADEQUACY', 'Adequacy Decision'
        SCC = 'SCC', 'Standard Contractual Clauses'
        BCR = 'BCR', 'Binding Corporate Rules'
        DPF = 'DPF', 'Data Privacy Framework'
        CONSENT = 'CONSENT', 'Explicit Consent'
        DEROGATION = 'DEROGATION', 'Derogation'

    title = models.CharField(max_length=200)
    source_country = models.CharField(max_length=100)
    destination_country = models.CharField(max_length=100)
    transfer_mechanism = models.CharField(max_length=15, choices=TransferMechanism.choices)
    data_categories = models.TextField(help_text='Types of data transferred')
    subprocessor = models.ForeignKey(Subprocessor, on_delete=models.SET_NULL, null=True, blank=True, related_name='transfers')
    contract = models.ForeignKey(Contract, on_delete=models.SET_NULL, null=True, blank=True, related_name='data_transfers')
    tia_completed = models.BooleanField(default=False, help_text='Transfer Impact Assessment completed')
    supplementary_measures = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    start_date = models.DateField(null=True, blank=True)
    review_date = models.DateField(null=True, blank=True)
    notes = models.TextField(blank=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f'{self.title} ({self.source_country} → {self.destination_country})'


class RetentionPolicy(models.Model):
    class Category(models.TextChoices):
        CONTRACTS = 'CONTRACTS', 'Contracts'
        CLIENT_DATA = 'CLIENT_DATA', 'Client Data'
        EMPLOYEE_DATA = 'EMPLOYEE_DATA', 'Employee Data'
        FINANCIAL = 'FINANCIAL', 'Financial Records'
        CORRESPONDENCE = 'CORRESPONDENCE', 'Correspondence'
        LITIGATION = 'LITIGATION', 'Litigation Files'
        COMPLIANCE = 'COMPLIANCE', 'Compliance Records'
        OTHER = 'OTHER', 'Other'

    title = models.CharField(max_length=200)
    category = models.CharField(max_length=20, choices=Category.choices)
    description = models.TextField(blank=True)
    retention_period_days = models.PositiveIntegerField(help_text='Retention period in days')
    legal_basis = models.TextField(blank=True, help_text='Legal requirement for retention')
    deletion_method = models.CharField(max_length=200, blank=True, help_text='How data is destroyed')
    auto_delete = models.BooleanField(default=False)
    review_frequency_days = models.PositiveIntegerField(default=365)
    last_reviewed = models.DateField(null=True, blank=True)
    next_review = models.DateField(null=True, blank=True)
    is_active = models.BooleanField(default=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name_plural = 'Retention policies'

    def __str__(self):
        return f'{self.title} ({self.retention_period_days} days)'


class LegalHold(models.Model):
    class Status(models.TextChoices):
        ACTIVE = 'ACTIVE', 'Active'
        RELEASED = 'RELEASED', 'Released'
        EXPIRED = 'EXPIRED', 'Expired'

    title = models.CharField(max_length=200)
    description = models.TextField()
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.ACTIVE)
    matter = models.ForeignKey(Matter, on_delete=models.CASCADE, null=True, blank=True, related_name='legal_holds')
    client = models.ForeignKey(Client, on_delete=models.SET_NULL, null=True, blank=True, related_name='legal_holds')
    custodians = models.ManyToManyField(User, related_name='legal_hold_custodians', blank=True)
    hold_start_date = models.DateField()
    hold_end_date = models.DateField(null=True, blank=True)
    reason = models.TextField(blank=True)
    scope = models.TextField(blank=True, help_text='Documents, emails, data types in scope')
    issued_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='issued_holds')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f'{self.title} ({self.get_status_display()})'


class ApprovalRule(models.Model):
    class TriggerType(models.TextChoices):
        VALUE_ABOVE = 'VALUE_ABOVE', 'Contract Value Above'
        JURISDICTION = 'JURISDICTION', 'Specific Jurisdiction'
        CONTRACT_TYPE = 'CONTRACT_TYPE', 'Contract Type'
        RISK_LEVEL = 'RISK_LEVEL', 'Risk Level'
        DATA_TRANSFER = 'DATA_TRANSFER', 'Cross-border Data Transfer'

    name = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    trigger_type = models.CharField(max_length=20, choices=TriggerType.choices)
    trigger_value = models.CharField(max_length=200, help_text='Threshold value or matching text')
    approval_step = models.CharField(max_length=20, choices=[
        ('LEGAL', 'Legal Review'),
        ('FINANCE', 'Finance Review'),
        ('PRIVACY', 'Privacy Review'),
        ('EXECUTIVE', 'Executive Approval'),
        ('COMPLIANCE', 'Compliance Review'),
    ])
    approver_role = models.CharField(max_length=20, choices=UserProfile.Role.choices)
    specific_approver = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='approval_rules')
    sla_hours = models.PositiveIntegerField(default=48, help_text='SLA in hours for approval')
    escalation_after_hours = models.PositiveIntegerField(default=72, help_text='Auto-escalate after hours')
    is_active = models.BooleanField(default=True)
    order = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['order']

    def __str__(self):
        return f'{self.name} ({self.get_trigger_type_display()})'


class ApprovalRequest(models.Model):
    class Status(models.TextChoices):
        PENDING = 'PENDING', 'Pending'
        APPROVED = 'APPROVED', 'Approved'
        REJECTED = 'REJECTED', 'Rejected'
        ESCALATED = 'ESCALATED', 'Escalated'

    contract = models.ForeignKey(Contract, on_delete=models.CASCADE, related_name='approval_requests')
    rule = models.ForeignKey(ApprovalRule, on_delete=models.SET_NULL, null=True, blank=True)
    approval_step = models.CharField(max_length=50)
    status = models.CharField(max_length=15, choices=Status.choices, default=Status.PENDING)
    assigned_to = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='approval_assignments')
    comments = models.TextField(blank=True)
    due_date = models.DateTimeField(null=True, blank=True)
    decided_at = models.DateTimeField(null=True, blank=True)
    decided_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='approval_decisions')
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f'{self.contract.title} - {self.approval_step} ({self.get_status_display()})'


# Temporary compatibility aliases for legacy care-oriented views/forms.
# These keep imports and URL checks operational while the care refactor is stabilized.
class _CareScope(models.TextChoices):
    GEMEENTE = 'GEMEENTE', 'Gemeente'
    REGIO = 'REGIO', 'Regio'


class _CareStatus(models.TextChoices):
    ACTIVE = 'ACTIVE', 'Active'
    ON_HOLD = 'ON_HOLD', 'On hold'


class _CaseAssessmentStatus(models.TextChoices):
    DRAFT = 'DRAFT', 'Draft'
    UNDER_REVIEW = 'UNDER_REVIEW', 'Under review'
    NEEDS_INFO = 'NEEDS_INFO', 'Needs info'
    APPROVED_FOR_MATCHING = 'APPROVED_FOR_MATCHING', 'Approved for matching'


Matter.Scope = _CareScope
Matter.Status = _CareStatus
CareConfiguration = Matter
MunicipalityConfiguration = Matter
RegionalConfiguration = Matter

DueDiligenceProcess.AssessmentStatus = _CaseAssessmentStatus
CaseAssessment = DueDiligenceProcess
