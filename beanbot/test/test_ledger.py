from beanbot.services.ledger_service import LedgerService
from beanbot.gateways.beancount_repo import BeancountRepository
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
repo = BeancountRepository(filename="my_ledger.bean", currency="CNY", logger=logger)
settings = "test"
service = LedgerService(settings, repo, None)
tx = service.build_transaction(["100", "CMB", "Food", "KFC", "午餐", "#lunch"])
print(tx)
