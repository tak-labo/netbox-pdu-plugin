"""
Test cases for NetBox PDU Plugin GraphQL API.

Run inside Docker:
  docker compose exec netbox python manage.py test netbox_pdu_plugin.tests.test_graphql -v2
"""

from ..models import PDUInlet, PDUOutlet
from ..testing import PluginGraphQLTestCase
from .test_models import create_test_pdu


class ManagedPDUGraphQLTest(PluginGraphQLTestCase):
    """Tests for ManagedPDU GraphQL queries."""

    @classmethod
    def setUpTestData(cls):
        cls.pdu = create_test_pdu()

    def test_query_managed_pdu_list(self):
        self.add_permissions('netbox_pdu_plugin.view_managedpdu')
        query = """
        query {
            managed_pdu_list {
                id
                vendor
                api_url
            }
        }
        """
        response = self.execute_query(query)
        self.assertIsNone(response.get('errors'))
        self.assertGreaterEqual(len(response['data']['managed_pdu_list']), 1)

    def test_query_managed_pdu(self):
        self.add_permissions('netbox_pdu_plugin.view_managedpdu')
        query = (
            "query { "
            f"managed_pdu(id: {self.pdu.pk}) {{ "
            "id vendor api_url "
            "} }"
        )
        response = self.execute_query(query)
        self.assertIsNone(response.get('errors'))
        self.assertEqual(response['data']['managed_pdu']['id'], str(self.pdu.pk))


class PDUOutletGraphQLTest(PluginGraphQLTestCase):
    """Tests for PDUOutlet GraphQL queries."""

    @classmethod
    def setUpTestData(cls):
        cls.pdu = create_test_pdu()
        cls.outlet = PDUOutlet.objects.create(
            managed_pdu=cls.pdu,
            outlet_number=1,
            outlet_name='Outlet 1',
        )

    def test_query_outlet_list(self):
        self.add_permissions('netbox_pdu_plugin.view_pduoutlet')
        query = """
        query {
            pdu_outlet_list {
                id
                outlet_number
                status
            }
        }
        """
        response = self.execute_query(query)
        self.assertIsNone(response.get('errors'))
        self.assertGreaterEqual(len(response['data']['pdu_outlet_list']), 1)


class PDUInletGraphQLTest(PluginGraphQLTestCase):
    """Tests for PDUInlet GraphQL queries."""

    @classmethod
    def setUpTestData(cls):
        cls.pdu = create_test_pdu()
        cls.inlet = PDUInlet.objects.create(
            managed_pdu=cls.pdu,
            inlet_number=1,
        )

    def test_query_inlet_list(self):
        self.add_permissions('netbox_pdu_plugin.view_pduinlet')
        query = """
        query {
            pdu_inlet_list {
                id
                inlet_number
            }
        }
        """
        response = self.execute_query(query)
        self.assertIsNone(response.get('errors'))
        self.assertGreaterEqual(len(response['data']['pdu_inlet_list']), 1)
