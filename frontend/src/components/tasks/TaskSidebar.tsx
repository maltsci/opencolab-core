import { CheckCircleOutlined, ClockCircleOutlined, FolderOpenOutlined, MessageOutlined } from '@ant-design/icons';
import { Button, Card, Descriptions, Space, Tag, Typography } from 'antd';

const { Paragraph, Text } = Typography;

interface TaskSidebarProps {
  projectName: string;
  projectDescription?: string | null;
  taskName: string;
  taskIdLabel: string;
  sessionId: string | null;
  sessionTitle: string | null;
  sessionMessageCount: number;
  runStatusLabel: string | null;
  runStatusColor: 'default' | 'success' | 'processing' | 'error' | 'warning' | undefined;
  hasDraft: boolean;
  draftSavedAtLabel: string | null;
  sessionReady: boolean;
  openSessionLabel: string;
  backLabel: string;
  projectLabel: string;
  projectMaterialsLabel: string;
  taskParametersLabel: string;
  outputTargetLabel: string;
  saveResultsLabel: string;
  fullConversationLabel: string;
  requestSummaryLabel: string;
  requiredInputsLabel: string;
  inputRequiredNoneLabel: string;
  taskNameLabel: string;
  taskIdTextLabel: string;
  runLabel: string;
  progressDetailLabel: string;
  draftSavedLabel: string;
  draftEmptyLabel: string;
  sessionPendingLabel: string;
  projectHint: string;
  projectMaterialsSummary: string;
  projectMaterialsHint: string;
  requestSummary: string;
  requiredInputsSummary: string[];
  outputTargetSummary: string;
  outputTargetHint: string;
  saveResultsHint: string;
  sessionHint: string;
  draftHint: string;
  showRuntimeSections: boolean;
  onOpenSession: () => void;
  onBackHome: () => void;
}

export default function TaskSidebar({
  projectName,
  projectDescription,
  taskName,
  taskIdLabel,
  sessionId,
  sessionTitle,
  sessionMessageCount,
  runStatusLabel,
  runStatusColor,
  hasDraft,
  draftSavedAtLabel,
  sessionReady,
  openSessionLabel,
  backLabel,
  projectLabel,
  projectMaterialsLabel,
  taskParametersLabel,
  outputTargetLabel,
  saveResultsLabel,
  fullConversationLabel,
  requestSummaryLabel,
  requiredInputsLabel,
  inputRequiredNoneLabel,
  taskNameLabel,
  taskIdTextLabel,
  runLabel,
  progressDetailLabel,
  draftSavedLabel,
  draftEmptyLabel,
  sessionPendingLabel,
  projectHint,
  projectMaterialsSummary,
  projectMaterialsHint,
  requestSummary,
  requiredInputsSummary,
  outputTargetSummary,
  outputTargetHint,
  saveResultsHint,
  sessionHint,
  draftHint,
  showRuntimeSections,
  onOpenSession,
  onBackHome,
}: TaskSidebarProps) {
  return (
    <Space orientation="vertical" size={16} style={{ width: '100%' }}>
      <Card size="small" title={projectLabel}>
        <Descriptions column={1} size="small" colon={false}>
          <Descriptions.Item label={projectLabel}>{projectName}</Descriptions.Item>
        </Descriptions>
        {projectDescription ? (
          <Paragraph type="secondary" style={{ marginBottom: 8 }}>
            {projectDescription}
          </Paragraph>
        ) : null}
        <Paragraph type="secondary" style={{ marginBottom: 0 }}>
          {projectHint}
        </Paragraph>
      </Card>

      <Card size="small" title={projectMaterialsLabel}>
        <Space orientation="vertical" size={12} style={{ width: '100%' }}>
          <Paragraph style={{ marginBottom: 0 }}>{projectMaterialsSummary}</Paragraph>
          <Paragraph type="secondary" style={{ marginBottom: 0 }}>
            {projectMaterialsHint}
          </Paragraph>
        </Space>
      </Card>

      <Card size="small" title={taskParametersLabel}>
        <Space orientation="vertical" size={12} style={{ width: '100%' }}>
          <Descriptions column={1} size="small" colon={false}>
            <Descriptions.Item label={taskNameLabel}>{taskName}</Descriptions.Item>
            <Descriptions.Item label={taskIdTextLabel}>{taskIdLabel}</Descriptions.Item>
            <Descriptions.Item label={requestSummaryLabel}>{requestSummary}</Descriptions.Item>
            <Descriptions.Item label={requiredInputsLabel}>
              {requiredInputsSummary.length > 0 ? (
                <Space size={[6, 6]} wrap>
                  {requiredInputsSummary.map((item) => <Tag key={item}>{item}</Tag>)}
                </Space>
              ) : (
                <Text type="secondary">{inputRequiredNoneLabel}</Text>
              )}
            </Descriptions.Item>
          </Descriptions>
        </Space>
      </Card>

      <Card size="small" title={outputTargetLabel}>
        <Space orientation="vertical" size={8} style={{ width: '100%' }}>
          <Paragraph style={{ marginBottom: 0 }}>{outputTargetSummary}</Paragraph>
          <Paragraph type="secondary" style={{ marginBottom: 0 }}>
            {outputTargetHint}
          </Paragraph>
        </Space>
      </Card>

      {showRuntimeSections ? (
        <Card size="small" title={saveResultsLabel}>
          <Space orientation="vertical" size={8} style={{ width: '100%' }}>
            <Tag color={hasDraft ? 'blue' : 'default'}>
              {hasDraft ? draftSavedLabel : draftEmptyLabel}
            </Tag>
            {draftSavedAtLabel ? <Text type="secondary">{draftSavedAtLabel}</Text> : null}
            <Paragraph type="secondary" style={{ marginBottom: 0 }}>
              {saveResultsHint}
            </Paragraph>
            <Paragraph type="secondary" style={{ marginBottom: 0 }}>
              {draftHint}
            </Paragraph>
          </Space>
        </Card>
      ) : null}

      {showRuntimeSections ? (
        <Card size="small" title={fullConversationLabel}>
          <Space orientation="vertical" size={12} style={{ width: '100%' }}>
            <Space size={8} wrap>
              <Tag icon={sessionReady ? <CheckCircleOutlined /> : <ClockCircleOutlined />} color={sessionReady ? 'success' : 'default'}>
                {sessionReady ? sessionId : sessionPendingLabel}
              </Tag>
              <Tag icon={<MessageOutlined />}>{sessionMessageCount}</Tag>
              {runStatusLabel ? <Tag color={runStatusColor}>{runStatusLabel}</Tag> : null}
            </Space>
            <Descriptions column={1} size="small" colon={false}>
              <Descriptions.Item label={fullConversationLabel}>{sessionTitle || '-'}</Descriptions.Item>
              <Descriptions.Item label={runLabel}>{progressDetailLabel}</Descriptions.Item>
            </Descriptions>
            <Paragraph type="secondary" style={{ marginBottom: 0 }}>
              {sessionHint}
            </Paragraph>
            <Button
              type="primary"
              icon={<FolderOpenOutlined />}
              onClick={onOpenSession}
              disabled={!sessionReady || !sessionId}
              block
            >
              {openSessionLabel}
            </Button>
          </Space>
        </Card>
      ) : null}

      <Button onClick={onBackHome} block>
        {backLabel}
      </Button>
    </Space>
  );
}
