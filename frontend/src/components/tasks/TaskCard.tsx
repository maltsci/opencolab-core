import { DatabaseOutlined, FileSearchOutlined, SaveOutlined } from '@ant-design/icons';
import { Button, Space, Tag, Typography, theme } from 'antd';

import SectionCard from '../ui/SectionCard';
import { getTaskRuntimeKind, type TaskDefinition } from '../../types/task';

const { Paragraph, Text, Title } = Typography;

interface TaskCardProps {
  task: TaskDefinition;
  onStart: (task: TaskDefinition) => void;
  startLabel: string;
  selected?: boolean;
  selectedLabel?: string;
  disabled?: boolean;
  disabledReason?: string;
  globalLabel: string;
  projectLabel: string;
  materialsLabel: string;
  memoryLabel: string;
  saveLabel: string;
  platformRuntimeLabel: string;
  codexRuntimeLabel: string;
}

export default function TaskCard({
  task,
  onStart,
  startLabel,
  selected = false,
  selectedLabel = 'Selected',
  disabled = false,
  disabledReason,
  globalLabel,
  projectLabel,
  materialsLabel,
  memoryLabel,
  saveLabel,
  platformRuntimeLabel,
  codexRuntimeLabel,
}: TaskCardProps) {
  const { token } = theme.useToken();
  const helperText = task.starter_prompts[0];
  const isProjectTask = task.project_ids.length > 0;
  const usesProjectMaterials = task.project_context_policy.inherit_project_sources === true;
  const usesResearchMemory = task.project_context_policy.include_research_memory === true;
  const hasResultTarget = Object.keys(task.result_presentation).length > 0;
  const runtimeKind = getTaskRuntimeKind(task);

  return (
    <SectionCard
      className={selected ? 'task-card-selected' : undefined}
      styles={{
        body: {
          padding: 16,
          height: '100%',
          display: 'flex',
          flexDirection: 'column',
          border: selected ? `1px solid ${token.colorPrimary}` : undefined,
        },
      }}
    >
      <Space size={[6, 6]} wrap style={{ marginBottom: 8 }}>
        <Tag color={isProjectTask ? 'blue' : 'default'}>
          {isProjectTask ? projectLabel : globalLabel}
        </Tag>
        <Tag color={runtimeKind === 'codex' ? 'purple' : 'geekblue'}>
          {runtimeKind === 'codex' ? codexRuntimeLabel : platformRuntimeLabel}
        </Tag>
        {usesProjectMaterials ? <Tag icon={<FileSearchOutlined />}>{materialsLabel}</Tag> : null}
        {usesResearchMemory ? <Tag icon={<DatabaseOutlined />}>{memoryLabel}</Tag> : null}
        {hasResultTarget ? <Tag icon={<SaveOutlined />}>{saveLabel}</Tag> : null}
      </Space>

      <div style={{ flex: 1 }}>
        <Title level={5} style={{ margin: 0 }}>
          {task.name}
        </Title>
        <Paragraph type="secondary" style={{ margin: '8px 0 0', fontSize: 13 }}>
          {task.description}
        </Paragraph>
        {helperText ? (
          <div style={{ marginTop: 12 }}>
            <Text type="secondary" style={{ fontSize: 12, display: 'block', marginBottom: 4 }}>
              Example prompt
            </Text>
            <Text type="secondary" ellipsis style={{ display: 'block' }}>
              {helperText}
            </Text>
          </div>
        ) : null}
      </div>

      <div style={{ marginTop: 16 }}>
        {disabled && disabledReason ? (
          <Text type="secondary" style={{ display: 'block', marginBottom: 8, fontSize: 12 }}>
            {disabledReason}
          </Text>
        ) : null}
        <Button
          block
          type={selected ? 'primary' : 'default'}
          onClick={() => onStart(task)}
          disabled={disabled}
        >
          {selected ? selectedLabel : startLabel}
        </Button>
      </div>
    </SectionCard>
  );
}
