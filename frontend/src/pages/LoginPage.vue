<script setup>
import { ref } from "vue";
import { useRouter } from "vue-router";
import { useAuth } from "../common/stores/auth.js";
import CompanyLogo from "../common/components/CompanyLogo.vue";
const auth = useAuth(),
  router = useRouter(),
  login = ref(""),
  password = ref(""),
  error = ref(""),
  busy = ref(false);
async function submit() {
  busy.value = true;
  error.value = "";
  try {
    await auth.login(login.value.trim(), password.value);
    router.push("/");
  } catch (e) {
    error.value = e.message;
  } finally {
    busy.value = false;
  }
}
</script>
<template>
  <main class="login-page">
    <div class="login-shell">
      <header class="login-brand">
        <span class="login-logo"><CompanyLogo /></span>
        <strong>Ирис</strong>
      </header>
      <div class="login-content">
        <section class="login-story" aria-label="О системе">
          <h2>Учёт трудозатрат и управление рисками проектов</h2>
        <div class="login-preview">
          <p class="preview-title">Работа с проектом</p>
          <dl class="project-outline">
            <div><dt>Задачи</dt><dd>Календарный план и доска</dd></div>
            <div><dt>Трудозатраты</dt><dd>План и фактические часы</dd></div>
            <div><dt>Риски</dt><dd>Критичность и реагирование</dd></div>
          </dl>
        </div>
        </section>
        <section class="login-card" aria-labelledby="login-title">
      <h1 id="login-title">Войти в Ирис</h1>
      <p class="mobile-context">Учёт трудозатрат и управление рисками проектов</p>

      <form @submit.prevent="submit">
        <label
          >Логин<input
            v-model="login"
            required
            autocomplete="username"
            autofocus /></label
        ><label
          >Пароль<input
            v-model="password"
            required
            type="password"
            autocomplete="current-password"
        /></label>
        <p v-if="error" class="alert error" role="alert">{{ error }}</p>
        <button class="primary full" :disabled="busy">
          {{ busy ? "Выполняется вход…" : "Войти" }}
        </button>
      </form>
      <details class="demo">
        <summary>Демонстрационные учётные записи</summary>
        <button
          v-for="[role, l, p] in [
            ['Администратор', 'admin', 'admin123'],
            ['Руководитель', 'manager1', 'manager123'],
            ['Сотрудник', 'employee1', 'employee123'],
          ]"
          :key="l"
          @click="
            login = l;
            password = p;
          "
        >
          {{ role }} <small>{{ l }} / {{ p }}</small>
        </button>
      </details>

        </section>
      </div>
    </div>
  </main>
</template>
<style scoped>
.login-page {
  display: grid;
  place-items: center;
  min-height: 100dvh;
  padding: 48px 32px;
  background: var(--bg);
  color: var(--text);
}
.login-shell {
  width: min(100%, 1088px);
  padding: 48px 56px 56px;
  background: var(--card);
  border: 1px solid var(--border);
  border-radius: 20px;
  box-shadow: 0 8px 32px #17171b06;
}
.login-brand {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 48px;
}
.login-logo { width: 36px; height: 36px; }
.login-logo :deep(.company-logo) { filter: var(--brand-image-filter); }
.login-brand strong { font-size: 24px; line-height: 32px; font-weight: 500; }
.login-content {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 360px;
  align-items: start;
  gap: 80px;
}
.login-story { min-width: 0; }
.login-story h2 {
  max-width: 13em;
  margin: 0 0 32px;
  font-size: 32px;
  line-height: 1.25;
  font-weight: 400;
}
.login-preview {
  color: var(--text);
  max-width: 480px;
  padding: 24px;
  border: 1px solid transparent;
  border-radius: 16px;
  background: transparent;
}
.preview-title {
  margin: 0 0 24px;
  color: var(--text);
  font-size: 16px;
  font-weight: 500;
}
.project-outline {
  margin: 0;
}
.project-outline > div {
  position: relative;
  padding: 0 0 24px 24px;
  border-left: 1px solid var(--border);
}
.project-outline > div:last-child {
  padding-bottom: 0;
  border-left-color: transparent;
}
.project-outline > div::before {
  content: "";
  position: absolute;
  top: 4px;
  left: -4px;
  width: 8px;
  height: 8px;
  background: var(--accent);
  border-radius: 2px;
}
.project-outline dt {
  font-size: 14px;
  font-weight: 500;
  line-height: 20px;
}
.project-outline dd {
  margin: 4px 0 0;
  color: var(--secondary);
  font-size: 14px;
  line-height: 20px;
}
.login-card { min-width: 0; }
.login-card h1 { margin: 0 0 28px; font-size: 28px; line-height: 36px; font-weight: 500; }
.login-card form { gap: 20px; }
.login-card label { gap: 8px; font-size: 14px; }
.login-card input, .login-card .primary { min-height: 48px; border-radius: 8px; }
.login-card input { background: var(--card); }
.login-card input:autofill {
  box-shadow: 0 0 0 1000px var(--card) inset;
  -webkit-text-fill-color: var(--text);
  caret-color: var(--text);
}
.login-card .primary { margin-top: 4px; }
.demo { margin-top: 24px; padding-top: 20px; font-size: 12px; }
.demo summary { line-height: 20px; }
.demo button { font-size: 13px; padding: 12px; }
.demo small { margin-top: 4px; font-size: 12px; }
.mobile-context { display: none; }
@media (max-width: 1000px) {
  .login-shell { padding: 40px; }
  .login-content { grid-template-columns: minmax(0, 1fr) 336px; gap: 48px; }
  .login-story h2 { font-size: 28px; }
}
@media (max-width: 800px) {
  .login-page { padding: 32px 16px; }
  .login-shell { max-width: 464px; padding: 32px; border-radius: 16px; }
  .login-brand { margin-bottom: 32px; }
  .login-content { grid-template-columns: 1fr; gap: 0; }
  .login-story { display: none; }
  .login-card h1 { margin-bottom: 12px; }
  .mobile-context { display: block; margin: 0 0 24px; color: var(--secondary); font-size: 14px; line-height: 20px; }
}
@media (max-width: 400px) {
  .login-page { padding: 16px; }
  .login-shell { padding: 24px; }
}
@media (max-height: 680px) {
  .login-page { padding-block: 24px; }
  .login-brand { margin-bottom: 24px; }
}
</style>

