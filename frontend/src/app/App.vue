<script setup>
import { ref, watch, nextTick, onMounted, onBeforeUnmount } from "vue";
import { useRoute, useRouter } from "vue-router";
import { useAuth } from "../common/stores/auth.js";
import { useUi } from "../common/stores/ui.js";
import { roles } from "../common/utils/format.js";
import CompanyLogo from "../common/components/CompanyLogo.vue";
import UiIcon from "../common/components/UiIcon.vue";
import ProjectSearch from "../common/components/ProjectSearch.vue";
const auth = useAuth(),
  ui = useUi(),
  route = useRoute(),
  router = useRouter(),
  open = ref(false),
  collapsed = ref(false),
  side = ref();
const theme = ref(localStorage.getItem("theme") || "light");
function toggleTheme() {
  theme.value = theme.value === "light" ? "dark" : "light";
  localStorage.setItem("theme", theme.value);
  document.documentElement.dataset.theme = theme.value;
}
watch(
  () => route.path,
  () => (open.value = false),
);
watch(open, async (value) => {
  if (value) {
    await nextTick();
    side.value?.querySelector("button")?.focus();
  }
});
function trap(e) {
  if (!open.value) return;
  if (e.key === "Escape") open.value = false;
  if (e.key === "Tab") {
    const nodes = [...side.value.querySelectorAll("a,button")];
    if (e.shiftKey && document.activeElement === nodes[0]) {
      e.preventDefault();
      nodes.at(-1).focus();
    } else if (!e.shiftKey && document.activeElement === nodes.at(-1)) {
      e.preventDefault();
      nodes[0].focus();
    }
  }
}
async function logout() {
  await ui.act(() => auth.logout(), "");
  router.push("/login");
}
function expired() {
  auth.clear();
  router.push("/login");
}
onMounted(() => {
  document.documentElement.dataset.theme = theme.value;
  window.addEventListener("session-expired", expired);
  if (auth.token) ui.act(() => auth.refresh(), "");
});
onBeforeUnmount(() => window.removeEventListener("session-expired", expired));
</script>
<template>
  <div
    v-if="auth.user && route.path != '/login'"
    class="layout"
    :class="{ collapsed }"
  >
    <div v-if="open" class="drawer-scrim" @click="open = false" />
    <aside ref="side" class="sidebar" :class="{ open }" @keydown="trap">
      <div class="brand">
        <span class="brand-mark"><CompanyLogo /></span
        ><span class="nav-text brand-name">Ирис</span
        ><button
          class="drawer-close"
          aria-label="Закрыть меню"
          @click="open = false"
        >
          <UiIcon name="close" />
        </button>
      </div>
      <nav aria-label="Основная навигация">
        <RouterLink to="/" title="Главное"
          ><UiIcon name="home" /><span class="nav-text"
            >Главное</span
          ></RouterLink
        ><RouterLink to="/projects" title="Проекты"
          ><UiIcon name="projects" /><span class="nav-text"
            >Проекты</span
          ></RouterLink
        ><RouterLink
          to="/timebook"
          :title="auth.admin ? 'Табель сотрудников' : 'Мои трудозатраты'"
          ><UiIcon name="time" /><span class="nav-text"
            >{{ auth.admin ? "Табель сотрудников" : "Мои трудозатраты" }}</span
          ></RouterLink
        >
        <p class="nav-text nav-label">Управление рисками</p>
        <RouterLink to="/risks" title="Реестр рисков"
          ><UiIcon name="risk" /><span class="nav-text"
            >Реестр рисков</span
          ></RouterLink
        ><RouterLink to="/risk-catalog" title="Справочник рисков"
          ><UiIcon name="catalog" /><span class="nav-text"
            >Справочник рисков</span
          ></RouterLink
        ><template v-if="auth.manager"
          ><p class="nav-text nav-label">Отчёты</p>
          <RouterLink to="/reports/labor" title="Трудозатраты"
            ><UiIcon name="chart" /><span class="nav-text"
              >Трудозатраты</span
            ></RouterLink
          ><RouterLink to="/reports/risks" title="Отчёт по рискам"
            ><UiIcon name="risk" /><span class="nav-text"
              >Риски и реагирование</span
            ></RouterLink
          ><RouterLink to="/reports/summary" title="Сводка по проекту"
            ><UiIcon name="chart" /><span class="nav-text"
              >Сводка по проекту</span
            ></RouterLink
          ></template
        ><RouterLink v-if="auth.admin" to="/users" title="Пользователи"
          ><UiIcon name="users" /><span class="nav-text"
            >Пользователи</span
          ></RouterLink
        ><RouterLink v-if="auth.admin" to="/settings" title="Настройки"
          ><UiIcon name="settings" /><span class="nav-text"
            >Настройки</span
          ></RouterLink
        >
      </nav>
      <button
        class="collapse-button"
        @click="collapsed = !collapsed"
        :aria-label="collapsed ? 'Развернуть меню' : 'Свернуть меню'"
      >
        <UiIcon :name="collapsed ? 'right' : 'left'" /><span class="nav-text">Свернуть меню</span>
      </button>
    </aside>
    <div class="main">
      <header class="topbar">
        <button
          class="burger"
          @click="open = true"
          aria-label="Открыть меню"
          :aria-expanded="open"
        >
          <UiIcon name="menu" /></button
        ><ProjectSearch :key="auth.user.user_id" />
        <div class="toolbar">
          <button @click="toggleTheme" aria-label="Переключить тему">
            <UiIcon :name="theme === 'light' ? 'moon' : 'sun'" />
          </button>
          <div class="user-avatar" aria-hidden="true">
            {{
              auth.user.full_name
                .split(" ")
                .slice(0, 2)
                .map((x) => x[0])
                .join("")
            }}
          </div>
          <div class="user-label">
            <strong>{{ auth.user.full_name }}</strong
            ><small>{{ roles[auth.user.role] }}</small>
          </div>
          <button class="logout-button" @click="logout" title="Выйти">
            <UiIcon name="logout" /><span>Выйти</span>
          </button>
        </div>
      </header>
      <main class="content" id="main-content">
        <RouterView :key="route.path" />
      </main>
    </div>
  </div>
  <RouterView v-else />
  <div
    v-if="ui.message"
    role="status"
    class="toast"
    :class="{ error: ui.error }"
  >
    {{ ui.message
    }}<button @click="ui.message = ''" aria-label="Закрыть уведомление">
      <UiIcon name="close" />
    </button>
  </div>
</template>
