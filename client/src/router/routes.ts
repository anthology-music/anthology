import type { RouteRecordRaw } from 'vue-router';

const routes: RouteRecordRaw[] = [
  {
    path: '/',
    component: () => import('@/layouts/MainLayout.vue'),
    children: [
      { path: '', redirect: { name: 'local' } },
      {
        path: 'streaming',
        name: 'streaming',
        component: () => import('@/pages/StreamingPage.vue'),
      },
      { path: 'local', name: 'local', component: () => import('@/pages/LocalPage.vue') },
      { path: 'works', name: 'works', component: () => import('@/pages/WorksPage.vue') },
      { path: 'settings', name: 'settings', component: () => import('@/pages/SettingsPage.vue') },
      // Developer demo of a large list (server needs ANTHOLOGY_DEV_DEMO=true); dev builds only.
      ...(import.meta.env.DEV
        ? [
            {
              path: 'dev/demo',
              name: 'demo',
              component: () => import('@/features/dev/DemoListPage.vue'),
            },
          ]
        : []),
    ],
  },
  {
    path: '/',
    component: () => import('@/layouts/AuthLayout.vue'),
    meta: { public: true },
    children: [
      {
        path: 'login',
        name: 'login',
        meta: { public: true },
        component: () => import('@/features/users/pages/LoginPage.vue'),
      },
      {
        path: 'setup',
        name: 'setup',
        meta: { public: true },
        component: () => import('@/features/users/pages/SetupPage.vue'),
      },
    ],
  },
  { path: '/:catchAll(.*)*', component: () => import('@/pages/NotFoundPage.vue') },
];

export default routes;
