##############################################################################
#
#    Author: Oy Tawasta OS Technologies Ltd.
#    Copyright 2013- Tawasta Oy (https://tawasta.fi)
#
#    This program is free software: you can redistribute it and/or modify
#    it under the terms of the GNU Lesser General Public License as
#    published by the Free Software Foundation, either version 3 of the
#    License, or (at your option) any later version.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
#    GNU Lesser General Public License for more details.
#
#    You should have received a copy of the GNU Lesser General Public License
#    along with this program. If not, see http://www.gnu.org/licenses/lgpl.html.
#
##############################################################################

{
    "name": "Payment Provider: Paytrail",
    "summary": "Add Paytrail as a payment provider",
    "version": "17.0.1.2.1",
    "development_status": "Production/Stable",
    "category": "Accounting/Payment Providers",
    "website": "https://github.com/Tawasta/paytrail",
    "author": "Tawasta",
    "license": "LGPL-3",
    "depends": ["payment"],
    "data": [
        "view/payment_method_template.xml",
        "view/payment_provider_views.xml",
        "view/payment_template.xml",
        "data/payment_provider_data.xml",
        "data/payment_method_data.xml",
    ],
    "images": ["static/description/banner.png"],
    "demo": [],
    "installable": True,
    "post_init_hook": "post_init_hook",
    "uninstall_hook": "uninstall_hook",
    "application": False,
}
