from sqlalchemy import CheckConstraint, UniqueConstraint

from app.core.database import Base
from app.models.knowledge_governance import (
    KnowledgeChangeEvent,
    KnowledgeSuggestion,
    ResearchDirectionSteward,
    ResearchGroupSteward,
)
from app.models.research_direction import ResearchDirection, ResearchDirectionRelation
from app.models.research_direction_link import (
    MemberResearchDirection,
    ProjectResearchDirection,
    ResearchAssetDirection,
    ResearchObjectDirection,
)


def test_lab_knowledge_tables_are_registered() -> None:
    assert {
        "research_directions",
        "research_direction_relations",
        "member_research_directions",
        "project_research_directions",
        "research_asset_directions",
        "research_object_directions",
        "research_group_stewards",
        "research_direction_stewards",
        "knowledge_suggestions",
        "knowledge_change_events",
    } <= set(Base.metadata.tables)


def test_direction_relation_has_order_and_uniqueness_constraints() -> None:
    table = ResearchDirectionRelation.__table__
    assert any(isinstance(item, CheckConstraint) for item in table.constraints)
    assert any(isinstance(item, UniqueConstraint) for item in table.constraints)


def test_steward_tables_use_foreign_keys_instead_of_polymorphic_scope_ids() -> None:
    assert "group_id" in ResearchGroupSteward.__table__.c
    assert "direction_id" in ResearchDirectionSteward.__table__.c
    assert KnowledgeSuggestion.__table__.c.target_id.nullable
    assert not KnowledgeChangeEvent.__table__.c.entity_id.nullable
