from beanbot.gateways.beancount_repo import BeancountRepository
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
repo = BeancountRepository(filename="my_ledger.bean", currency="CNY", logger=logger)

result = repo.run_query("SELECT account, sum(position) WHERE account ~ 'Expenses'")
print(result)
