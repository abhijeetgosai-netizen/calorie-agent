import pytest

from calorie_agent.agent.core import CalorieAgent
from calorie_agent.agent.graph import Deps
from calorie_agent.db.repo import Repository
from calorie_agent.db.session import make_engine, migrate
from calorie_agent.nutrition.service import NutritionService
from tests.fakes import EGG, RICE, FakeLLM, FakeSource


@pytest.fixture
def engine(tmp_path):
    url = f"sqlite:///{tmp_path}/test.db"
    migrate(url)
    return make_engine(url)


@pytest.fixture
def repo(engine):
    return Repository(engine)


@pytest.fixture
def llm():
    return FakeLLM()


@pytest.fixture
def source():
    return FakeSource({"egg": EGG, "rice": RICE})


@pytest.fixture
def agent(engine, repo, llm, source):
    nutrition = NutritionService(engine, [source], llm.estimate)
    return CalorieAgent(Deps(repo=repo, llm=llm, nutrition=nutrition))


@pytest.fixture
def uid(agent):
    return agent.user_id_for(42)
