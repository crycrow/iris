import { createRouter, createWebHistory } from "vue-router";
import { useAuth } from "../common/stores/auth.js";
const routes = [
  { path: "/login", component: () => import("../pages/LoginPage.vue") },
  { path: "/", component: () => import("../pages/DashboardPage.vue") },
  { path: "/projects", component: () => import("../pages/ProjectsPage.vue") },
  {
    path: "/projects/:id",
    component: () => import("../pages/ProjectCardPage.vue"),
  },
  {
    path: "/timebook",
    component: () => import("../modules/time-tracking/views/Timesheet.vue"),
  },
  {
    path: "/risks",
    component: () => import("../modules/risks/views/RiskRegistry.vue"),
  },
  {
    path: "/risks/:id",
    component: () => import("../modules/risks/views/RiskCard.vue"),
  },
  {
    path: "/risk-catalog",
    component: () => import("../modules/risks/views/RiskTypeCatalog.vue"),
  },
  {
    path: "/reports/:kind?",
    component: () => import("../pages/ReportsPage.vue"),
    meta: { manager: true },
  },
  {
    path: "/settings",
    component: () => import("../pages/SettingsPage.vue"),
    meta: { admin: true },
  },
  {
    path: "/users",
    component: () => import("../pages/UsersPage.vue"),
    meta: { admin: true },
  },
  { path: "/forbidden", component: () => import("../pages/ForbiddenPage.vue") },
  { path: "/:pathMatch(.*)*", redirect: "/" },
];
const router = createRouter({ history: createWebHistory(), routes });
router.beforeEach((to) => {
  const auth = useAuth();
  if (!auth.token && to.path != "/login") return "/login";
  if (auth.token && to.path === "/login") return "/";
  if ((to.meta.admin && !auth.admin) || (to.meta.manager && !auth.manager))
    return "/forbidden";
});
export default router;
