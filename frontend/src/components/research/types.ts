export interface SessionResearchObject {
  id: string;
  session_id?: string | null;
  message_id?: string | null;
  type: string;
  title: string | null;
  content: string | null;
  content_json: Record<string, unknown>;
  created_by?: string | null;
  created_at: string;
}

export interface ResearchRelationCitation {
  source_id?: string;
  chunk_id?: string;
  snippet?: string;
  score?: number;
}

export interface ResearchRelationEvidence {
  trace_id?: string;
  citations?: ResearchRelationCitation[];
  note?: string;
}

export interface ResearchRelationMetadata {
  confidence?: number;
  evidence?: ResearchRelationEvidence;
  note?: string;
  trace_id?: string;
  citations?: ResearchRelationCitation[];
}

export interface SessionResearchObjectRelation {
  id: string;
  relation_type: 'supports' | 'contradicts';
  source_object_id: string;
  target_object_id: string;
  metadata_json: ResearchRelationMetadata;
  created_by: string | null;
  created_by_type: string;
  target_object: {
    id: string;
    type: string;
    title: string | null;
  };
  created_at: string;
}

export interface ResearchRelationSubmitPayload {
  relation_type: 'supports' | 'contradicts';
  target_object_id: string;
  metadata_json: {
    confidence: number;
    evidence: {
      trace_id?: string;
      citations: ResearchRelationCitation[];
      note?: string;
    };
  };
}
