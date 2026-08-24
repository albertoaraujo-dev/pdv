import json
from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase, override_settings

from .abacatepay import create_transparent, get_transparent, simulate_transparent


class AbacatePayClientTests(SimpleTestCase):
    @override_settings(ABACATEPAY_API_KEY="sandbox-key")
    @patch("apps.sales.abacatepay.urlopen")
    def test_create_transparent_uses_documented_payload(self, urlopen_mock):
        response = MagicMock()
        response.read.return_value = b'{"success": true}'
        urlopen_mock.return_value.__enter__.return_value = response

        create_transparent(amount_cents=350, external_id="sale-1", metadata={"saleId": "1"})

        request = urlopen_mock.call_args.args[0]
        self.assertEqual(request.full_url, "https://api.abacatepay.com/v2/transparents/create")
        self.assertEqual(json.loads(request.data), {
            "method": "PIX",
            "data": {"amount": 350, "externalId": "sale-1", "metadata": {"saleId": "1"}},
        })
        self.assertEqual(request.get_header("Authorization"), "Bearer sandbox-key")
        self.assertEqual(request.get_header("User-agent"), "pdv-final-abacatepay/1.0 (+https://ligara.online)")

    @override_settings(ABACATEPAY_API_KEY="sandbox-key")
    @patch("apps.sales.abacatepay.urlopen")
    def test_status_and_simulation_use_documented_query_endpoints(self, urlopen_mock):
        response = MagicMock()
        response.read.return_value = b'{}'
        urlopen_mock.return_value.__enter__.return_value = response

        get_transparent("pix_char_1")
        simulate_transparent("pix_char_1")

        status_request, simulation_request = [call.args[0] for call in urlopen_mock.call_args_list]
        self.assertEqual(status_request.full_url, "https://api.abacatepay.com/v2/transparents/check?id=pix_char_1")
        self.assertEqual(simulation_request.full_url, "https://api.abacatepay.com/v2/transparents/simulate-payment?id=pix_char_1")
        self.assertEqual(simulation_request.get_method(), "POST")
