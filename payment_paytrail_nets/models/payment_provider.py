import logging
import requests
import uuid
import hmac
import hashlib

from odoo import api, fields, models, _

_logger = logging.getLogger(__name__)


class PaymentProvider(models.Model):
    _inherit = "payment.provider"

    code = fields.Selection(
        selection_add=[("paytrail", "Paytrail")], ondelete={"paytrail": "set default"}
    )

    paytrail_merchant_id = fields.Char(
        string="Merchant ID",
        required_if_provider="paytrail",
    )
    paytrail_merchant_secret = fields.Char(
        string="Merchant secret",
        required_if_provider="paytrail",
    )
    paytrail_base_url = fields.Char(
        string="Return address",
        default=lambda self: self._get_default_base_url(),
        required_if_provider="paytrail",
    )
    paytrail_send_invoice_data_if_no_sale_order = fields.Boolean(
        string="Send Invoice Data if no Sale Order Exists",
        default=True,
        help="When sending data to Paytrail, if a related Sale Order does not exist, "
        "look for customer, monetary amount etc. data from a related Invoice instead. "
        "Can be toggled on if dealing with e.g. invoices that have originated from "
        "Contracts and do not have a Sale Order.",
    )

    def _get_default_base_url(self):
        return self.env["ir.config_parameter"].get_param("web.base.url")

    def _get_paytrail_headers(self, payload):
        """
        Get Paytrail headers

        :param payload: dict
        :return: dict
        """
        headers = {
            "checkout-account": str(self.paytrail_merchant_id),
            "checkout-algorithm": "sha256",
            "checkout-method": "GET",
            "checkout-nonce": str(uuid.uuid4()),
            "checkout-timestamp": fields.Datetime.now().isoformat(),
            "platform-name": "futural_odoo",
        }

        if payload != "":
            # If request has a body, set content type and change checkout method to POST
            headers["content-type"] = "application/json; charset=utf-8"
            headers["checkout-method"] = "POST"

        headers["signature"] = self._paytrail_compute_signature(headers, payload)
        return headers

    def _paytrail_compute_signature(self, headers, payload):
        """
        Get Paytrail HMAC signature

        :param headers: dict
        :param payload: dict
        :return: string
        """
        # Calculation uses all headers named "checkout-" in alphabetical order
        checkout_headers = [k for k, v in headers.items() if k.startswith("checkout-")]
        checkout_headers.sort()

        hmac_string = "\n".join(f"{key}:{headers[key]}" for key in checkout_headers)
        hmac_string += f"\n{payload}"
        signature = hmac.new(
            self.paytrail_merchant_secret.encode("utf-8"),
            hmac_string.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()
        return signature

    def action_paytrail_update_method_brands(self):
        self.ensure_one()

        self.env.ref("payment.payment_method_paytrail").active = True

        headers = self._get_paytrail_headers("")
        r = requests.get(
            "https://services.paytrail.com/merchants/payment-providers", headers=headers
        )

        if r.status_code == 200:
            paytrail_methods = r.json()
            _logger.info(_("Found %s supported payment methods", len(paytrail_methods)))
            payment_method = self.env["payment.method"]

            active_methods = []
            for paytrail_method in paytrail_methods:
                method_id = payment_method.with_context(active_test=False).search(
                    [
                        "|",
                        ("name", "=ilike", paytrail_method.get("name")),
                        ("code", "=ilike", paytrail_method.get("name")),
                    ]
                )
                if method_id:
                    paytrail_method = self.env.ref("payment.payment_method_paytrail")
                    if (
                        not method_id.active
                        and method_id.primary_payment_method_id != paytrail_method
                    ):
                        # Change the payment method for this brand
                        method_id.primary_payment_method_id = paytrail_method.id

                    method_id.active = True
                    active_methods.append(method_id.name)
                else:
                    _logger.warning(
                        _(
                            "Could not find payment method %s",
                            paytrail_method.get("name"),
                        )
                    )
        else:
            _logger.error(_("Error while fetching providers: %s", r.text))

        title = _("Payment method brands enabled!")
        message = ", ".join(active_methods)
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": title,
                "message": message,
                "sticky": False,
            },
        }
