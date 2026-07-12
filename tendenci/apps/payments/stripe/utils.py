import math

from django.conf import settings

from tendenci import __version__ as tendenci_version
from tendenci.apps.site_settings.utils import get_setting


def stripe_set_app_info(stripe):
    stripe.set_app_info(
    "Tendenci Stripe Plugin",
    version=tendenci_version,
    url="https://www.tendenci.com",
    partner_id="pp_partner_FcOFsMQDoGeT1B"
)


def configure_stripe(stripe_module):
    """Set API key, API version, and partner app info for Stripe requests."""
    stripe_module.api_key = getattr(settings, 'STRIPE_SECRET_KEY', '')
    stripe_module.api_version = settings.STRIPE_API_VERSION
    stripe_set_app_info(stripe_module)


def build_payment_intent_params(payment, currency, customer_id=None,
                                setup_future_usage=None):
    """Build PaymentIntent.create kwargs. Never set payment method types (use Dashboard dynamic methods)."""
    params = {
        'amount': math.trunc(payment.amount * 100),
        'currency': currency,
        'description': payment.description,
        'metadata': {
            'tendenci_payment_id': str(payment.id),
            'tendenci_payment_guid': payment.guid,
        },
    }

    if customer_id:
        params['customer'] = customer_id
    if setup_future_usage:
        params['setup_future_usage'] = setup_future_usage

    connected_account_id, scope = payment.invoice.stripe_connected_account()
    if connected_account_id:
        import stripe as stripe_module
        stripe_module.client_id = get_setting(
            'module', 'payments', 'stripe_connect_client_id')
        if scope == 'express':
            application_fee = payment.invoice.get_stripe_application_fee(
                payment.amount)
            params.update({
                'application_fee_amount': math.trunc(application_fee * 100),
                'transfer_data': {'destination': connected_account_id},
            })
        else:
            params['stripe_account'] = connected_account_id

    return params


def _charge_id_from_intent(payment_intent):
    latest_charge = getattr(payment_intent, 'latest_charge', None)
    if not latest_charge:
        return ''
    if isinstance(latest_charge, str):
        return latest_charge
    return getattr(latest_charge, 'id', '') or ''


def payment_update_from_intent(request, payment_intent, payment):
    """Approve a Payment from a succeeded PaymentIntent; store Charge id."""
    if getattr(payment_intent, 'status', None) == 'succeeded':
        payment.status_detail = 'approved'
        payment.response_code = '1'
        payment.response_subcode = '1'
        payment.response_reason_code = '1'
        payment.response_reason_text = (
            'This transaction has been approved. (Created# %s)'
            % payment_intent.created
        )
        payment.trans_id = _charge_id_from_intent(payment_intent)
    else:
        payment.response_code = 0
        payment.response_reason_code = 0
        payment.response_reason_text = (
            'PaymentIntent status=%s' % getattr(payment_intent, 'status', '')
        )

    if payment.is_approved:
        payment.mark_as_paid()
        payment.save()
        payment.invoice.make_payment(request.user, payment.amount)
    else:
        if payment.status_detail == '':
            payment.status_detail = 'not approved'
        payment.save()


def payment_update_stripe(request, charge_response, payment):
    if hasattr(charge_response,'paid') and charge_response.paid:
        payment.status_detail = 'approved'
        payment.response_code = '1'
        payment.response_subcode = '1'
        payment.response_reason_code = '1'
        payment.response_reason_text = 'This transaction has been approved. (Created# %s)' % charge_response.created
        payment.trans_id = charge_response.id
    else:
        payment.response_code = 0
        payment.response_reason_code = 0
        payment.response_reason_text = charge_response

    if payment.is_approved:
        payment.mark_as_paid()
        payment.save()
        payment.invoice.make_payment(request.user, payment.amount)
    else:
        if payment.status_detail == '':
            payment.status_detail = 'not approved'
        payment.save()
