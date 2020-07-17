from celery import shared_task
from celery.utils.log import get_task_logger

from charged.lninvoice.models import PurchaseOrderInvoice
from charged.lnnode.models import get_all_nodes
from charged.lnpurchase.models import PurchaseOrder
from shop.models import TorDenyList

logger = get_task_logger(__name__)


@shared_task()
def process_initial_purchase_order(obj_id):
    logger.info('Running on ID: %s' % obj_id)

    # checks
    obj: PurchaseOrder = PurchaseOrder.objects \
        .filter(id=obj_id) \
        .filter(status=PurchaseOrder.INITIAL) \
        .first()

    if not obj:
        logger.info('Not found')
        return None

    if not obj.total_price_msat:
        logger.info('No total price - skipping: %s' % obj)
        return None

    # ToDo(frennkie) this should not live in Django Charged
    target_with_port = obj.item_details.first().product.target
    try:
        target = target_with_port.split(':')[0]
    except IndexError:
        target = target_with_port

    if TorDenyList.objects.filter(is_denied=True).filter(target=target):
        logger.info('Target is on Deny List: %s' % target)
        obj.status = PurchaseOrder.REJECTED
        obj.message = "Target is on Deny List"
        obj.save()
        return None

    # ToDo(frennkie) check this!
    owned_nodes = get_all_nodes(obj.owner.id)
    for node_tuple in owned_nodes:
        node = node_tuple[1]
        if node.is_enabled:
            invoice = PurchaseOrderInvoice(label="PO: {}".format(obj.id),
                                           msatoshi=obj.total_price_msat,
                                           lnnode=node)

            invoice.save()
            obj.ln_invoices.add(invoice)

            obj.status = PurchaseOrder.NEEDS_TO_BE_PAID
            obj.save()

            logger.info('Created LnInvoice: %s (%s)' % (invoice.id, invoice))

            break

    else:
        raise RuntimeError("no owned nodes found")

    return invoice.id
