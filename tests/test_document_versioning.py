import hashlib

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, TestCase
from django.urls import reverse

from contracts.models import Client as ClientModel, Contract, Document, Matter, Organization, OrganizationMembership
from contracts.models import DocumentOCRReview


User = get_user_model()


class DocumentVersioningTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.owner = User.objects.create_user(
            username='owner-user',
            email='owner@example.com',
            password='testpass123',
        )
        self.organization = Organization.objects.create(name='Docs Org', slug='docs-org')
        OrganizationMembership.objects.create(
            organization=self.organization,
            user=self.owner,
            role=OrganizationMembership.Role.OWNER,
            is_active=True,
        )
        self.contract = Contract.objects.create(
            organization=self.organization,
            title='Docs Contract',
            contract_type=Contract.ContractType.MSA,
            content='Contract content',
            status=Contract.Status.ACTIVE,
            counterparty='Acme Corp',
            governing_law='State of Delaware',
            jurisdiction='New York',
            created_by=self.owner,
        )
        self.document = Document.objects.create(
            organization=self.organization,
            title='Initial Document',
            document_type=Document.DocType.CONTRACT,
            status=Document.Status.FINAL,
            description='Initial version',
            file=SimpleUploadedFile('initial.txt', b'Initial content', content_type='text/plain'),
            contract=self.contract,
            client=None,
            matter=None,
            uploaded_by=self.owner,
            tags='',
            is_privileged=False,
            is_confidential=False,
        )

    def test_document_save_persists_file_hash(self):
        expected_hash = hashlib.sha256(b'Initial content').hexdigest()
        self.document.refresh_from_db()
        self.assertEqual(self.document.file_hash, expected_hash)
        self.assertTrue(DocumentOCRReview.objects.filter(document=self.document).exists())

    def test_document_update_creates_immutable_new_version(self):
        self.client.login(username='owner-user', password='testpass123')
        response = self.client.post(
            reverse('contracts:document_update', kwargs={'pk': self.document.pk}),
            data={
                'title': 'Updated Document',
                'document_type': Document.DocType.CONTRACT,
                'status': Document.Status.FINAL,
                'description': 'Updated version',
                'file': SimpleUploadedFile('updated.txt', b'Updated content', content_type='text/plain'),
                'contract': self.contract.pk,
                'matter': '',
                'client': '',
                'tags': 'updated,version',
                'is_privileged': '',
                'is_confidential': '',
            },
            follow=True,
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'updated as version 2')

        original_document = Document.objects.get(pk=self.document.pk)
        new_version = Document.objects.get(parent_document=original_document)
        self.assertEqual(original_document.version, 1)
        self.assertEqual(new_version.version, 2)
        self.assertEqual(new_version.title, 'Updated Document')
        self.assertEqual(new_version.description, 'Updated version')
        self.assertEqual(new_version.file_hash, hashlib.sha256(b'Updated content').hexdigest())
        self.assertEqual(new_version.parent_document_id, original_document.id)

    def test_document_compare_shows_version_differences(self):
        self.client.login(username='owner-user', password='testpass123')
        response = self.client.post(
            reverse('contracts:document_update', kwargs={'pk': self.document.pk}),
            data={
                'title': 'Updated Document',
                'document_type': Document.DocType.CONTRACT,
                'status': Document.Status.FINAL,
                'description': 'Updated version',
                'file': SimpleUploadedFile('updated.txt', b'Updated content', content_type='text/plain'),
                'contract': self.contract.pk,
                'matter': '',
                'client': '',
                'tags': 'updated,version',
                'is_privileged': '',
                'is_confidential': '',
            },
            follow=True,
        )

        self.assertEqual(response.status_code, 200)
        new_version = Document.objects.get(parent_document=self.document)
        compare_response = self.client.get(
            reverse('contracts:document_compare', kwargs={'pk': self.document.pk, 'other_pk': new_version.pk}),
        )

        self.assertEqual(compare_response.status_code, 200)
        self.assertContains(compare_response, 'Field Differences')
        self.assertContains(compare_response, 'file_hash')
        self.assertContains(compare_response, self.document.file_hash)
        self.assertContains(compare_response, new_version.file_hash)

    def test_document_ocr_queue_is_accessible(self):
        self.client.login(username='owner-user', password='testpass123')
        response = self.client.get(reverse('contracts:document_ocr_queue'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'OCR Queue')
        self.assertContains(response, self.document.title)

    def test_document_ocr_review_can_be_verified(self):
        review = DocumentOCRReview.objects.get(document=self.document)
        self.client.login(username='owner-user', password='testpass123')
        response = self.client.post(
            reverse('contracts:document_ocr_review', kwargs={'pk': review.pk}),
            data={
                'status': DocumentOCRReview.Status.VERIFIED,
                'extracted_text': 'Verified text',
                'confidence_score': '0.98',
                'review_notes': 'Looks good',
            },
            follow=True,
        )

        self.assertEqual(response.status_code, 200)
        review.refresh_from_db()
        self.assertEqual(review.status, DocumentOCRReview.Status.VERIFIED)
        self.assertEqual(review.reviewed_by_id, self.owner.id)
        self.assertIsNotNone(review.reviewed_at)
