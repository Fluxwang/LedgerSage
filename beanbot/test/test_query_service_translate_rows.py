from beanbot.services.query_service import QueryService
from beanbot.gateways.beancount_repo import BeancountRepository
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
repo = BeancountRepository(filename="my_ledger.bean", currency="CNY", logger=logger)

query_service = QueryService(repo)

# print(json.dumps(asdict(query_service.fetch_expense()), ensure_ascii=False, indent=2))
print(query_service.fetch_expense())
