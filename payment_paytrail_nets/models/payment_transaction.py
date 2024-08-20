import logging
import json
import uuid
import requests

from odoo import _, fields, models
from odoo.exceptions import ValidationError
from odoo.http import request

from odoo.addons.payment import utils as payment_utils
from odoo.addons.payment_paytrail_nets.controllers.main import PaytrailController

_logger = logging.getLogger(__name__)


class PaymentTransaction(models.Model):
    _inherit = "payment.transaction"

    paytrail_checkout_stamp = fields.Char(
        string="Paytrail checkout stamp",
        readonly=True,
    )

    paytrail_checkout_account = fields.Char(
        string="Paytrail checkout account",
        readonly=True,
    )

    paytrail_checkout_provider = fields.Char(
        string="Paytrail checkout provider",
        readonly=True,
    )

    def _paytrail_form_validate(self, data):
        """
        Validate transaction

        :param data: dict
        :return: None
        """
        _logger.debug(f"Paytrail response data: {data}")
        paytrail_status = data.get("checkout-status")

        res = {
            "provider_reference": data.get("checkout-transaction-id"),
            "paytrail_checkout_stamp": data.get("checkout-stamp"),
            "paytrail_checkout_account": data.get("checkout-account"),
            "paytrail_checkout_provider": data.get("checkout-provider"),
        }
        self.write(res)

        if paytrail_status == "fail":
            _logger.info(
                _("Paytrail payment for tx %s: set as canceled", self.reference)
            )
            self._set_canceled()
        elif paytrail_status in ["pending", "delayed"]:
            _logger.info(
                _("Paytrail payment for tx %s: set as pending", self.reference)
            )
            self._set_pending()
        elif paytrail_status == "ok":
            _logger.info(_("Paytrail payment for tx %s: set as done", self.reference))
            self._set_done()
        else:
            error = _(
                "Received unrecognized response for Paytrail payment %s, set as error",
                self.reference,
            )
            _logger.error(error)
            self._set_error(error)

        return

    def _get_paytrail_urlset(self):
        """
        Get Paytrail urlset

        :return: dict
        """
        base_url = self.provider_id.paytrail_base_url
        res = {
            "success": f"{base_url}{PaytrailController._success_url}",
            "cancel": f"{base_url}{PaytrailController._cancel_url}",
        }
        return res

    def _get_payment_language(self, values):
        """
        Set payment language for Paytrail

        :param values: dict
        :return: string, language code
        """
        language = False
        if "billing_partner" in values:
            language = values["billing_partner"].lang[0:2].upper()

        # Valid languages
        if language in ["EN", "FI", "SE"]:
            return language
        else:
            return "EN"

    def _form_paytrail_payment_json(self, values):
        """
        Forms paytrail payment params, supports fetching data from either
        - Sale Order (primary, always attempted first)
        - Invoice (attempted second if
          a) no linked SO exists, and
          b) this option has been enabled in payment acquirer settings

        Invoice-based logic is intended for situations where the invoice is created
        from e.g. a contract, so a related Sale Order does not exist, and you still
        want to send a payment link to the customer.

        :param values: dict
        :return: JSON string
        """
        if "reference" in values:
            reference = values["reference"]

            if (not reference or reference == "/") and request.website is not None:
                reference = request.website.sale_get_order(self._context).name
            if reference:
                values["reference"] = reference
            else:
                values["reference"] = ""

        transaction = self.env["payment.transaction"].search(
            [
                ("reference", "=", values["reference"]),
                ("state", "in", ["draft", "pending"]),
            ],
            order="create_date DESC",
            limit=1,
        )

        # Put together payment data that is common, regardless if data is fetched
        # from SO or invoice
        urlset = self._get_paytrail_urlset()
        res = {
            "stamp": str(uuid.uuid4()),
            "reference": values["reference"],
            "language": self._get_payment_language(values),
            "redirectUrls": urlset,
            "callbackUrls": urlset,
            "usePricesWithoutVat": False,
        }

        if len(transaction.sale_order_ids) == 1:
            # Check SO primarily
            res = self._form_paytrail_payment_json_from_sale_order(transaction, res)

        else:
            # If SO not found, check invoice second, if configured in settings.
            if not self.provider_id.paytrail_send_invoice_data_if_no_sale_order:
                raise ValidationError(_("Only one sale order for payment is supported"))

            _logger.debug(
                "No invoice found and 'paytrail_send_invoice_data_if_no_sale_order' "
                "is enabled. Starting to look for a matching Invoice..."
            )

            if len(transaction.invoice_ids) != 1:
                raise ValidationError(_("Only one invoice for payment is supported"))

            res = self._form_paytrail_payment_json_from_invoice(transaction, res)

        # Check if a separate item for rounding should be added
        item_prices_total = sum(
            (item["unitPrice"] * item["units"]) for item in res["items"]
        )
        amount_difference = res["amount"] - item_prices_total

        if amount_difference != 0 and len(res["items"]) > 0:
            _logger.debug(
                "Total amount was %s, items' summed prices were %s. Adding a "
                "separate rounding item...",
                res["amount"],
                item_prices_total,
            )
            res = self._append_rounding_item(res, amount_difference)
        else:
            _logger.debug(
                "Total amount and items's summed prices match, rounding item not needed."
            )

        return json.dumps(res, separators=(",", ":"))

    def _append_rounding_item(self, res, amount_difference):
        """
        Add a new item to account for the possible rounding difference between:
        1) the total amount that was taken directly from SO or Invoice, and
        2) the summed individual items' prices, that were taken from SO/Invoice lines
           and divided by the line quantity.

        This ensures payment validation will not fail due to rounding errors.

        :param res: dict to be sent to paytrail, without the rounding item
        :param amount_difference: rounding difference to be added
        :return: dict to be sent to paytrail, with the rounding item added
        """

        rounding_item = {
            "unitPrice": amount_difference,
            "units": 1,
            "vatPercentage": 0,
            "productCode": "ITEM_ROUNDING",
        }

        _logger.debug("Added rounding item: %s", rounding_item)
        res["items"].append(rounding_item)

        return res

    def _form_paytrail_payment_json_from_sale_order(self, transaction, res):
        """
        Form Paytrail payload from sale order

        :param transaction: payment.transaction
        :param res: payment dict to be sent to paytrail
        :return: dict
        """
        order = transaction.sale_order_ids[0]
        items = self._get_paytrail_items_from_sale_order(order)

        # Customer
        partner = order.partner_id
        first_name, last_name = payment_utils.split_partner_name(partner.name)

        res.update(
            {
                "amount": payment_utils.to_minor_currency_units(
                    order.amount_total, self.currency_id
                ),
                "currency": order.currency_id.name,
                "orderId": order.name,
                "items": items,
                "customer": {
                    "email": partner.email,
                    "firstName": first_name,
                    "lastName": last_name,
                    "phone": partner.phone or "",
                    "vatId": partner.vat or "",
                },
                "deliveryAddress": {
                    "streetAddress": order.partner_shipping_id.street[0:50],
                    "postalCode": order.partner_shipping_id.zip,
                    "city": order.partner_shipping_id.city[0:30],
                    "country": order.partner_shipping_id.country_id.code,
                },
                "invoicingAddress": {
                    "streetAddress": order.partner_invoice_id.street[0:50],
                    "postalCode": order.partner_invoice_id.zip,
                    "city": order.partner_invoice_id.city[0:30],
                    "country": order.partner_invoice_id.country_id.code,
                },
            }
        )
        return res

    def _form_paytrail_payment_json_from_invoice(self, transaction, res):
        """
        Form Paytrail payload from invoice

        :param transaction: payment.transaction
        :param res: payment dict to be sent to paytrail
        :return: dict
        """

        invoice = transaction.invoice_ids[0]
        items = self._get_paytrail_items_from_invoice(invoice)

        # Customer
        partner = invoice.partner_id
        first_name, last_name = payment_utils.split_partner_name(partner.name)

        # For delivery address, fall back to partner, if separate delivery address
        # field is not set
        shipping_partner = invoice.partner_shipping_id or invoice.partner_id

        res.update(
            {
                "amount": payment_utils.to_minor_currency_units(
                    invoice.amount_total, self.currency_id
                ),
                "currency": invoice.currency_id.name,
                "orderId": invoice.name,
                "items": items,
                "customer": {
                    "email": partner.email,
                    "firstName": first_name,
                    "lastName": last_name,
                    "phone": partner.phone or "",
                    "vatId": partner.vat or "",
                },
                "deliveryAddress": {
                    "streetAddress": shipping_partner.street[0:50],
                    "postalCode": shipping_partner.zip,
                    "city": shipping_partner.city[0:30],
                    "country": shipping_partner.country_id.code,
                },
                "invoicingAddress": {
                    "streetAddress": invoice.partner_id.street[0:50],
                    "postalCode": invoice.partner_id.zip,
                    "city": invoice.partner_id.city[0:30],
                    "country": invoice.partner_id.country_id.code,
                },
            }
        )
        return res

    def _get_paytrail_items_from_sale_order(self, order):
        """
        Get items for Paytrail payload from sale order lines

        :param order: sale.order
        :return: list
        """
        items = []
        for line in order.order_line:
            vat_percent = sum(line.tax_id.mapped("amount"))
            quantity = int(round(line.product_uom_qty, 0))
            items.append(
                {
                    "unitPrice": round(line.price_total * 100 / quantity),
                    "units": quantity,
                    "vatPercentage": vat_percent,
                    "productCode": line.product_id.default_code
                    or str(line.product_id.id),
                    "description": line.product_id.name,
                    "category": line.product_id.categ_id.display_name,
                    # Shop-in-Shop payments
                    # "orderId":
                    # "stamp":
                    # "reference":
                    # "merchant":
                    # "commission":
                }
            )
        return items

    def _get_paytrail_items_from_invoice(self, invoice):
        """
        Get items for Paytrail payload from invoice lines

        :param invoice: account.move
        :return: list
        """

        items = []
        for line in invoice.invoice_line_ids:
            # Ignore note lines
            if line.display_type == "line_note":
                continue

            vat_percent = sum(line.tax_ids.mapped("amount"))
            quantity = int(round(line.quantity, 0))
            items.append(
                {
                    "unitPrice": round(line.price_total * 100 / quantity),
                    "units": quantity,
                    "vatPercentage": int(vat_percent),
                    "productCode": line.product_id.default_code
                    or str(line.product_id.id),
                    "description": line.product_id.name,
                    "category": line.product_id.categ_id.display_name,
                    # Shop-in-Shop payments
                    # "orderId":
                    # "stamp":
                    # "reference":
                    # "merchant":
                    # "commission":
                }
            )

        return items

    def _get_paytrail_url_token(self, payload):
        """
        Create a new payment with Paytrail API

        :param payload: dict
        :return: dict
        """
        headers = self.provider_id._get_paytrail_headers(payload)
        uri = "https://services.paytrail.com/payments"
        _logger.debug(f"Payload: {payload}")
        _logger.debug(f"Headers: {headers}")

        r = requests.post(uri, headers=headers, data=payload)

        if r.status_code == 201:
            data = r.json()
            return data
        else:
            res = r.json()

            try:
                msg = f"Error: {res['message']}"
                _logger.error(msg)
            except Exception as e:
                msg = "Unknown error: %s" % e
                _logger.error(msg)

        return res

    def _get_specific_rendering_values(self, processing_values):
        """
        Override of payment to return Paytrail-specific rendering values.

        :param processing_values: dict
        :return: dict
        """
        res = super()._get_specific_rendering_values(processing_values)
        if self.provider_code != "paytrail":
            return res

        paytrail_tx_values = dict(processing_values)
        payload = self._form_paytrail_payment_json(paytrail_tx_values)
        _logger.debug(f"Payload: {payload}")

        token = self._get_paytrail_url_token(payload)
        _logger.debug(f"Token: {token}")

        if token.get("status") == "error":
            raise ValidationError(token.get("message"))
        else:
            paytrail_tx_values[
                "paytrail_url"
            ] = f"/payment/paytrail/redirect?url={token.get('href')}"

        _logger.debug(f"TX values: {paytrail_tx_values}")
        return paytrail_tx_values

    def _get_tx_from_notification_data(self, provider_code, notification_data):
        """Override of payment to find the transaction based on Paytrail data.

        :param str provider_code: The code of the provider that handled the transaction
        :param dict notification_data: The notification data sent by the provider
        :return: The transaction if found
        :rtype: recordset of `payment.transaction`
        :raise: ValidationError if inconsistent data were received
        :raise: ValidationError if the data match no transaction
        """
        tx = super()._get_tx_from_notification_data(provider_code, notification_data)
        if provider_code != "paytrail" or len(tx) == 1:
            return tx

        reference = notification_data.get("checkout-reference")
        txn_id = notification_data.get("checkout-transaction-id")
        if not reference or not txn_id:
            raise ValidationError(
                "Paytrail: "
                + _(
                    "Received data with missing reference %(r)s or txn_id %(t)s.",
                    r=reference,
                    t=txn_id,
                )
            )

        tx = self.search(
            [("reference", "=", reference), ("provider_code", "=", "paytrail")]
        )
        if not tx:
            raise ValidationError(
                "Paytrail: "
                + _("No transaction found matching reference %s.", reference)
            )

        return tx

    def _process_notification_data(self, notification_data):
        """Override of payment to process the transaction based on Paytrail data.

        Note: self.ensure_one()

        :param dict notification_data: The notification data sent by the provider
        :return: None
        :raise: ValidationError if inconsistent data were received
        """
        _logger.debug(f"Received notification data:\n{notification_data}")
        super()._process_notification_data(notification_data)
        if self.provider_code != "paytrail":
            return

        self._paytrail_form_validate(notification_data)
