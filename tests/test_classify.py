import pytest
from beanbot.services.agent.classify import Classification, route_classification


@pytest.mark.parametrize(('intent', 'confidence', 'route'), [
    ('record', .9, 'record'), ('query', .9, 'query'), ('budget', .9, 'budget'),
    ('other', .9, 'ask'), ('record', .5, 'ask'),
])
def test_classification_routes(intent, confidence, route):
    assert route_classification(Classification(intent=intent, confidence=confidence)) == route