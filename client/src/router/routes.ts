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
      {
        // Local view: the library (spec: library, Local library view and following).
        path: 'local',
        name: 'local',
        component: () => import('@/pages/LocalPage.vue'),
        redirect: { name: 'library-albums' },
        children: [
          {
            path: 'albums',
            name: 'library-albums',
            component: () => import('@/features/library/pages/AlbumsPage.vue'),
          },
          {
            path: 'artists',
            name: 'library-artists',
            component: () => import('@/features/library/pages/ArtistsPage.vue'),
          },
          {
            path: 'artists/:artistId',
            name: 'library-artist',
            props: true,
            component: () => import('@/features/library/pages/ArtistPage.vue'),
          },
          {
            path: 'releases/:releaseId',
            name: 'library-release',
            props: true,
            component: () => import('@/features/library/pages/ReleasePage.vue'),
          },
          {
            path: 'tracks',
            name: 'library-tracks',
            component: () => import('@/features/library/pages/TracksPage.vue'),
          },
          {
            // Search (spec: search): text, type and context in the query.
            path: 'search',
            name: 'search',
            component: () => import('@/features/search/pages/SearchPage.vue'),
          },
        ],
      },
      { path: 'works', name: 'works', component: () => import('@/pages/WorksPage.vue') },
      {
        // Review list (spec: review): editors and admins.
        path: 'review',
        name: 'review',
        meta: { editors: true },
        component: () => import('@/features/review/pages/ReviewPage.vue'),
      },
      {
        // Conflict list (spec: tagging, Conflict list): editors and admins.
        path: 'conflicts',
        name: 'conflicts',
        meta: { editors: true },
        component: () => import('@/features/tagging/pages/ConflictsPage.vue'),
      },
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
