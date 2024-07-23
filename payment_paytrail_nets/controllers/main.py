import werkzeug
import logging
import hmac
from werkzeug.exceptions import Forbidden

from odoo import http
from odoo.http import request

_logger = logging.getLogger(__name__)


class PaytrailController(http.Controller):
    """Handles responses from Paytrail"""

    _success_url = "/payment/paytrail/success"
    _cancel_url = "/payment/paytrail/cancel"

    @http.route(
        [_success_url, _cancel_url],
        type="http",
        auth="public",
    )
    def paytrail_return_from_checkout(self, **data):
        """ """
        _logger.info(f"Handling redirection from Paytrail with data\n{data}")
        tx_sudo = (
            request.env["payment.transaction"]
            .sudo()
            ._get_tx_from_notification_data("paytrail", data)
        )
        self._verify_notification_signature(data, tx_sudo)
        _logger.debug(f"Signature {data['signature']} valid!")
        tx_sudo._handle_notification_data("paytrail", data)
        return request.redirect("/payment/status")

    @staticmethod
    def _verify_notification_signature(notification_data, tx_sudo):
        """Check that the received signature matches the expected one.

        :param dict notification_data: The notification data
        :param recordset tx_sudo: The sudoed transaction referenced by the notification data, as a
                                  `payment.transaction` record
        :return: None
        :raise: :class:`werkzeug.exceptions. Forbidden` if the signatures don't match
        """
        # Retrieve the received signature from the data
        received_signature = notification_data.get("signature")
        if not received_signature:
            _logger.warning("Received notification with missing signature")
            raise Forbidden()

        # Compare the received signature with the expected signature computed from the data
        expected_signature = tx_sudo.provider_id._paytrail_compute_signature(
            notification_data, ""
        )
        if not hmac.compare_digest(received_signature, expected_signature):
            _logger.warning("Received notification with invalid signature")
            raise Forbidden()

    @http.route(
        ["/payment/paytrail/redirect"],
        type="http",
        auth="public",
        csrf=False,
    )
    def paytrail_redirect(self, url, **kwargs):
        return werkzeug.utils.redirect(url)
