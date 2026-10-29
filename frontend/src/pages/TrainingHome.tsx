import { ArrowRightOutlined, BookOutlined, CheckCircleFilled } from '@ant-design/icons';
import { Button, Empty, Progress, Spin, Tag, Typography } from 'antd';
import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useNavigate } from 'react-router-dom';

import { ROLE_ADMIN, ROLE_PI } from '../constants/roles';
import { useAuth } from '../hooks/useAuth';
import apiClient from '../services/api-client';
import './training-home.css';

const { Paragraph, Text, Title } = Typography;

interface TrainingOverviewModule {
  assignment_id: string;
  module_id: string;
  module_title: string;
  status: string;
  requires_retraining: boolean;
  latest_unit_assessment_score: number | null;
}

interface TrainingOverviewCourse {
  course_id: string;
  course_name: string;
  course_assignment_id: string | null;
  status: string;
  due_at: string | null;
  next_kind: 'module' | 'course';
  next_assignment_id: string;
  modules: TrainingOverviewModule[];
}

export default function TrainingHome() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const { user } = useAuth();
  const [training, setTraining] = useState<TrainingOverviewCourse[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    apiClient.get<TrainingOverviewCourse[]>('/training/me')
      .then(({ data }) => setTraining(data))
      .finally(() => setLoading(false));
  }, []);

  const canManage = user?.role === ROLE_ADMIN || user?.role === ROLE_PI;

  const openNext = (course: TrainingOverviewCourse) => {
    const path = course.next_kind === 'module'
      ? `/training/module-assignments/${course.next_assignment_id}`
      : `/training/assignments/${course.next_assignment_id}`;
    navigate(path);
  };

  return (
    <div className="training-home">
      <header className="training-home-header">
        <div>
          <Text className="training-home-eyebrow">{t('trainingHome.workspace')}</Text>
          <Title level={1}>{t('trainingHome.title')}</Title>
          <Paragraph>{t('trainingHome.description')}</Paragraph>
        </div>
        {canManage && (
          <Button onClick={() => navigate('/training/courses')}>
            {t('trainingHome.manageCourses')}
          </Button>
        )}
      </header>

      <section className="training-overview" aria-labelledby="my-training-title">
        <div className="training-overview-heading">
          <Title id="my-training-title" level={2}>{t('trainingHome.myTraining')}</Title>
          {!loading && training.length > 0 && (
            <Text type="secondary">{t('trainingHome.courseCount', { count: training.length })}</Text>
          )}
        </div>

        {loading ? (
          <Spin className="training-home-loading" />
        ) : training.length === 0 ? (
          <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={t('trainingHome.noTraining')} />
        ) : (
          <div className="training-course-list">
            {training.map((course) => {
              const completedModules = course.modules.filter((module) => module.status === 'completed').length;
              const moduleProgress = course.modules.length
                ? Math.round((completedModules / course.modules.length) * 100)
                : 0;
              const modulesDone = course.modules.length > 0 && completedModules === course.modules.length;
              return (
                <article className="training-course" key={course.course_id}>
                  <div className="training-course-summary">
                    <div className="training-course-title-row">
                      <BookOutlined />
                      <div>
                        <Title level={3}>{course.course_name}</Title>
                        {course.due_at && (
                          <Text type="secondary">
                            {t('trainingHome.dueAt', { date: new Date(course.due_at).toLocaleDateString() })}
                          </Text>
                        )}
                      </div>
                    </div>
                    <Tag color={course.status === 'completed' ? 'green' : course.status === 'in_progress' ? 'blue' : 'default'}>
                      {t(`trainingHome.assignmentStatus.${course.status}`)}
                    </Tag>
                  </div>

                  {course.modules.length > 0 && (
                    <div className="training-course-modules">
                      <div className="training-module-progress">
                        <Text strong>{t('trainingHome.moduleProgress', {
                          completed: completedModules,
                          total: course.modules.length,
                        })}</Text>
                        <Progress percent={moduleProgress} showInfo={false} size="small" />
                      </div>
                      <div className="training-module-list">
                        {course.modules.map((module, index) => (
                          <div className="training-module-row" key={module.assignment_id}>
                            <span className={`training-module-index${module.status === 'completed' ? ' completed' : ''}`}>
                              {module.status === 'completed' ? <CheckCircleFilled /> : index + 1}
                            </span>
                            <Text className="training-module-name">{module.module_title}</Text>
                            <Tag color={module.status === 'completed' ? 'green' : 'default'}>
                              {t(`trainingHome.assignmentStatus.${module.status}`)}
                            </Tag>
                            {module.requires_retraining && (
                              <Tag color="orange">{t('trainingHome.retrainingRequired')}</Tag>
                            )}
                            {module.latest_unit_assessment_score !== null && (
                              <Text className="training-module-score">
                                {t('trainingHome.moduleScore', { score: module.latest_unit_assessment_score })}
                              </Text>
                            )}
                          </div>
                        ))}
                      </div>
                    </div>
                  )}

                  <footer className="training-course-footer">
                    <Text type="secondary">
                      {modulesDone && course.course_assignment_id && course.status !== 'completed'
                        ? t('trainingHome.modulesCompleteNextAssessment')
                        : t(`trainingHome.next.${course.next_kind}`)}
                    </Text>
                    <Button type="primary" icon={<ArrowRightOutlined />} onClick={() => openNext(course)}>
                      {course.status === 'completed'
                        ? t('trainingHome.viewResult')
                        : t('trainingHome.continueLearning')}
                    </Button>
                  </footer>
                </article>
              );
            })}
          </div>
        )}
      </section>
    </div>
  );
}
