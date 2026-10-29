/**
 * User role constants. Must match backend app.core.constants.
 */

export const ROLE_ADMIN = 'admin';
export const ROLE_PI = 'pi';
export const ROLE_RESEARCHER = 'researcher';

export const ROLES_CAN_CREATE_PROJECT: readonly string[] = [ROLE_ADMIN, ROLE_PI, ROLE_RESEARCHER];

export const ROLES_PRIVILEGED: readonly string[] = [ROLE_ADMIN, ROLE_PI];

export const ROLE_OPTIONS = [
  { value: ROLE_RESEARCHER, label: 'Researcher' },
  { value: ROLE_PI, label: 'PI' },
  { value: ROLE_ADMIN, label: 'Admin' },
] as const;
