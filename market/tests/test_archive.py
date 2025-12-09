from django.urls import reverse
from rest_framework.test import APITestCase
from django.contrib.auth import get_user_model
from market.models import Product
from rest_framework import status
from django.utils import timezone

User = get_user_model()


class ArchiveTests(APITestCase):
    def setUp(self):
        self.owner = User.objects.create_user(username='owner', password='pass')
        self.admin = User.objects.create_user(username='admin', password='pass', role='ADMIN', is_staff=True)
        self.other = User.objects.create_user(username='other', password='pass')
        self.product = Product.objects.create(seller=self.owner, title='T', price='10.00')

    def test_owner_can_archive_and_restore(self):
        self.client.login(username='owner', password='pass')
        url = reverse('products-archive', args=[self.product.id])
        resp = self.client.post(url)
        self.assertEqual(resp.status_code, status.HTTP_204_NO_CONTENT)
        p = Product.objects.get(id=self.product.id)
        self.assertTrue(p.archived)
        self.assertIsNotNone(p.archived_at)

        # restore
        url = reverse('products-restore', args=[self.product.id])
        resp = self.client.post(url)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        p.refresh_from_db()
        self.assertFalse(p.archived)
        self.assertIsNone(p.archived_at)

    def test_include_archived_owner_and_admin(self):
        # owner archives
        self.product.archived = True
        self.product.archived_at = timezone.now()
        self.product.save()

        # owner listing with include_archived and seller_id
        self.client.login(username='owner', password='pass')
        url = reverse('products-list') + f'?include_archived=true&seller_id={self.owner.id}'
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertTrue(any(it['id'] == self.product.id for it in resp.json()))

        # other user cannot include archived unless admin
        self.client.logout()
        self.client.login(username='other', password='pass')
        url = reverse('products-list') + '?include_archived=true'
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        # product should not be visible
        self.assertFalse(any(it['id'] == self.product.id for it in resp.json()))

        # admin can include archived
        self.client.logout()
        self.client.login(username='admin', password='pass')
        url = reverse('products-list') + '?include_archived=true'
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertTrue(any(it['id'] == self.product.id for it in resp.json()))
