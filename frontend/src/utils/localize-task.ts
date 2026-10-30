import type { i18n } from 'i18next';
import type { TaskDefinition } from '../types/task';

export function localizeTask(task: TaskDefinition, i18n: i18n): TaskDefinition {
  if (!task.is_builtin || !i18n.language.startsWith('en')) return task;
  const key = `task.builtin.${task.id}`;
  const source = i18n.getFixedT('zh-CN');
  const target = i18n.getFixedT('en-US');
  const translate = (field: string, value: string) => {
    const fieldKey = `${key}.${field}`;
    return i18n.exists(fieldKey, { lng: 'zh-CN' }) && value === source(fieldKey)
      ? target(fieldKey)
      : value;
  };
  return {
    ...task,
    name: translate('name', task.name),
    description: translate('description', task.description),
    starter_prompts: task.starter_prompts.map((prompt, index) => index === 0 ? translate('prompt', prompt) : prompt),
  };
}
