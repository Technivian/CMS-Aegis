# CRM Contract Canonical Field Map (Sprint 1)

This canonical schema is the source of truth for CRM-to-contract ingestion.

| Canonical Field | Default Salesforce Object | Default Salesforce Field |
|---|---|---|
| `contract_title` | `Opportunity` | `Name` |
| `counterparty_name` | `Opportunity` | `Account.Name` |
| `contract_type` | `Opportunity` | `Type` |
| `contract_value` | `Opportunity` | `Amount` |
| `currency` | `Opportunity` | `CurrencyIsoCode` |
| `effective_date` | `Contract__c` | `Effective_Date__c` |
| `end_date` | `Contract__c` | `End_Date__c` |
| `renewal_date` | `Contract__c` | `Renewal_Date__c` |
| `governing_law` | `Contract__c` | `Governing_Law__c` |
| `jurisdiction` | `Contract__c` | `Jurisdiction__c` |
| `owner_email` | `Opportunity` | `Owner.Email` |
| `owner_name` | `Opportunity` | `Owner.Name` |
| `approver_email` | `Contract__c` | `Approver_Email__c` |
| `risk_level` | `Contract__c` | `Risk_Level__c` |
| `status` | `Contract__c` | `Status__c` |
| `workflow_template` | `Contract__c` | `Workflow_Template__c` |
| `source_system_id` | `Opportunity` | `Id` |
| `source_system_url` | `Opportunity` | `Record_URL__c` |
| `created_at` | `Opportunity` | `CreatedDate` |
| `updated_at` | `Opportunity` | `LastModifiedDate` |

Notes:
- Organization admins can override mappings via `GET/PUT /contracts/api/integrations/salesforce/field-map/`.
- Canonical fields are unique per organization to keep ingestion deterministic.
