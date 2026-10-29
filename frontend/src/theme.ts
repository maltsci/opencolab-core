import type { ThemeConfig } from 'antd';

/**
 * Global Ant Design theme tokens.
 * Keep this minimal: the app uses the default antd color palette; only
 * shape and layout background are customized for a cleaner look.
 */
export const themeConfig: ThemeConfig = {
  token: {
    borderRadius: 8,
    colorBgLayout: '#f5f6f8',
  },
};
