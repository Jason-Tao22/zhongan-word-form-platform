import { createRouter, createWebHistory } from 'vue-router'

export default createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', component: () => import('../pages/TemplatesPage.vue') },
    { path: '/templates/:templateId/review', component: () => import('../pages/TemplateReviewPage.vue'), props: true },
    { path: '/templates/:templateId/form', component: () => import('../pages/FormPage.vue'), props: true },
  ],
})
