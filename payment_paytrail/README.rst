.. image:: https://img.shields.io/badge/licence-LGPL--3-blue.svg
   :target: http://www.gnu.org/licenses/lgpl-3.0-standalone.html
   :alt: License: LGPL-3

==========================
Payment Provider: Paytrail
==========================

Payment Provider for Paytrail.
Supports VAT with decimals, e.g. 25,5%.

Please note that as the module is open source and free to use,
any warranty or support is not included.

Configuration
=============
1. **Activate** the module "Payment Provider: Paytrail" from Apps
2. **Select** Paytrail in Payment Providers configuration.
3. **Setup** your *Merchant ID* and *Merchant Secret*. Check that *Return address* matches your installation address
4. **Select** Payment methods in *Configuration*-tab, or click *Auto-enable* to do it automatically
5. **Enable** Paytrail as payment method

Good to go!
You can limit availability to certain countries, if necessary.

Usage
=====
Select as a payment method when paying your order.

Issues
======
Please report issues in
https://github.com/Tawasta/paytrail/issues

Roadmap
=======
* Add support for Refunds (POST /payments/{transactionId}/refund)
* Add support Payment page bypass
* Add support for shop-in-shop

Credits
=======

Contributors
------------

* Aleksi Savijoki <aleksi.savijoki@tawasta.fi>
* Jaakko Komulainen <jaakko.komulainen@vizucom.com>
* Jarmo Kortetjärvi <jarmo.kortetjarvi@tawasta.fi>
* Valtteri Lattu <valtteri.lattu@tawasta.fi>
* Timo Talvitie <timo.talvitie@tawasta.fi>

Maintainer
----------

.. image:: https://tawasta.fi/templates/tawastrap/images/logo.png
   :alt: Oy Tawasta OS Technologies Ltd.
   :target: https://tawasta.fi/

This module is maintained by Oy Tawasta OS Technologies Ltd.
