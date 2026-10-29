from app.schemas.workflow import WorkflowDefinition, WorkflowStepDefinition


LITERATURE_SYNTHESIZER_WORKFLOW = WorkflowDefinition(
    id="literature_synthesizer",
    name="Literature Synthesizer",
    description="Retrieve, synthesize, validate, and format literature insights.",
    steps=[
        WorkflowStepDefinition(
            id="retrieve",
            type="skill",
            ref="rag-retrieve",
            output_key="retrieved_chunks",
        ),
        WorkflowStepDefinition(
            id="synthesize",
            type="skill",
            ref="literature-synthesize",
            depends_on=["retrieve"],
            output_key="synthesis",
        ),
        WorkflowStepDefinition(
            id="validate",
            type="skill",
            ref="grounding-validate",
            depends_on=["synthesize"],
            output_key="validation",
        ),
        WorkflowStepDefinition(
            id="format_output",
            type="skill",
            ref="format-output",
            depends_on=["validate"],
            output_key="final_output",
        ),
    ],
)

REVIEWER_ASSISTANT_WORKFLOW = WorkflowDefinition(
    id="reviewer_assistant",
    name="Reviewer Assistant",
    description="Retrieve context, draft reviewer responses, validate grounding, and format output.",
    steps=[
        WorkflowStepDefinition(
            id="retrieve",
            type="skill",
            ref="rag-retrieve",
            output_key="retrieved_chunks",
        ),
        WorkflowStepDefinition(
            id="draft_response",
            type="skill",
            ref="reviewer-response-draft",
            depends_on=["retrieve"],
            output_key="draft",
        ),
        WorkflowStepDefinition(
            id="validate",
            type="skill",
            ref="grounding-validate",
            depends_on=["draft_response"],
            output_key="validation",
        ),
        WorkflowStepDefinition(
            id="format_output",
            type="skill",
            ref="format-output",
            depends_on=["validate"],
            output_key="final_output",
        ),
    ],
)

BUILTIN_WORKFLOW_DEFINITIONS = [
    LITERATURE_SYNTHESIZER_WORKFLOW,
    REVIEWER_ASSISTANT_WORKFLOW,
]
