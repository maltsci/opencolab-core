import { ArrowLeftOutlined, BookOutlined } from '@ant-design/icons';
import { Card, Descriptions, Empty, List, Space, Spin, Tag, Typography } from 'antd';
import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useNavigate, useParams } from 'react-router-dom';

import apiClient from '../services/api-client';

const { Text, Title } = Typography;

interface CourseReport {
  course_id: string;
  course_name: string;
  assignment_status: string;
  total_topics: number;
  completed_topics: number;
  practice_average_score: number | null;
  final_assessment_score: number | null;
  last_answered_at: string | null;
}

interface LearningReport {
  trainee_name: string;
  courses: CourseReport[];
}

export default function TrainingReport() {
  const { t, i18n } = useTranslation();
  const navigate = useNavigate();
  const { traineeId } = useParams();
  const [report, setReport] = useState<LearningReport>();
  const [loading, setLoading] = useState(true);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    if (!traineeId) return;
    apiClient.get<LearningReport>(`/training/reports/${traineeId}`)
      .then(({ data }) => setReport(data))
      .catch(() => setFailed(true))
      .finally(() => setLoading(false));
  }, [traineeId]);

  if (loading) return <Spin size="large" style={{ display: 'block', margin: '200px auto' }} />;
  if (failed || !report) return <Empty description={t('trainingReport.loadFailed')} style={{ marginTop: 160 }} />;

  const date = (value: string | null) => value ? new Date(value).toLocaleString(i18n.language) : t('trainingReport.notAvailable');

  return (
    <div style={{ maxWidth: 920, margin: '0 auto', padding: '40px 24px 64px' }}>
      <Space direction="vertical" size={8} style={{ width: '100%', marginBottom: 28 }}>
        <a onClick={() => navigate('/training/courses')}><ArrowLeftOutlined /> {t('trainingReport.back')}</a>
        <Title level={2} style={{ margin: 0 }}>{t('trainingReport.title', { name: report.trainee_name })}</Title>
        <Text type="secondary">{t('trainingReport.description')}</Text>
      </Space>

      {report.courses.length === 0 ? <Empty description={t('trainingReport.noCourses')} /> : (
        <List
          dataSource={report.courses}
          renderItem={(course) => (
            <List.Item>
              <Card style={{ width: '100%' }} title={<Space><BookOutlined /><span>{course.course_name}</span></Space>} extra={<Tag color="blue">{t(`trainingReport.assignmentStatus.${course.assignment_status}`)}</Tag>}>
                <Descriptions size="small" column={{ xs: 1, sm: 2 }}>
                  <Descriptions.Item label={t('trainingReport.topics')}>{t('trainingReport.topicProgress', { completed: course.completed_topics, total: course.total_topics })}</Descriptions.Item>
                  <Descriptions.Item label={t('trainingReport.practiceScore')}>{course.practice_average_score === null ? t('trainingReport.notAvailable') : t('trainingReport.score', { score: course.practice_average_score })}</Descriptions.Item>
                  <Descriptions.Item label={t('trainingReport.finalAssessment')}>{course.final_assessment_score === null ? t('trainingReport.notAvailable') : t('trainingReport.score', { score: course.final_assessment_score })}</Descriptions.Item>
                  <Descriptions.Item label={t('trainingReport.lastAnsweredAt')}>{date(course.last_answered_at)}</Descriptions.Item>
                </Descriptions>
              </Card>
            </List.Item>
          )}
        />
      )}
    </div>
  );
}
